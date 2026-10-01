"""Profile writes must preserve saved secrets behind the public masked view."""

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch

import server


class ProfileSaveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name) / "data"
        self.data.mkdir()
        self.profiles_path = self.data / "profiles.json"
        self.profiles_patch = patch.object(server, "PROFILES_PATH", self.profiles_path)
        self.data_patch = patch.object(server, "DATA_DIR", self.data)
        self.profiles_patch.start()
        self.data_patch.start()
        self.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        self.worker = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.worker.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.worker.join(timeout=2)
        self.data_patch.stop()
        self.profiles_patch.stop()
        self.tmp.cleanup()

    def request(self, method, path, payload=None):
        body = json.dumps(payload).encode() if payload is not None else None
        conn = HTTPConnection("127.0.0.1", self.httpd.server_port, timeout=5)
        conn.request(method, path, body, {"Content-Type": "application/json"})
        response = conn.getresponse()
        result = response.status, json.loads(response.read())
        conn.close()
        return result

    def seed(self):
        server.save_profiles([{
            "id": "p1", "name": "旧名称", "provider": "custom", "protocol": "openai",
            "baseUrl": "https://example.invalid", "model": "m1", "models": ["m1", "m2"],
            "fallback": ["m2"], "proxyUrl": "", "apiKey": "sk-original-123456",
            "enabled": True,
        }])

    def test_edit_without_retyping_key_keeps_secret_and_custom_models(self):
        self.seed()
        status, public = self.request("GET", "/api/profiles")
        self.assertEqual(status, 200)
        profile = public["profiles"][0]
        self.assertTrue(profile["has_key"])
        self.assertEqual(profile["models"], ["m1", "m2"])
        self.assertNotIn("sk-original-123456", json.dumps(public))
        profile["name"] = "新名称"
        status, result = self.request("POST", "/api/profiles", {"profiles": [profile]})
        self.assertEqual(status, 200)
        self.assertEqual(server.load_profiles()[0]["apiKey"], "sk-original-123456")
        self.assertEqual(server.load_profiles()[0]["name"], "新名称")
        self.assertNotIn("sk-original-123456", json.dumps(result))

    def test_retype_replaces_key_and_clear_is_explicit(self):
        self.seed()
        _, public = self.request("GET", "/api/profiles")
        profile = public["profiles"][0]
        profile["apiKey"] = "sk-replacement-654321"
        status, _ = self.request("POST", "/api/profiles", {"profiles": [profile]})
        self.assertEqual(status, 200)
        self.assertEqual(server.load_profiles()[0]["apiKey"], "sk-replacement-654321")
        profile["enabled"] = False
        profile["apiKey"] = ""
        status, _ = self.request("POST", "/api/profiles", {"profiles": [profile]})
        self.assertEqual(status, 200)
        self.assertEqual(server.load_profiles()[0]["apiKey"], "")
        self.assertFalse(self.request("GET", "/api/profiles")[1]["profiles"][0]["has_key"])

    def test_missing_key_preserves_it_but_forged_mask_is_rejected(self):
        self.seed()
        _, public = self.request("GET", "/api/profiles")
        profile = public["profiles"][0]
        del profile["apiKey"]
        status, _ = self.request("POST", "/api/profiles", {"profiles": [profile]})
        self.assertEqual(status, 200)
        self.assertEqual(server.load_profiles()[0]["apiKey"], "sk-original-123456")
        profile["apiKey"] = "sk-fake••••••••tail"
        status, _ = self.request("POST", "/api/profiles", {"profiles": [profile]})
        self.assertEqual(status, 400)
        self.assertEqual(server.load_profiles()[0]["apiKey"], "sk-original-123456")

    def test_old_mask_accidentally_saved_is_not_treated_as_usable_key(self):
        self.seed()
        profiles = server.load_profiles()
        profiles[0]["apiKey"] = "sk-o••••••••3456"
        server.save_profiles(profiles)
        self.assertFalse(self.request("GET", "/api/profiles")[1]["profiles"][0]["has_key"])
        self.assertEqual(server.resolve_active_llm_settings()["api_key"], "")

    def test_connection_check_uses_saved_key_when_input_is_blank(self):
        self.seed()
        payload = {"profile_id": "p1", "provider": "custom", "protocol": "openai",
                   "base_url": "https://other.invalid", "model": "m1", "api_key": ""}
        with patch.object(server, "call_llm", return_value="测试成功") as call:
            status, result = self.request("POST", "/api/test_llm", payload)
        self.assertEqual(status, 200)
        self.assertTrue(result["ok"])
        self.assertEqual(call.call_args.args[0]["api_key"], "sk-original-123456")
        self.assertEqual(call.call_args.args[0]["base_url"], "https://example.invalid")
        self.assertNotIn("sk-original-123456", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
