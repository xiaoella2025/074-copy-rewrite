"""Resume FIFO acceptance with temporary state and fake executors only."""
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from task_queue import TaskQueue


class Resume1250Tests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.backend = SimpleNamespace(DATA_DIR=Path(self.temporary.name),
            TASK_OPERATION_LOCK=threading.RLock(), TASK_OPERATIONS=set(),
            _prepare_task_rerun=Mock(), get_task_detail=lambda tid: {'info': {'task_id': tid}, 'steps': {}})
        self.queue = TaskQueue(self.backend, executor=lambda job, queue: None)
        self.addCleanup(self.queue.stop)
        for tid in ('failed', 'batch_current', 'batch_next', 'ordinary_next'):
            folder = self.backend.DATA_DIR / 'tasks' / tid
            folder.mkdir(parents=True)
            (folder / 'client_config.json').write_text(json.dumps({'generate': {}, 'tts': {}, 'image': {}}), 'utf-8')

    def failed(self, hold=False, stage='images'):
        self.queue.enqueue('failed')
        job = self.queue._find('failed')
        job.update(status='failed', stage=stage, failure_hold=hold)
        return job

    def test_failed_resume_joins_tail_while_other_batch_is_running(self):
        self.failed()
        batch = self.queue.enqueue_batch(['batch_current', 'batch_next'])
        self.queue._find('batch_current')['status'] = 'running'
        self.backend.TASK_OPERATIONS.add('batch_current')
        resumed = self.queue.enqueue('failed')
        self.assertEqual(resumed['status'], 'queued')
        self.assertEqual([j['task_id'] for j in self.queue.jobs], ['batch_current', 'batch_next', 'failed'])
        self.assertEqual(resumed['position'], 2)
        self.assertEqual(self.queue.enqueue('failed')['id'], resumed['id'])
        self.assertEqual(self.queue.batch(batch['id'])['status'], 'running')

    def test_running_batch_with_queued_jobs_still_keeps_retry_at_tail(self):
        self.failed()
        self.queue.enqueue_batch(['batch_current', 'batch_next'])
        self.queue.enqueue('failed')
        self.assertEqual([j['task_id'] for j in self.queue.jobs], ['batch_current', 'batch_next', 'failed'])

    def test_retry_runs_after_existing_batch_members_and_survives_reload(self):
        self.failed()
        self.queue.enqueue_batch(['batch_current', 'batch_next'])
        self.queue.enqueue('failed')
        calls = []
        restored = TaskQueue(self.backend, executor=lambda job, queue: calls.append(job['task_id']))
        self.addCleanup(restored.stop)
        for _ in range(3): self.assertTrue(restored.run_next())
        self.assertEqual(calls, ['batch_current', 'batch_next', 'failed'])
        self.assertFalse(restored.run_next())

    def test_standalone_failure_hold_resume_keeps_priority_over_ordinary_queue(self):
        self.failed(hold=True)
        self.queue.enqueue('ordinary_next')
        self.assertFalse(self.queue.run_next())
        resumed = self.queue.enqueue('failed')
        self.assertEqual(resumed['position'], 1)
        self.assertEqual([j['task_id'] for j in self.queue.jobs], ['failed', 'ordinary_next'])
        self.backend._prepare_task_rerun.assert_not_called()

    def test_another_task_operation_does_not_globally_reject_resume(self):
        self.failed()
        self.queue.enqueue('ordinary_next')
        self.backend.TASK_OPERATIONS.add('another_local_operation')
        self.assertEqual(self.queue.enqueue('failed')['position'], 2)
        self.backend.TASK_OPERATIONS.add('failed')
        self.queue._find('failed')['status'] = 'failed'
        with self.assertRaises(ValueError):
            self.queue.enqueue('failed')

    def test_cover_failure_hold_still_blocks_following_task_without_explicit_resume(self):
        self.failed(hold=True, stage='cover')
        self.queue.enqueue_batch(['batch_current', 'batch_next'])
        self.assertFalse(self.queue.run_next())
        self.assertEqual(self.queue.get('batch_current')['status'], 'queued')
        self.assertEqual(self.queue.get('failed')['status'], 'failed')
        self.backend._prepare_task_rerun.assert_not_called()

    def test_paused_manual_position_and_approval_are_preserved(self):
        self.queue.enqueue('ordinary_next')
        self.queue.enqueue('failed')
        self.queue._find('failed').update(status='paused', manual_pause=True, approved_stages=['generate'])
        self.queue.enqueue_batch(['batch_current', 'batch_next'])
        resumed = self.queue.enqueue('failed')
        self.assertEqual([j['task_id'] for j in self.queue.jobs], ['ordinary_next', 'failed', 'batch_current', 'batch_next'])
        self.assertEqual(resumed['approved_stages'], ['generate'])


if __name__ == '__main__': unittest.main()
