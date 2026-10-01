"""人工编辑和单镜重画创建可续跑版本，原任务保持完整。"""

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path

import server


class TaskRevisionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_data = server.DATA_DIR
        server.DATA_DIR = Path(self.tmp.name) / "data"
        self.source = server.DATA_DIR / "tasks" / "task_original"
        (self.source / "covers").mkdir(parents=True)
        (self.source / "audio").mkdir()
        (self.source / "02-rewrite.txt").write_text("原改写稿", encoding="utf-8")
        (self.source / "02-meta.json").write_text('{"title":"标题"}', encoding="utf-8")
        (self.source / "03-shots.json").write_text(
            json.dumps([{"idx": 1, "text": "第一镜"}, {"idx": 2, "text": "第二镜"}]), encoding="utf-8")
        (self.source / "04-prompts.json").write_text(
            json.dumps([{"idx": 1, "desc_prompt": "画一"}, {"idx": 2, "desc_prompt": "画二"}]), encoding="utf-8")
        (self.source / "covers" / "1.png").write_bytes(b"image-one")
        (self.source / "covers" / "2.png").write_bytes(b"image-two")
        for idx in (1, 2):
            (self.source / "audio" / f"seg_{idx:03d}.mp3").write_bytes(b"mp3")
        (self.source / "05-tts-segments.json").write_text(json.dumps([
            {"index": idx, "path": str(self.source / "audio" / f"seg_{idx:03d}.mp3"),
             "duration": 1.0, "text": f"第{idx}镜"} for idx in (1, 2)
        ]), encoding="utf-8")
        (self.source / "06-draft-meta.json").write_text('{"draft_dir":"old"}', encoding="utf-8")

    def tearDown(self):
        server.DATA_DIR = self.old_data
        self.tmp.cleanup()

    def test_redraw_fork_reuses_other_image_and_audio_without_old_draft(self):
        new_id = server.fork_task_for_edit("task_original", "redraw", 2)
        target = server.DATA_DIR / "tasks" / new_id
        self.assertEqual((target / "covers" / "1.png").read_bytes(), b"image-one")
        self.assertFalse((target / "covers" / "2.png").exists())
        self.assertFalse((target / "06-draft-meta.json").exists())
        segments = json.loads((target / "05-tts-segments.json").read_text(encoding="utf-8"))
        self.assertEqual(segments[0]["path"], str(target / "audio" / "seg_001.mp3"))
        self.assertTrue((self.source / "covers" / "2.png").exists())
        self.assertTrue((self.source / "06-draft-meta.json").exists())

    def test_rewrite_fork_drops_stale_downstream_products(self):
        new_id = server.fork_task_for_edit("task_original", "rewrite", "人工修订稿")
        target = server.DATA_DIR / "tasks" / new_id
        self.assertEqual((target / "02-rewrite.txt").read_text(encoding="utf-8"), "人工修订稿")
        self.assertFalse((target / "03-shots.json").exists())
        self.assertFalse((target / "audio").exists())
        self.assertEqual((self.source / "02-rewrite.txt").read_text(encoding="utf-8"), "原改写稿")

    def test_bad_id_or_empty_edit_is_rejected(self):
        with self.assertRaises(ValueError):
            server.fork_task_for_edit("../outside", "redraw", 1)
        with self.assertRaises(ValueError):
            server.fork_task_for_edit("task_original", "rewrite", "  ")

    def test_resume_url_with_query_serves_editor(self):
        httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        worker = threading.Thread(target=httpd.serve_forever, daemon=True)
        worker.start()
        try:
            conn = HTTPConnection("127.0.0.1", httpd.server_port, timeout=5)
            conn.request("GET", "/index.html?resume=task_original")
            response = conn.getresponse()
            body = response.read()
            conn.close()
            self.assertEqual(response.status, 200)
            self.assertIn(b"runImagePipeline", body)
        finally:
            httpd.shutdown()
            httpd.server_close()
            worker.join(timeout=2)

    def test_media_urls_resolve_and_cannot_read_settings(self):
        (self.source / "audio" / "seg_001.mp3").write_bytes(b"audio-one")
        (self.source / "videos").mkdir()
        (self.source / "videos" / "seg_001.mp4").write_bytes(b"video-one")
        (server.DATA_DIR / "settings.json").write_bytes(b"test-secret")
        (server.DATA_DIR / "covers").mkdir()
        (server.DATA_DIR / "covers" / "cover_test.png").write_bytes(b"cover")
        httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        worker = threading.Thread(target=httpd.serve_forever, daemon=True)
        worker.start()
        try:
            cases = {
                "/api/task_image/task_original/1.png": (200, b"image-one"),
                "/api/audio/task_original/seg_001.mp3": (200, b"audio-one"),
                "/api/task_video/task_original/seg_001.mp4": (200, b"video-one"),
                "/covers/cover_test.png": (200, b"cover"),
                "/covers/../settings.json": (404, None),
                "/tasks/../settings.json": (404, None),
                "/api/task_image/task_original/../../settings.json": (404, None),
                "/assets/../README.md": (404, None),
            }
            for path, (wanted_status, wanted_body) in cases.items():
                with self.subTest(path=path):
                    conn = HTTPConnection("127.0.0.1", httpd.server_port, timeout=5)
                    conn.request("GET", path)
                    response = conn.getresponse()
                    body = response.read()
                    conn.close()
                    self.assertEqual(response.status, wanted_status)
                    if wanted_body is not None:
                        self.assertEqual(body, wanted_body)
                    self.assertNotIn(b"test-secret", body)
        finally:
            httpd.shutdown()
            httpd.server_close()
            worker.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
