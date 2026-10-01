import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import server


class TaskRecordTests(unittest.TestCase):
    def test_saving_same_task_twice_updates_one_history_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(server, "DATA_DIR", Path(directory)):
                server.save_task_record({"id": "task_1", "title": "初稿", "shots_count": 2})
                server.save_task_record({"id": "task_1", "title": "初稿", "shots_count": 3})
                tasks = server.load_tasks()["tasks"]

        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["shots_count"], 3)


if __name__ == "__main__":
    unittest.main()
