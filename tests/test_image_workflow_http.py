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
    def test_selected_web_source_reaches_rewrite_context(self):
        with patch.object(server, "search_web_summaries", return_value=[
            {"title": "资料标题", "summary": "可核查的摘要", "url": "https://example.org/article"}
        ]) as search:
            results = server.task_knowledge({"sources": ["search"], "keywords": "关键字"})
        search.assert_called_once_with("关键字", limit=5)
        self.assertEqual(results[0]["source"], "全网搜索")
        self.assertIn("可核查的摘要", server.build_context_block({"knowledge_results": results}))

    def test_live_progress_endpoint_reports_current_step_without_credentials(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(server, "DATA_DIR", Path(directory)):
            server.write_generation_progress("sample", "1", "running")
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
            worker = threading.Thread(target=httpd.serve_forever, daemon=True)
            worker.start()
            try:
                conn = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=5)
                conn.request("GET", "/api/task_progress/sample")
                response = conn.getresponse()
                payload = json.loads(response.read().decode("utf-8"))
                self.assertEqual(response.status, 200)
                self.assertEqual((payload["step"], payload["status"]), ("1", "running"))
                conn.close()
            finally:
                httpd.shutdown()
                httpd.server_close()
                worker.join(timeout=5)

    def test_product_reference_upload_is_scoped_to_task(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(server, "DATA_DIR", Path(directory)):
            handler = object.__new__(server.Handler)
            replies = []
            handler._json = lambda status, payload: replies.append((status, payload))
            handler._handle_reference_upload({"task_id": "sample"},
                                             {"file": b"\x89PNG\r\n\x1a\nreference"})
            self.assertEqual(replies[0][0], 200)
            self.assertTrue((Path(directory) / "tasks" / "sample" / "product-reference.png").is_file())
            with self.assertRaises(ValueError):
                handler._handle_reference_upload({"task_id": "../other"}, {"file": b"\xff\xd8bad"})

    def test_bgm_upload_is_scoped_to_task_and_validates_audio(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(server, "DATA_DIR", Path(directory)):
            handler = object.__new__(server.Handler)
            replies = []
            handler._json = lambda status, payload: replies.append((status, payload))
            handler._handle_bgm_upload({"task_id": "sample"}, {"file": b"ID3mock-music"})
            self.assertEqual(replies[0][0], 200)
            self.assertEqual(Path(replies[0][1]["path"]).read_bytes(), b"ID3mock-music")
            with self.assertRaises(ValueError):
                handler._handle_bgm_upload({"task_id": "../other"}, {"file": b"ID3bad"})
            with self.assertRaises(ValueError):
                handler._handle_bgm_upload({"task_id": "sample"}, {"file": b"not music"})

    def test_rewrite_rounds_retry_only_for_length_mismatch(self):
        original = "原" * 300
        with patch.object(server, "call_llm", side_effect=["短", "改" * 290]) as llm:
            text = server.rewrite_with_attempts({"api_key": "fake"}, "system", "user", original, "story", "std")
        self.assertEqual(len(text), 290)
        self.assertEqual(llm.call_count, 2)
        with patch.object(server, "call_llm", return_value="短") as llm:
            server.rewrite_with_attempts({"api_key": "fake"}, "system", "user", original, "story", "fast")
        self.assertEqual(llm.call_count, 1)

    def test_result_page_is_separate_from_new_task_form(self):
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            conn = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=5)
            conn.request("GET", "/result.html?task=example")
            response = conn.getresponse()
            page = response.read().decode("utf-8")
            self.assertEqual(response.status, 200)
            self.assertIn("任务详情", page)
            self.assertIn("/api/task/", page)
            self.assertIn("/assets/workflow_view.js", page)
            conn.close()
        finally:
            httpd.shutdown()
            httpd.server_close()

    def test_cover_prompt_uses_selected_layout_and_subtitle(self):
        with patch.object(server, "call_llm", return_value="cover prompt") as llm:
            prompt = server.build_cover_prompt({}, "主标题", "文案", "写实", [],
                                               "title", "副标题", "emotional")
        self.assertTrue(prompt.startswith('cover prompt'))
        self.assertIn('情绪海报构图法',llm.call_args.args[1])
        self.assertIn('主标题「主标题」',prompt)
        self.assertIn('「副标题」',prompt)
        self.assertNotIn('{{',prompt)

    def test_runninghub_probe_accepts_unsaved_key_without_writing_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings_path = root / "settings.json"
            settings_path.write_text(json.dumps({"runninghub": {"model": "rh-image-g2"}}), encoding="utf-8")
            with patch.object(server, "DATA_DIR", root), patch.object(server, "SETTINGS_PATH", settings_path), \
                 patch.object(server, "_probe_runninghub_key") as probe:
                httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
                worker = threading.Thread(target=httpd.serve_forever, daemon=True)
                worker.start()
                try:
                    conn = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=5)
                    body = {"provider": "runninghub", "api_key": "fake-unsaved-key", "model": "rh-image-x"}
                    conn.request("POST", "/api/test_image", json.dumps(body).encode("utf-8"),
                                 {"Content-Type": "application/json"})
                    response = conn.getresponse()
                    result = json.loads(response.read().decode("utf-8"))
                    conn.close()
                    self.assertEqual(response.status, 200, result)
                    self.assertTrue(result["verified"])
                    self.assertEqual(probe.call_args.args[0]["api_key"], "fake-unsaved-key")
                    self.assertEqual(probe.call_args.args[0]["model"], "rh-image-x")
                    self.assertNotIn("api_key", json.loads(settings_path.read_text(encoding="utf-8"))["runninghub"])
                finally:
                    httpd.shutdown()
                    httpd.server_close()
                    worker.join(timeout=5)

    def test_runninghub_task_uses_key_only_and_saved_resolution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = {"image": {"provider": "runninghub"},
                        "runninghub": {"api_key": "fake", "model": "rh-image-g2",
                                       "ratio": "3:4", "resolution": "2k", "concurrency": 6}}
            settings_path = root / "settings.json"
            settings_path.write_text(json.dumps(settings), encoding="utf-8")
            with patch.object(server, "DATA_DIR", root), patch.object(server, "SETTINGS_PATH", settings_path), \
                 patch.object(server, "image_dispatcher", return_value={
                     "b64": base64.b64encode(b"fake-image").decode("ascii")}) as dispatcher:
                httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
                worker = threading.Thread(target=httpd.serve_forever, daemon=True)
                worker.start()
                try:
                    conn = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=5)
                    body = {"provider": "runninghub", "task_id": "test_rh",
                            "prompts": [{"idx": 1, "desc_prompt": "画面"}]}
                    conn.request("POST", "/api/step4_generate_images", json.dumps(body).encode("utf-8"),
                                 {"Content-Type": "application/json"})
                    response = conn.getresponse()
                    result = json.loads(response.read().decode("utf-8"))
                    conn.close()
                    self.assertEqual(response.status, 200, result)
                    self.assertTrue(result["results"][0]["ok"], result)
                    self.assertEqual(result["concurrency"], 6)
                    self.assertEqual(dispatcher.call_args.kwargs,
                                     {"ratio": "3:4", "resolution": "2k"})
                finally:
                    httpd.shutdown()
                    httpd.server_close()
                    worker.join(timeout=5)

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
                patch.object(server, "export_jianying_draft", side_effect=lambda task, draft, app, options: {
                    "ok":True, "draft_dir":str(draft), "template_id":options["template_id"]}),
                patch.object(server, "DATA_DIR", root),
                patch.object(server, "SETTINGS_PATH", root / "settings.json"),
                patch.object(server, "PROFILES_PATH", root / "profiles.json"),
                patch.object(server, "step0_pre_review", return_value={"passed": True}),
                patch.object(server, "call_llm", return_value="改写稿"),
                patch.object(server, "step1_meta", return_value={"title": "标题", "short_title": "短标题",
                                                                "summary": "发布文案", "tags": ["话题"],
                                                                "comments": ["评论"]}),
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
            mock_image_dispatcher = server.image_dispatcher
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
                                                "task_id": "test_progress", "track_progress": True,
                                                "run_steps": ["0", "1", "meta", "2"],
                                                "publish": {"short_title": False, "summary": True,
                                                            "tags": False, "comments": False}})
                self.assertEqual(first["steps"]["meta"]["short_title"], "")
                self.assertEqual(first["steps"]["meta"]["summary"], "发布文案")
                self.assertEqual(first["steps"]["meta"]["tags"], [])
                self.assertEqual(first["steps"]["meta"]["comments"], [])
                task_id = first["task_id"]
                self.assertEqual(task_id, "test_progress")
                self.assertEqual(json.loads((root / "tasks" / task_id / "progress.json").read_text(encoding="utf-8"))["status"], "complete")
                self.assertTrue((root / "tasks" / task_id / "01-review.json").is_file())
                shots = first["steps"]["2"]["shots"]
                speech = post("/api/step5_tts", {"task_id": task_id, "provider": "aura",
                                                    "segments": shots})
                prompts = post("/api/generate", {"task_id": task_id, "rewritten": "改写稿",
                                                  "shots": shots, "meta": first["steps"]["meta"],
                                                  "run_steps": ["3"]})["steps"]["3"]
                (root / "tasks" / task_id / "product-reference.png").write_bytes(b"\x89PNG\r\n\x1a\nmock")
                images = post("/api/step4_generate_images", {"task_id": task_id,
                                                             "provider": "gpt_image", "prompts": prompts})
                self.assertTrue(mock_image_dispatcher.call_args.kwargs["reference_data_url"].startswith("data:image/png;base64,"))
                draft = post("/api/step6_jianying_draft", {"task_id": task_id, "title": "标题",
                                                              "template_id": "builtin-portrait-4-3", "ratio": "4:3",
                                                              "shots": shots, "images": images["results"],
                                                              "segments": speech["results"]})
                self.assertTrue(Path(draft["draft_dir"]).exists())
                self.assertEqual(draft["template_id"], "builtin-portrait-4-3")
                self.assertEqual(server.export_jianying_draft.call_args.args[0], root / "tasks" / task_id)
                self.assertEqual(len(server.load_tasks()["tasks"]), 1)
                self.assertIn(0, server.get_task_detail(task_id)["info"]["completed_steps"])
                self.assertEqual(speech["results"][0]["duration_source"], "ffprobe")
                cover = post("/api/cover", {"prompt": "自己修改的封面提示词", "provider": "gpt_image",
                                              "ratio": "3:4"})
                self.assertEqual(cover["prompt"], "自己修改的封面提示词")
                self.assertEqual(mock_image_dispatcher.call_args.kwargs["ratio"], "3:4")
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
