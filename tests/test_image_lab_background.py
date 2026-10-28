import json
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import image_lab
import image_lab_jobs


class BackgroundTests(unittest.TestCase):
    def test_receipt_survives_client_leaving_and_repeat_submit_runs_once(self):
        with tempfile.TemporaryDirectory() as directory:
            entered = threading.Event()
            release = threading.Event()
            def dispatch(*args, **kwargs):
                kwargs['on_task_id']('remote-123', {'api_key': 'never-store'})
                entered.set()
                self.assertTrue(release.wait(5))
                return {'b64': 'offline'}
            backend = SimpleNamespace(DATA_DIR=Path(directory), load_settings=lambda: {},
                resolve_image_config=lambda *_: {'provider': 'modelscope', 'api_key': 'fake'},
                story_workflow_reference=lambda: {'styles': []},
                image_job_options=lambda *_: ('9:16', '1k'),
                image_job_concurrency=lambda *_: 1,
                image_dispatcher=Mock(side_effect=dispatch), save_cover_image=lambda *_: '/covers/isolated.png')
            request = {'background': True, 'request_id': 'a'*32, 'prompt': '离开后继续', 'ratios': ['9:16']}
            try:
                receipt = image_lab.generate(backend, request)
                self.assertTrue(receipt['accepted'])
                self.assertTrue(entered.wait(3))
                rows = image_lab.history(directory)
                self.assertEqual(next(x for x in rows if x.get('upstream_task_id'))['upstream_task_id'], 'remote-123')
                self.assertTrue(any(x.get('kind') == 'lab-job' and x['status'] == 'running' for x in rows))
                self.assertEqual(image_lab.generate(backend, request), receipt)
                with self.assertRaises(ValueError):
                    image_lab.generate(backend, {**request, 'prompt': '不同内容'})
            finally:
                release.set()
            jobpath = Path(directory)/'image-lab-jobs'/('a'*32+'.json')
            for _ in range(200):
                if json.loads(jobpath.read_text('utf8'))['status'] == 'complete': break
                time.sleep(.01)
            self.assertEqual(json.loads(jobpath.read_text('utf8'))['status'], 'complete')
            rows = image_lab.history(directory)
            self.assertEqual(len(rows), 1)
            self.assertTrue(rows[0]['ok'])
            self.assertEqual(rows[0]['url'], '/covers/isolated.png')
            image_lab.generate(backend, request)
            backend.image_dispatcher.assert_called_once()
            self.assertNotIn('never-store', ''.join(p.read_text('utf8') for p in Path(directory).rglob('*.json')))

    def test_restart_retains_unknown_receipt_without_resubmission(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'image-lab-jobs'/('b'*32+'.json')
            image_lab_jobs.write(path, dict(id='b'*32, status='running', instance='old-process', fingerprint='x', createdAt=1))
            before = path.read_bytes()
            self.assertEqual(image_lab_jobs.receipts(directory)[0]['status'], 'interrupted')
            self.assertEqual(path.read_bytes(), before)

    def test_planning_error_has_durable_visible_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            image_lab.generate(SimpleNamespace(DATA_DIR=Path(directory)),
                {'background': True, 'request_id': 'c'*32, 'prompt': 'test', 'mode': 'invalid'})
            for _ in range(200):
                rows = image_lab.history(directory)
                if rows and rows[0]['status'] == 'failed': break
                time.sleep(.01)
            self.assertEqual(rows[0]['status'], 'failed')
            self.assertIn('未知实验室模式', rows[0]['error'])


if __name__ == '__main__': unittest.main()
