"""Exercise the real image stage with fake suppliers, never paid services."""
import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import server
import task_cover
import task_queue


class AutoRetryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.folder = self.root / 'tasks/fixture'
        (self.folder / 'covers').mkdir(parents=True)
        (self.folder / 'covers/1.png').write_bytes(b'already-completed')
        self.settings = {'image': {'provider': 'runninghub'}, 'runninghub': {'api_key': 'fixture-key'}}
        self.addCleanup(patch.stopall)
        patch.object(server, 'DATA_DIR', self.root).start()
        patch.object(server, 'load_settings', return_value=self.settings).start()
        self.query = patch.object(task_cover, 'query_provider', return_value={'status': 'FAILED', 'failReason': 'worker unavailable'}).start()
        self.save = patch.object(server, 'save_cover_image', side_effect=self.save_image).start()
        self.dispatch = patch.object(server, 'image_dispatcher', side_effect=self.generate).start()
        patch('time.sleep', return_value=None).start()
        self.calls = 0

    def save_image(self, *args):
        target = self.root / 'covers/result.png'
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(b'generated-image')
        return '/covers/result.png'

    def generate(self, cfg, prompt, **kwargs):
        self.calls += 1
        kwargs['on_task_id']('fixture-' + str(self.calls), cfg)
        if self.calls == 1:
            raise RuntimeError('RunningHub 任务失败: worker unavailable')
        return {'b64': base64.b64encode(b'generated-image').decode()}

    def run_stage(self, **data):
        return task_queue.dispatch(server, '/api/step4_generate_images', {
            'task_id': 'fixture', 'prompts': [{'idx': 1, 'desc_prompt': 'saved'}, {'idx': 2, 'desc_prompt': 'missing'}],
            **data}, 'fixture')

    def receipt(self):
        return json.loads((self.folder / 'image-jobs/2.json').read_text('utf8'))

    def test_default_retries_only_failed_scene_once_and_preserves_success(self):
        result = self.run_stage()
        self.assertTrue(all(r['ok'] for r in result['results']), result)
        self.assertEqual(self.calls, 2)
        self.assertEqual((self.folder / 'covers/1.png').read_bytes(), b'already-completed')
        self.assertEqual(result['results'][1]['auto_retries'], 1)
        self.assertEqual(self.receipt()['status'], 'ok')
        self.run_stage()
        self.assertEqual(self.calls, 2)

    def test_retry_budget_survives_next_request(self):
        self.dispatch.side_effect = server.ImageSubmissionRejected('worker unavailable')
        first = self.run_stage()
        self.assertFalse(first['results'][1]['ok'])
        self.assertEqual(self.dispatch.call_count, 2)
        second = self.run_stage()
        self.assertFalse(second['results'][1]['ok'])
        self.assertEqual(self.dispatch.call_count, 2)
        self.assertIn('已自动重试', second['results'][1]['error'])

    def test_explicit_off_does_not_resubmit(self):
        value = self.run_stage(retry=False)
        self.assertFalse(value['results'][1]['ok'])
        self.assertEqual(self.calls, 1)

    def test_severe_failures_never_trigger_another_purchase(self):
        for message in ['HTTP 401 invalid API key', '余额不足', 'content policy violation', '实名认证未通过', 'HTTP 422 invalid parameter', 'quota exhausted']:
            with self.subTest(message=message):
                import shutil
                shutil.rmtree(self.folder / 'image-jobs', ignore_errors=True)
                self.dispatch.reset_mock()
                self.dispatch.side_effect = server.ImageSubmissionRejected(message)
                value = self.run_stage(retry=True)
                self.assertFalse(value['results'][1]['ok'])
                self.assertEqual(self.dispatch.call_count, 1)

    def test_lost_submit_response_is_never_purchased_again(self):
        self.dispatch.side_effect = TimeoutError('lost response')
        self.assertFalse(self.run_stage(retry=True)['results'][1]['ok'])
        self.assertFalse(self.run_stage(retry=True)['results'][1]['ok'])
        self.assertEqual(self.dispatch.call_count, 1)
        self.assertEqual(self.receipt()['status'], 'unknown')

    def test_durable_claim_failure_never_submits_replacement(self):
        import image_auto_retry
        original = task_queue.atomic_json
        def write(path, value):
            if '.auto-retry' in str(path):
                raise OSError('fixture disk full')
            return original(path, value)
        with patch.object(task_queue, 'atomic_json', side_effect=write):
            self.assertFalse(self.run_stage()['results'][1]['ok'])
        self.assertEqual(self.calls, 1)
        self.assertEqual(self.receipt()['status'], 'failed')

    def test_explicit_single_image_retry_still_works_after_auto_budget_exhausted(self):
        import scene_image_recovery
        self.dispatch.side_effect = server.ImageSubmissionRejected('worker unavailable')
        self.run_stage()
        self.assertEqual(self.dispatch.call_count, 2)
        task_queue.atomic_json(self.folder / '04-prompts.json', [{'idx': 2, 'desc_prompt': 'missing'}])
        task_queue.atomic_json(self.folder / 'client_config.json', {'image': {'provider': 'runninghub'}})
        self.dispatch.side_effect = None
        self.dispatch.return_value = {'b64': 'aW1hZ2U='}
        result = scene_image_recovery.retry(server, 'fixture', {'index': 2, 'operation_id': 'explicit-new-operation'})
        self.assertTrue(result['ok'])
        self.assertEqual(self.dispatch.call_count, 3)

    def test_cancel_during_backoff_prevents_replacement_purchase(self):
        cancelled = False
        def pause(_):
            nonlocal cancelled
            cancelled = True
        def checkpoint():
            if cancelled:
                raise RuntimeError('fixture paused')
        with patch('time.sleep', side_effect=pause):
            value = task_queue.dispatch(server, '/api/step4_generate_images', {
                'task_id': 'fixture', 'prompts': [{'idx': 2, 'desc_prompt': 'missing'}]}, 'fixture', checkpoint=checkpoint)
        self.assertFalse(value['results'][0]['ok'])
        self.assertEqual(self.calls, 1)
        self.assertEqual(self.receipt()['status'], 'failed')
        # Restart after a claimed-but-unsubmitted retry cannot blindly resend.
        self.assertFalse(self.run_stage()['results'][1]['ok'])
        self.assertEqual(self.calls, 1)

    def test_progress_exposes_only_scene_and_retry_status(self):
        import image_auto_retry
        task_queue.atomic_json(self.folder / 'image-jobs/.auto-retry/2.json', {'attempts': 1, 'status': 'claimed', 'previous': {'prompt': 'private fixture', 'taskId': 'private-id'}})
        self.assertEqual(image_auto_retry.progress(self.folder), [{'index': 2, 'attempts': 1, 'status': 'claimed'}])

    def test_timeout_queries_original_and_reuses_success_without_purchase(self):
        self.query.return_value = {'status': 'SUCCESS', 'results': [{'url': 'https://fixture.invalid/already-paid.png'}]}
        def submit(cfg, prompt, **kwargs):
            kwargs['on_task_id']('original-paid', cfg)
            raise TimeoutError('poll timed out')
        self.dispatch.side_effect = submit
        value = self.run_stage()
        self.assertTrue(value['results'][1]['ok'], value)
        self.dispatch.assert_called_once()
        self.assertEqual(self.query.call_args.args[2], 'original-paid')

    def test_pending_and_unknown_query_status_never_resubmit(self):
        for status in ['RUNNING', 'UNKNOWN']:
            self.query.return_value = {'status': status}
            self.dispatch.reset_mock()
            self.dispatch.side_effect = self.generate
            self.calls = 0
            value = self.run_stage(retry=True)
            self.assertFalse(value['results'][1]['ok'])
            self.assertEqual(self.dispatch.call_count, 1 if status == 'RUNNING' else 0)

    def test_supplier_moderation_reason_prevents_retry_after_generic_failure(self):
        self.query.return_value = {'status': 'FAILED', 'failReason': 'content policy violation'}
        value = self.run_stage(retry=True)
        self.assertFalse(value['results'][1]['ok'])
        self.assertEqual(self.calls, 1)

    def test_download_failure_reuses_paid_result(self):
        self.dispatch.side_effect = None
        self.dispatch.return_value = {'b64': 'aW1hZ2U='}
        self.save.side_effect = [TimeoutError('download timeout'), '/covers/result.png']
        self.save_image()
        value = self.run_stage(retry=True)
        self.assertTrue(value['results'][1]['ok'], value)
        self.dispatch.assert_called_once()

    def test_synchronous_timeout_also_has_durable_unknown_receipt(self):
        self.settings = {'image': {'provider': 'gpt_image', 'api_key': 'fixture-key', 'base_url': 'https://fixture.invalid'}}
        server.load_settings.return_value = self.settings
        self.dispatch.side_effect = TimeoutError('lost synchronous response')
        self.run_stage(retry=True)
        self.run_stage(retry=True)
        self.dispatch.assert_called_once()
        self.assertEqual(self.receipt()['status'], 'unknown')


if __name__ == '__main__':
    unittest.main()
