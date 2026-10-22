import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
import task_queue


class StoryQueueAutorunTests(unittest.TestCase):
    def test_idle_submission_and_skip_resume_the_worker_without_another_start_click(self):
        with tempfile.TemporaryDirectory() as directory:
            backend=SimpleNamespace(DATA_DIR=Path(directory),TASK_OPERATION_LOCK=threading.RLock(),
                TASK_OPERATIONS=set(),_prepare_task_rerun=Mock(),get_task_detail=lambda _: {})
            completed=threading.Event();performed=[]
            def execute(job,queue):performed.append(job['task_id']);completed.set()
            q=task_queue.TaskQueue(backend,executor=execute)
            for name in ('first','paused','next'):
                folder=backend.DATA_DIR/'tasks'/name;folder.mkdir(parents=True)
                (folder/'client_config.json').write_text(json.dumps({'generate':{},'tts':{},'image':{}}))
                (folder/'saved.png').write_bytes(b'preserve')
            try:
                q.start();q.enqueue('first');self.assertTrue(completed.wait(3))
                # Wait for the first fake executor to release its queue ownership.
                with backend.TASK_OPERATION_LOCK,q.lock:
                    pass
                completed.clear()
                # Enqueue and pause atomically so the fake worker cannot race the test setup.
                with backend.TASK_OPERATION_LOCK,q.lock:
                    q.enqueue('paused');q.request_pause('paused');q.enqueue('next')
                self.assertFalse(completed.wait(.1))
                q.cancel('paused')
                self.assertTrue(completed.wait(3))
                self.assertEqual(performed,['first','next'])
                self.assertEqual((backend.DATA_DIR/'tasks/paused/saved.png').read_bytes(),b'preserve')
                backend._prepare_task_rerun.assert_not_called()
            finally:q.stop()
