import http.client
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import server


class AsrSettingsTests(unittest.TestCase):
    def test_cloud_reuses_tts_key_and_needs_no_app_id(self):
        settings = {"asr": {"provider": "volcengine"},
                    "tts": {"volcengine": {"api_key": "fake-key"}}}
        with patch.object(server, "load_settings", return_value=settings):
            public = server.public_settings()["asr"]
        self.assertTrue(public["configured"])
        self.assertNotIn("fake-key", json.dumps(public))
        with patch.object(server, "_volc_asr_transcribe", return_value=[]) as transcribe:
            server.transcribe_with_selected_asr(settings, Path("fake.mp3"))
        self.assertEqual(transcribe.call_args.args[0], "fake-key")

    def test_local_model_status_requires_files_and_runtime(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(server, "DATA_DIR", Path(folder)):
            model_dir = server.asr_model_dir()
            model_dir.mkdir(parents=True)
            for name in server.ASR_MODEL_FILES:
                (model_dir / name).write_bytes(b"model")
            with patch.object(server.importlib.util, "find_spec", return_value=None):
                status = server.asr_public_status({"asr": {"provider": "local"}})
            self.assertTrue(status["local_model_present"])
            self.assertFalse(status["configured"])

    def test_asr_provider_persists_through_settings_http(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            settings_path = root / "settings.json"
            settings_path.write_text(json.dumps({
                "tts": {"volcengine": {"api_key": "fake-key"}},
                "asr": {"provider": "local"},
            }), encoding="utf-8")
            with patch.object(server, "DATA_DIR", root), patch.object(server, "SETTINGS_PATH", settings_path):
                httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
                worker = threading.Thread(target=httpd.serve_forever, daemon=True)
                worker.start()
                try:
                    conn = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=5)
                    conn.request("POST", "/api/settings", b'{"asr_provider":"volcengine"}',
                                 {"Content-Type": "application/json"})
                    response = conn.getresponse()
                    body = json.loads(response.read())
                    conn.close()
                    self.assertEqual(response.status, 200, body)
                    self.assertEqual(body["settings"]["asr"]["provider"], "volcengine")
                    self.assertTrue(body["settings"]["asr"]["configured"])
                    self.assertEqual(json.loads(settings_path.read_text(encoding="utf-8"))["asr"]["provider"], "volcengine")
                finally:
                    httpd.shutdown()
                    httpd.server_close()
                    worker.join(timeout=5)

    def test_aura_tts_uses_selected_cloud_asr(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            settings_path = root / "settings.json"
            settings_path.write_text(json.dumps({
                "tts": {"provider": "aura", "aura": {"api_key": "fake-aura"},
                        "volcengine": {"api_key": "fake-volc"}},
                "asr": {"provider": "volcengine"},
            }), encoding="utf-8")
            with patch.object(server, "DATA_DIR", root), patch.object(server, "SETTINGS_PATH", settings_path), \
                 patch.object(server, "_aura_tts_synthesize", return_value={
                     "idx": 1, "ok": True, "text": "测试", "audio_bytes": b"ID3"}), \
                 patch.object(server, "probe_audio_duration", return_value=2.0), \
                 patch.object(server, "transcribe_with_selected_asr", return_value=[
                     {"text": "测试", "start": 0.0, "end": 1.8}]) as transcribe:
                httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
                worker = threading.Thread(target=httpd.serve_forever, daemon=True)
                worker.start()
                try:
                    conn = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=5)
                    conn.request("POST", "/api/step5_tts", json.dumps({
                        "provider": "aura", "task_id": "asr_test", "segments": [{"idx": 1, "text": "测试"}]
                    }).encode("utf-8"), {"Content-Type": "application/json"})
                    response = conn.getresponse()
                    body = json.loads(response.read())
                    conn.close()
                    self.assertEqual(response.status, 200, body)
                    self.assertTrue(transcribe.called)
                    self.assertEqual(body["results"][0]["duration_source"], "volc_asr")
                finally:
                    httpd.shutdown()
                    httpd.server_close()
                    worker.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
