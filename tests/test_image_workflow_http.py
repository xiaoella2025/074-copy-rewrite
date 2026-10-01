import base64
import http.client
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import server


class ImageWorkflowHttpTests(unittest.TestCase):
    def test_complete_route_sequence_writes_one_task_and_draft_without_external_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            draft_root = root / "drafts"
            draft_root.mkdir()
            config = {
                "provider": "openai", "protocol": "openai", "base_url": "https://example.test",
                "model": "fake", "api_key": "fake",
                "tts": {"provider": "aura", "aura": {"api_key": "fake", "model": "fake", "voice_id": "fake"}},
                "image": {"provider": "gpt_image", "base_url": "https://example.test",
                          "api_key": "fake", "model": "fake"},
                "jianying": {"draft_path": str(draft_root)},
            }
            (root / "settings.json").write_text(json.dumps(config), encoding="utf-8")
            patches = [
                patch.object(server, "DATA_DIR", root),
                patch.object(server, "SETTINGS_PATH", root / "settings.json"),
                patch.object(server, "PROFILES_PATH", root / "profiles.json"),
                patch.object(server, "step0_pre_review", return_value={"passed": True}),
                patch.object(server, "call_llm", return_value="改写稿"),
                patch.object(server, "step1_meta", return_value={"title": "标题"}),
                patch.object(server, "step2_split", return_value={"shots": [{"idx": 1, "text": "第一镜"}]}),
                patch.object(server, "step3_image_prompts", return_value=[{"idx": 1, "desc_prompt": "画面"}]),
                patch.object(server, "_aura_tts_synthesize", return_value={
                    "idx": 1, "ok": True, "text": "第一镜", "audio_bytes": b"ID3"}),
                patch.object(server, "probe_audio_duration", return_value=2.0),
                patch.object(server, "image_dispatcher", return_value={
                    "b64": base64.b64encode(b"fake-image").decode("ascii"), "mime": "image/png"}),
            ]
            for p in patches:
                p.start()
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
            worker = threading.Thread(target=httpd.serve_forever, daemon=True)
            worker.start()

            def post(path, body):
                conn = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=5)
                conn.request("POST", path, json.dumps(body).encode("utf-8"),
                             {"Content-Type": "application/json"})
                response = conn.getresponse()
                payload = json.loads(response.read().decode("utf-8"))
                conn.close()
                self.assertEqual(response.status, 200, payload)
                return payload

            try:
                first = post("/api/generate", {"reference": "原文", "line": "story", "level": "standard",
                                                "run_steps": ["0", "1", "meta", "2"]})
                task_id = first["task_id"]
                shots = first["steps"]["2"]["shots"]
                speech = post("/api/step5_tts", {"task_id": task_id, "provider": "aura",
                                                    "segments": shots})
                prompts = post("/api/generate", {"task_id": task_id, "rewritten": "改写稿",
                                                  "shots": shots, "meta": first["steps"]["meta"],
                                                  "run_steps": ["3"]})["steps"]["3"]
                images = post("/api/step4_generate_images", {"task_id": task_id,
                                                             "provider": "gpt_image", "prompts": prompts})
                draft = post("/api/step6_jianying_draft", {"task_id": task_id, "title": "标题",
                                                              "shots": shots, "images": images["results"],
                                                              "segments": speech["results"]})
                self.assertTrue(Path(draft["draft_dir"]).exists())
                self.assertEqual(len(server.load_tasks()["tasks"]), 1)
                self.assertIn(0, server.get_task_detail(task_id)["info"]["completed_steps"])
                self.assertEqual(speech["results"][0]["duration_source"], "ffprobe")
                cover = post("/api/cover", {"prompt": "自己修改的封面提示词", "provider": "gpt_image"})
                self.assertEqual(cover["prompt"], "自己修改的封面提示词")
                upload = post("/api/cover_upload", {"task_id": task_id,
                    "data_url": "data:image/png;base64," + base64.b64encode(b"fake-image").decode("ascii")})
                self.assertTrue(upload["url"].startswith("/covers/"))
                self.assertEqual(server.get_task_detail(task_id)["steps"]["cover"]["url"], upload["url"])
            finally:
                httpd.shutdown()
                httpd.server_close()
                worker.join(timeout=5)
                for p in reversed(patches):
                    p.stop()
