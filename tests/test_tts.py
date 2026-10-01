import json
import unittest
from unittest.mock import patch

import server


class TtsSettingsTests(unittest.TestCase):
    def setUp(self):
        self.base = {
            "provider": "openai", "protocol": "openai", "base_url": "https://example.test",
            "model": "test-model", "api_key": "llm-secret",
            "tts": {"volcengine": {}, "minimax": {}, "aura": {}},
        }

    def test_volc_key_and_aura_settings_are_saved(self):
        with patch.object(server, "load_settings", return_value=self.base):
            result = server._merged({
                "tts_volc_key": "volc-secret", "tts_provider": "aura",
                "tts_aura_key": "aura-secret", "tts_aura_model": "minimax-speech-2.8-turbo",
                "tts_aura_voice": "voice_test",
                "tts_aura_custom_voices": [{"name": "我的音色", "id": "voice_test"}],
            })
        self.assertEqual(result["tts"]["volcengine"]["api_key"], "volc-secret")
        self.assertEqual(result["tts"]["aura"]["api_key"], "aura-secret")
        self.assertEqual(result["tts"]["aura"]["voice_id"], "voice_test")
        self.assertEqual(result["tts"]["aura"]["custom_voices"][0]["id"], "voice_test")

    def test_tts_can_be_configured_before_llm(self):
        with patch.object(server, "load_settings", return_value={}):
            result = server._merged({"tts_provider": "aura", "tts_aura_key": "fake-key"})
        self.assertEqual(result["tts"]["aura"]["api_key"], "fake-key")

    def test_public_settings_does_not_return_secret_keys(self):
        cfg = {**self.base, "tts": {
            "volcengine": {"api_key": "volc-secret", "speaker": "speaker"},
            "minimax": {"api_key": "minimax-secret", "model": "model"},
            "aura": {"api_key": "aura-secret", "model": "model", "voice_id": "voice", "custom_voices": []},
        }, "jimeng": {"session_id": "jimeng-secret", "ak": "jimeng-ak-secret", "sk": "jimeng-sk-secret"},
            "runninghub": {"api_key": "rh-secret"},
            "custom_image": {"api_key": "custom-secret"},
            "modelscope": {"tokens": ["ms-secret"]}}
        with patch.object(server, "load_settings", return_value=cfg):
            result = server.public_settings()
        dumped = json.dumps(result)
        for secret in ("volc-secret", "minimax-secret", "aura-secret", "llm-secret",
                       "jimeng-secret", "jimeng-ak-secret", "jimeng-sk-secret", "rh-secret",
                       "custom-secret", "ms-secret"):
            self.assertNotIn(secret, dumped)
        self.assertTrue(result["tts"]["aura_configured"])


class AuraAdapterTests(unittest.TestCase):
    def test_audio_url_response_is_downloaded(self):
        class Response:
            status = 200

            def __init__(self, body):
                self.body = body

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return self.body

        calls = []

        def fake_urlopen(request, timeout):
            calls.append(request.full_url if hasattr(request, "full_url") else request)
            return Response(b'{"audio":"https://example.test/signed-audio.mp3"}' if len(calls) == 1 else b"ID3-url")

        with patch.object(server.urllib.request, "urlopen", side_effect=fake_urlopen):
            result = server._aura_tts_synthesize("fake-token", "测试", "voice_test", 1)
        self.assertEqual(result["audio_bytes"], b"ID3-url")
        self.assertEqual(calls[1], "https://example.test/signed-audio.mp3")

    def test_request_and_hex_audio_response(self):
        class Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b'{"audio":"494433"}'

        captured = {}

        def fake_urlopen(request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return Response()

        with patch.object(server.urllib.request, "urlopen", side_effect=fake_urlopen):
            result = server._aura_tts_synthesize("fake-token", "测试", "voice_test", 1, 1.15,
                                                 {"model": "minimax-speech-2.8-turbo"})
        req = captured["request"]
        body = json.loads(req.data)
        self.assertEqual(req.full_url, "https://tts.aurastd.com/api/v1/tts")
        self.assertEqual(req.get_header("Authorization"), "Bearer fake-token")
        self.assertEqual(body["voice_setting"]["voice_id"], "voice_test")
        self.assertEqual(body["voice_setting"]["speed"], 1.15)
        self.assertEqual(result["audio_bytes"], b"ID3")

    def test_audio_duration_uses_ffprobe_when_available(self):
        completed = type("Completed", (), {"returncode": 0, "stdout": "3.42\n"})()
        with patch.object(server.shutil, "which", return_value="ffprobe"), \
             patch.object(server.subprocess, "run", return_value=completed):
            self.assertEqual(server.probe_audio_duration("audio.mp3"), 3.42)


if __name__ == "__main__":
    unittest.main()
