"""Real image stage, controlled local suppliers; never contact a paid service."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import server
import task_queue


class ImageProgressTests(unittest.TestCase):
    def test_priority_stops_waiting_on_the_old_remote_image_and_runs_the_selected_task(self):
        import queue_order
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            cfg = {'generate': {}, 'tts': {}, 'image': {}}
            for tid in ('old', 'selected'):
                folder = root / 'tasks' / tid
                folder.mkdir(parents=True)
                (folder / 'client_config.json').write_text(json.dumps(cfg), 'utf8')
            backend = SimpleNamespace(DATA_DIR=root, TASK_OPERATION_LOCK=threading.RLock(), TASK_OPERATIONS=set())
            entered, release = threading.Event(), threading.Event()
            performed = []
            def http(url, headers, body, **kwargs):
                if url.endswith('/query'):
                    entered.set()
                    if not release.wait(5): raise RuntimeError('fixture timeout')
                    return 200, '{"status":"RUNNING"}'
                return 200, '{"taskId":"already-paid-fixture","status":"RUNNING"}'
            def execute(job, queue):
                if job['task_id'] == 'old':
                    task_queue.dispatch(server, '/api/step4_generate_images', {
                        'task_id': 'old', 'retry': False, 'prompts': [{'idx': 1, 'desc_prompt': 'fixture'}]},
                        'old', checkpoint=lambda: queue.checkpoint(job))
                    queue.checkpoint(job)
                performed.append(job['task_id'])
            q = task_queue.TaskQueue(backend, executor=execute)
            self.addCleanup(q.stop)
            settings = {'image': {'provider': 'runninghub'}, 'runninghub': {'api_key': 'fixture'}}
            with patch.object(server, 'DATA_DIR', root), patch.object(server, 'load_settings', return_value=settings), \
                 patch.object(server, '_http_post_json', side_effect=http) as requests, patch('time.sleep'):
                q.enqueue('old'); q.enqueue('selected')
                worker = threading.Thread(target=q.run_next)
                worker.start()
                try:
                    self.assertTrue(entered.wait(3))
                    queue_order.control(q, {'task_id': 'selected', 'action': 'first'})
                finally:
                    release.set(); worker.join(5)
                self.assertFalse(worker.is_alive())
                self.assertEqual(q.get('old')['status'], 'paused')
                self.assertTrue(q.run_next())
                self.assertEqual(performed, ['selected'])
                self.assertEqual(sum(not c.args[0].endswith('/query') for c in requests.call_args_list), 1)
                receipt = json.loads((root / 'tasks/old/image-jobs/1.json').read_text('utf8'))
                self.assertEqual(receipt['taskId'], 'already-paid-fixture')
                self.assertEqual(receipt['status'], 'pending')

    def test_two_workers_are_visible_and_each_result_appears_before_batch_finishes(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            folder = root / 'tasks/fixture'
            folder.mkdir(parents=True)
            gates = [threading.Event() for _ in range(3)]
            entered = [threading.Event() for _ in range(3)]
            result = []
            def generate(cfg, prompt, **kwargs):
                i = int(prompt) - 1
                entered[i].set()
                self.assertTrue(gates[i].wait(5))
                return {'b64': prompt, 'mime': 'image/png'}
            def save(value, *_):
                path = root / 'covers' / (value + '.png')
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(b'local fixture image')
                return '/covers/' + path.name
            def detail():
                return server.get_task_detail('fixture')['steps']
            settings = {'image': {'provider': 'gpt_image', 'api_key': 'fixture', 'base_url': 'http://fixture.invalid'}}
            with patch.object(server, 'DATA_DIR', root), patch.object(server, 'load_settings', return_value=settings), \
                 patch.object(server, 'image_dispatcher', side_effect=generate), patch.object(server, 'save_cover_image', side_effect=save):
                worker = threading.Thread(target=lambda: result.append(task_queue.dispatch(server, '/api/step4_generate_images', {
                    'task_id': 'fixture', 'concurrency': 2, 'retry': False,
                    'prompts': [{'idx': i, 'desc_prompt': str(i)} for i in (1, 2, 3)]}, 'fixture')))
                worker.start()
                try:
                    self.assertTrue(all(e.wait(3) for e in entered[:2]))
                    self.assertEqual(detail().get('image_generating'), [1, 2])
                    self.assertFalse(entered[2].is_set())
                    gates[0].set()
                    self.assertTrue(entered[2].wait(3))
                    self.assertIn('1.png', [x['name'] for x in detail().get('images', [])])
                    self.assertIn(2, detail()['image_generating'])
                    self.assertNotIn(1, detail()['image_generating'])
                finally:
                    for gate in gates: gate.set()
                    worker.join(5)
                self.assertEqual(detail().get('image_generating'), [])
                self.assertTrue(all(x['ok'] for x in result[0]['results']))

    def test_pause_after_remote_id_stops_polling_without_resubmitting_or_losing_receipt(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            paused = threading.Event()
            def checkpoint():
                if paused.is_set(): raise InterruptedError('fixture paused')
            def http(url, headers, body, **kwargs):
                if url.endswith('/query'):
                    self.fail('A paused task must not continue polling')
                paused.set()
                return 200, json.dumps({'taskId': 'original-fixture-id', 'status': 'RUNNING'})
            import image_generation_progress
            with patch.object(server, '_http_post_json', side_effect=http):
                with self.assertRaises(InterruptedError):
                    image_generation_progress.run(folder, 1, checkpoint,
                        server.batch_image_result, {'provider': 'runninghub', 'api_key': 'fixture'},
                        'private prompt', 1, '9:16', '1k', folder)
            receipt = json.loads((folder / 'image-jobs/1.json').read_text('utf8'))
            self.assertEqual(receipt['taskId'], 'original-fixture-id')
            self.assertEqual(receipt['status'], 'pending')
            self.assertEqual(image_generation_progress.active(folder), [])
            paused.clear()
            import task_cover
            cfg = {'provider': 'runninghub', 'api_key': 'fixture'}
            with patch.object(server, 'load_settings', return_value={'runninghub': cfg}), \
                 patch.object(task_cover, 'query_provider', side_effect=[{'status': 'RUNNING'},
                     {'status': 'SUCCESS', 'results': [{'url': 'https://fixture.invalid/already-paid.png'}]}]) as query, \
                 patch.object(server, 'image_dispatcher', side_effect=AssertionError('must not resubmit')), patch('time.sleep'):
                result = image_generation_progress.run(folder, 1, checkpoint, server.batch_image_result,
                    cfg, 'private prompt', 1, '9:16', '1k', folder)
            self.assertEqual(result['url'], 'https://fixture.invalid/already-paid.png')
            self.assertEqual(query.call_count, 2)
            self.assertTrue(all(c.args[2] == 'original-fixture-id' for c in query.call_args_list))
