"""Explicit engine replacement uses only temporary tasks and fake providers."""
import base64
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
import uuid
from unittest.mock import patch

from PIL import Image
import server
import task_cover


class CoverReplaceUnknownTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.tid = 'replacement_fixture'
        self.folder = self.root / 'tasks' / self.tid
        self.folder.mkdir(parents=True)
        self.addCleanup(patch.stopall)
        patch.object(server, 'DATA_DIR', self.root).start()
        patch.object(server, 'load_settings', return_value={}).start()
        self.cfg = {'provider': 'modelscope', 'api_key': 'fixture-key', 'model': 'fixture-image'}
        patch.object(server, 'resolve_image_config', side_effect=lambda settings, provider=None: {**self.cfg, 'provider': provider or self.cfg['provider']}).start()
        self.generate = patch.object(server, 'image_dispatcher', side_effect=AssertionError('supplier forbidden')).start()
        patch.object(server, '_http_post_json', side_effect=AssertionError('network forbidden')).start()
        patch.object(server, '_http_get_json', side_effect=AssertionError('network forbidden')).start()
        task_cover.write(self.folder / '02-meta.json', {'title': '封面标题', 'cover_image_prompts': ['人物侧影']})
        task_cover.write(self.folder / 'client_config.json', {'cover': {'provider': 'modelscope'}})
        task_cover.write(self.folder / 'cover-editor.json', {'1': {'provider': 'modelscope'}})
        self.old = {'status': 'unknown', 'provider': 'runninghub', 'model': 'rh-image-g2', 'operationId': 'old-operation', 'firstDiagnostic': {'message': 'old timeout'}, 'opaqueReceipt': {'keep': [1, 2]}}
        self.job_path = self.folder / 'cover-job-1.json'
        self.old_bytes = (json.dumps(self.old, ensure_ascii=False, indent=3) + '\n').encode('utf8')
        self.job_path.write_bytes(self.old_bytes)
        self.op = str(uuid.uuid4())

    def png(self):
        out = io.BytesIO()
        Image.new('RGB', (32, 48), 'blue').save(out, 'PNG')
        return out.getvalue()

    def replace(self, **updates):
        return task_cover.action(server, self.tid, 'replace-unknown', {'slot': 1, 'provider': 'modelscope', 'operation_id': self.op, 'acknowledge_unknown': True, **updates})

    def archives(self):
        return list((self.folder / '.cover-replacements').glob('*.json'))

    def test_unsubmitted_pause_preserves_replacement_operation_target_and_fallback(self):
        self.replace();paused=InterruptedError('pause');paused.image_not_submitted=True
        self.generate.side_effect=paused
        with self.assertRaises(InterruptedError):task_cover.initial(server,self.tid,explicit_prompt='scene')
        self.assertEqual(task_cover.read(self.job_path,{})['status'],'unsubmitted')
        captured=[]
        def generate(cfg,*args,**kwargs):captured.append(cfg);return {'b64':base64.b64encode(self.png()).decode()}
        self.generate.side_effect=generate
        task_cover.initial(server,self.tid,explicit_prompt='scene')
        job=task_cover.read(self.job_path,{})
        self.assertEqual(job['operationId'],self.op);self.assertEqual(job['targetProvider'],'modelscope')
        self.assertTrue(job['replacement']);self.assertFalse(captured[0]['auto_fallback_gpt'])

    def test_confirm_archives_exact_old_receipt_and_does_not_submit(self):
        result = self.replace()
        self.assertEqual(result['job']['status'], 'replacement_ready')
        self.assertEqual(result['job']['operationId'], self.op)
        self.assertEqual(result['job']['targetProvider'], 'modelscope')
        self.assertEqual(len(self.archives()), 1)
        self.assertEqual(self.archives()[0].read_bytes(), self.old_bytes)
        self.generate.assert_not_called()

    def test_explicit_new_operation_generates_once_and_keeps_success_assets(self):
        shots = self.folder / '04-scene.png'
        tts = self.folder / 'podcast.mp3'
        shots.write_bytes(b'scene-preserved')
        tts.write_bytes(b'voice-preserved')
        self.replace()
        self.generate.side_effect = None
        self.generate.return_value = {'b64': base64.b64encode(self.png()).decode()}
        result = task_cover.initial(server, self.tid, options={'provider': 'runninghub'})
        self.assertEqual(Path(result['path']).read_bytes(), self.png())
        self.assertEqual(task_cover.read(self.job_path, {})['operationId'], self.op)
        self.assertEqual(self.generate.call_args.args[0]['provider'], 'modelscope')
        self.replace()
        task_cover.initial(server, self.tid)
        self.generate.assert_called_once()
        self.assertEqual(len(self.archives()), 1)
        self.assertEqual(shots.read_bytes(), b'scene-preserved')
        self.assertEqual(tts.read_bytes(), b'voice-preserved')

    def test_duplicate_confirmation_preserves_new_unknown_and_new_id(self):
        self.replace()
        self.generate.side_effect = TimeoutError('fixture timeout')
        with self.assertRaises(TimeoutError):
            task_cover.initial(server, self.tid)
        before = self.job_path.read_bytes()
        self.replace()
        self.assertEqual(self.job_path.read_bytes(), before)
        with self.assertRaises(ValueError):
            task_cover.initial(server, self.tid)
        self.generate.assert_called_once()
        self.assertEqual(len(self.archives()), 1)
        with self.assertRaises(ValueError):
            self.replace(operation_id=str(uuid.uuid4()))

    def test_duplicate_confirmation_preserves_new_inflight_id(self):
        self.replace()
        def submit(*args, **kwargs):
            kwargs['on_task_id']('new-paid-id')
            raise TimeoutError('poll fixture')
        self.generate.side_effect = submit
        with self.assertRaises(TimeoutError):
            task_cover.initial(server, self.tid)
        before = self.job_path.read_bytes()
        self.assertEqual(self.replace()['job']['taskId'], 'new-paid-id')
        self.assertEqual(self.job_path.read_bytes(), before)
        self.generate.assert_called_once()

    def test_ordinary_resume_stays_blocked_without_explicit_confirm(self):
        with self.assertRaises(ValueError):
            task_cover.initial(server, self.tid)
        with self.assertRaises(ValueError):
            task_cover.action(server, self.tid, 'generate', {'operation_id': self.op})
        self.assertEqual(self.job_path.read_bytes(), self.old_bytes)
        self.generate.assert_not_called()

    def test_unsafe_replacements_do_not_mutate_old_receipt(self):
        cases = [({'acknowledge_unknown': False}, {}), ({'acknowledge_unknown': 'true'}, {}), ({'provider': 'runninghub'}, {}), ({'provider': 'jimeng'}, {}), ({'slot': 2}, {}), ({'operation_id': '../bad'}, {}), ({}, {'taskId': 'paid-id'}), ({}, {'result': {'url': 'https://fixture.invalid/paid.png'}}), ({}, {'status': 'pending'}), ({}, {'status': 'failed'})]
        for payload, updates in cases:
            with self.subTest(payload=payload, updates=updates):
                task_cover.write(self.job_path, {**self.old, **updates})
                before = self.job_path.read_bytes()
                with self.assertRaises(ValueError):
                    self.replace(**payload)
                self.assertEqual(self.job_path.read_bytes(), before)
                self.assertEqual(self.archives(), [])
        self.generate.assert_not_called()

    def test_submitting_without_id_can_be_explicitly_replaced(self):
        task_cover.write(self.job_path, {**self.old, 'status': 'submitting'})
        self.assertEqual(self.replace()['job']['status'], 'replacement_ready')

    def test_local_cover_is_reused_before_unknown_receipt_and_rejects_replace(self):
        target = self.folder / 'cover-poster-1.png'
        target.write_bytes(self.png())
        task_cover.write(self.folder / 'cover-meta.json', {'path': str(target), 'url': '/api/task_cover/replacement_fixture/1.png'})
        result = task_cover.initial(server, self.tid)
        self.assertEqual(Path(result['path']).read_bytes(), self.png())
        self.assertEqual(self.job_path.read_bytes(), self.old_bytes)
        with self.assertRaises(ValueError):
            self.replace()
        self.generate.assert_not_called()

    def test_pinned_replacement_rejects_provider_change_and_new_generate_id(self):
        self.replace()
        task_cover.write(self.folder / 'cover-editor.json', {'1': {'provider': 'jimeng'}})
        with self.assertRaises(ValueError):
            task_cover.initial(server, self.tid)
        with self.assertRaises(ValueError):
            task_cover.action(server, self.tid, 'generate', {'operation_id': str(uuid.uuid4())})
        self.assertEqual(task_cover.read(self.job_path, {})['status'], 'replacement_ready')
        self.generate.assert_not_called()

    def test_archive_failure_leaves_old_job_untouched(self):
        with patch.object(Path, 'mkdir', side_effect=OSError('fixture archive unavailable')):
            with self.assertRaises(OSError):
                self.replace()
        self.assertEqual(self.job_path.read_bytes(), self.old_bytes)
        self.generate.assert_not_called()

    def test_old_queue_snapshot_without_editor_cannot_change_fixed_provider(self):
        (self.folder / 'cover-editor.json').unlink()
        self.replace()
        self.generate.side_effect = None
        self.generate.return_value = {'b64': base64.b64encode(self.png()).decode()}
        task_cover.initial(server, self.tid, options={'provider': 'runninghub'})
        self.assertEqual(self.generate.call_args.args[0]['provider'], 'modelscope')
        self.assertEqual(task_cover.read(self.job_path, {})['operationId'], self.op)

    def test_replacement_never_falls_back_to_the_old_engine(self):
        self.cfg.update(auto_fallback_gpt=True, fallback_provider='runninghub')
        self.replace()
        self.generate.side_effect = None
        self.generate.return_value = {'b64': base64.b64encode(self.png()).decode()}
        task_cover.initial(server, self.tid)
        self.assertFalse(self.generate.call_args.args[0]['auto_fallback_gpt'])

    def test_archive_survives_failed_intent_write_and_retry_does_not_duplicate(self):
        original_write = task_cover.write
        def failing_write(path, value):
            if path == self.job_path:
                raise OSError('fixture intent write interrupted')
            return original_write(path, value)
        with patch.object(task_cover, 'write', side_effect=failing_write):
            with self.assertRaises(OSError):
                self.replace()
        self.assertEqual(self.job_path.read_bytes(), self.old_bytes)
        self.assertEqual(len(self.archives()), 1)
        self.assertEqual(self.archives()[0].read_bytes(), self.old_bytes)
        self.replace()
        self.assertEqual(len(self.archives()), 1)
        self.generate.assert_not_called()

    def test_archive_must_be_flushed_before_original_job_can_change(self):
        with patch.object(task_cover.os, 'fsync', side_effect=OSError('fixture flush failed')):
            with self.assertRaises(OSError):
                self.replace()
        self.assertEqual(self.job_path.read_bytes(), self.old_bytes)
        self.assertEqual(self.archives(), [])
        self.generate.assert_not_called()

    def test_existing_paid_result_is_queried_without_new_generation(self):
        task_cover.write(self.job_path, {**self.old, 'result': {'b64': base64.b64encode(self.png()).decode()}})
        result = task_cover.initial(server, self.tid)
        self.assertEqual(Path(result['path']).read_bytes(), self.png())
        self.generate.assert_not_called()

    def test_invalid_local_image_still_obeys_unknown_receipt_protection(self):
        (self.folder / 'cover-poster-1.png').write_bytes(b'not a picture')
        with self.assertRaises(ValueError):
            task_cover.initial(server, self.tid)
        self.assertEqual(self.job_path.read_bytes(), self.old_bytes)
        self.generate.assert_not_called()

    def test_missing_old_local_metadata_can_be_replaced_explicitly(self):
        task_cover.write(self.folder / 'cover-meta.json', {'path': str(self.folder / 'missing.png'), 'url': '/api/task_cover/replacement_fixture/1.png'})
        self.replace()
        self.generate.side_effect = None
        self.generate.return_value = {'b64': base64.b64encode(self.png()).decode()}
        task_cover.initial(server, self.tid)
        self.generate.assert_called_once()

    def test_workflow_provider_is_valid_and_query_uses_adapter(self):
        task_cover.validate_options(server, {'provider': 'runninghub_workflow'})
        task_cover.sync_provider_config(self.folder, {'cover': {'provider': 'modelscope'}}, {'cover': {'provider': 'runninghub_workflow'}})
        self.assertEqual(task_cover.view(server, self.tid)['provider'], 'runninghub_workflow')
        cfg = {**self.cfg, 'provider': 'runninghub_workflow'}
        task_cover.write(self.job_path, {'provider': 'runninghub_workflow', 'status': 'pending', 'taskId': 'workflow-paid-id', 'credential': task_cover.credential(cfg)})
        query = unittest.mock.Mock(return_value={'status': 'PENDING'})
        with patch.dict(sys.modules, {'rh_workflow_provider': types.SimpleNamespace(query=query)}):
            task_cover.action(server, self.tid, 'query', {})
        query.assert_called_once()
        self.assertEqual(query.call_args.args, (server, {**cfg, 'auto_fallback_gpt': False}, 'workflow-paid-id'))


if __name__ == '__main__':
    unittest.main()
