"""双人播客：step2_split script_format=podcast + /api/step5_tts mode=podcast。"""

import json
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
import uuid
from http.client import HTTPConnection
from pathlib import Path

import server as s


def _synth_mp3(path: Path, length_seconds: float = 1.0):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise unittest.SkipTest("ffmpeg 不在 PATH")
    subprocess.run([ffmpeg, "-y", "-f", "lavfi",
                    "-i", f"sine=frequency=440:duration={length_seconds}",
                    "-ar", "22050", "-ac", "1", "-b:a", "64k", str(path)],
                   capture_output=True, check=True, timeout=15)


class Step5PodcastEndpointTests(unittest.TestCase):
    """端到端验证 /api/step5_tts mode=podcast：缺 API key 拒绝、podcast.mp3 合并、字幕加 speaker 前缀。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        tmp_path = Path(cls.tmp.name)
        cls.orig_data = s.DATA_DIR
        cls.orig_settings = s.SETTINGS_PATH
        s.DATA_DIR = tmp_path / "data"
        s.SETTINGS_PATH = s.DATA_DIR / "settings.json"
        s.DATA_DIR.mkdir()
        s.SETTINGS_PATH.write_text(json.dumps({
            "tts": {
                "provider": "volcengine",
                "volcengine": {"api_key": "test-key", "speaker": "voiceA"},
                "podcast": {"speaker_a": "voiceA", "speaker_b": "voiceB"},
            },
        }), encoding="utf-8")
        # 替换 _volc_tts_synthesize 以走测试音频
        cls.orig_synth = s._volc_tts_synthesize
        counter = {"n": 0}

        def fake_synth(api_key, text, speaker, idx, speed=1.0):
            counter["n"] += 1
            ffmpeg = shutil.which("ffmpeg")
            if not ffmpeg:
                return {"ok": False, "error": "ffmpeg 缺失"}
            tmp = Path(tempfile.gettempdir()) / f"podcast_test_{counter['n']}.mp3"
            _synth_mp3(tmp, 1.0)
            data = tmp.read_bytes()
            tmp.unlink(missing_ok=True)
            return {"ok": True, "audio_bytes": data, "duration": 1.0}
        s._volc_tts_synthesize = fake_synth
        cls.counter = counter

        cls.port = 18840 + (uuid.getnode() % 100)
        ready = threading.Event()
        class _W(s.ThreadingHTTPServer):
            def server_bind(self):
                super().server_bind()
                ready.set()
        cls.srv = _W(("127.0.0.1", cls.port), s.Handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        ready.wait(timeout=3)
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.srv.server_close()
        s._volc_tts_synthesize = cls.orig_synth
        s.DATA_DIR = cls.orig_data; s.SETTINGS_PATH = cls.orig_settings
        cls.tmp.cleanup()

    def _post(self, path: str, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        conn = HTTPConnection("127.0.0.1", self.port, timeout=30)
        conn.request("POST", path, body=body,
                     headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp.status, json.loads(data.decode("utf-8")) if data else {}

    def test_podcast_missing_api_key_returns_400(self):
        s.SETTINGS_PATH.write_text(json.dumps({"tts": {"volcengine": {}}}),
                                    encoding="utf-8")
        status, body = self._post("/api/step5_tts", {
            "task_id": "t_podcast_nokey",
            "mode": "podcast",
            "segments": [{"idx": 1, "text": "你好", "speaker": "A"}],
        })
        self.assertEqual(status, 400)
        self.assertIn("火山", body.get("error", ""))
        # 还原 settings
        s.SETTINGS_PATH.write_text(json.dumps({
            "tts": {"provider": "volcengine",
                    "volcengine": {"api_key": "test-key", "speaker": "voiceA"},
                    "podcast": {"speaker_a": "voiceA", "speaker_b": "voiceB"}},
        }), encoding="utf-8")

    def test_podcast_concat_mp3_and_write_metadata(self):
        status, body = self._post("/api/step5_tts", {
            "task_id": "t_podcast_ok",
            "mode": "podcast",
            "segments": [
                {"idx": 1, "text": "你好，欢迎收听", "speaker": "A"},
                {"idx": 2, "text": "今天我们聊一聊 AI", "speaker": "B"},
                {"idx": 3, "text": "没错", "speaker": "A"},
            ],
        })
        self.assertEqual(status, 200, body)
        self.assertEqual(body["mode"], "podcast")
        self.assertEqual(body["speakers"]["A"], "voiceA")
        self.assertEqual(body["speakers"]["B"], "voiceB")
        self.assertEqual(body["ok_count"], 3)
        self.assertEqual(body["total"], 3)
        # 落盘 05-podcast.json
        task_dir = s.DATA_DIR / "tasks" / "t_podcast_ok"
        meta = json.loads((task_dir / "05-podcast.json").read_text(encoding="utf-8"))
        self.assertEqual(len(meta["rounds"]), 3)
        self.assertEqual(meta["rounds"][0]["speaker"], "A")
        self.assertEqual(meta["rounds"][1]["speaker"], "B")
        self.assertEqual(meta["speakers"]["A"], "voiceA")
        # podcast.mp3 必须存在且非空
        self.assertTrue(Path(body["podcast_path"]).exists())
        self.assertGreater(Path(body["podcast_path"]).stat().st_size, 0)
        # 05-tts-segments.json 里每段也带 speaker
        segs = json.loads((task_dir / "05-tts-segments.json").read_text(encoding="utf-8"))
        self.assertEqual([seg["speaker"] for seg in segs], ["A", "B", "A"])

    def test_podcast_request_overrides_settings_speakers(self):
        """请求体 podcast.speaker_a/speaker_b 优先于 settings。"""
        status, body = self._post("/api/step5_tts", {
            "task_id": "t_podcast_override",
            "mode": "podcast",
            "podcast": {"speaker_a": "overrideA", "speaker_b": "overrideB"},
            "segments": [
                {"idx": 1, "text": "A 说话", "speaker": "A"},
                {"idx": 2, "text": "B 说话", "speaker": "B"},
            ],
        })
        self.assertEqual(status, 200, body)
        self.assertEqual(body["speakers"]["A"], "overrideA")
        self.assertEqual(body["speakers"]["B"], "overrideB")


class Step2PodcastScriptFormatTests(unittest.TestCase):
    """step2_split 在 script_format=podcast 时切到 podcast_dialogue prompt，并打 speaker。"""

    def test_step2_narrator_default_does_not_set_speaker(self):
        # 没 LLM 凭据时走兜底：按段落 + 标点切
        result = s.step2_split({}, "第一句。第二句。\n第三句！第四句？",
                                target_shots=4, script_format="narrator")
        shots = result["shots"]
        self.assertGreater(len(shots), 0)
        for sh in shots:
            self.assertNotIn("speaker", sh)

    def test_step2_podcast_fallback_assigns_alternating_speakers(self):
        # 没 LLM 凭据走兜底，但仍按 i % 2 分配 A/B
        result = s.step2_split({}, "第一句。第二句。\n第三句！第四句？",
                                target_shots=4, script_format="podcast")
        shots = result["shots"]
        self.assertGreater(len(shots), 0)
        speakers = [sh["speaker"] for sh in shots]
        # 至少出现 A 和 B（4 段及以上时）
        self.assertIn("A", speakers)
        self.assertIn("B", speakers)
        # 相邻不应全相同
        self.assertNotEqual(speakers[0], speakers[1])


class Step6PodcastSubtitleTests(unittest.TestCase):
    """step6 字幕加 speaker 前缀 + extra.podcast_path。"""

    def test_subtitle_prefixes_speaker(self):
        # 直接构造 step6 的 subtitle_segments 切片（用本地 HTTP，避免依赖 settings）
        with tempfile.TemporaryDirectory() as tmp:
            tmp_p = Path(tmp)
            draft_root = tmp_p / "drafts"; draft_root.mkdir()
            orig_data = s.DATA_DIR
            orig_set = s.SETTINGS_PATH
            s.DATA_DIR = tmp_p / "data"; (s.DATA_DIR / "tasks").mkdir(parents=True)
            s.SETTINGS_PATH = s.DATA_DIR / "settings.json"
            s.SETTINGS_PATH.write_text(json.dumps({
                "jianying": {"draft_path": str(draft_root)},
            }), encoding="utf-8")
            try:
                port = 18850 + (uuid.getnode() % 100)
                ready = threading.Event()
                class _W(s.ThreadingHTTPServer):
                    def server_bind(self):
                        super().server_bind(); ready.set()
                srv = _W(("127.0.0.1", port), s.Handler)
                threading.Thread(target=srv.serve_forever, daemon=True).start()
                ready.wait(timeout=3)
                time.sleep(0.1)
                try:
                    body = json.dumps({
                        "task_id": "t_step6_podcast",
                        "title": "测试",
                        "shots": [
                            {"idx": 1, "text": "你好", "speaker": "A"},
                            {"idx": 2, "text": "今天聊 AI", "speaker": "B"},
                        ],
                        "images": [{"idx": 1, "url": "/api/task_image/x/1.png"},
                                   {"idx": 2, "url": "/api/task_image/x/2.png"}],
                        "segments": [{"idx": 1, "path": "/a/1.mp3", "duration": 2.0,
                                      "url": "/api/audio/x/seg_001.mp3"},
                                     {"idx": 2, "path": "/a/2.mp3", "duration": 2.0,
                                      "url": "/api/audio/x/seg_002.mp3"}],
                        "podcast_path": "/tmp/podcast.mp3",
                        "ratio": "9:16",
                    }).encode("utf-8")
                    conn = HTTPConnection("127.0.0.1", port, timeout=10)
                    conn.request("POST", "/api/step6_jianying_draft", body=body,
                                 headers={"Content-Type": "application/json"})
                    resp = conn.getresponse()
                    data = resp.read()
                    conn.close()
                    self.assertEqual(resp.status, 200, data.decode("utf-8"))
                    # 解析草稿验证字幕加前缀 + extra.podcast_path
                    draft_files = list(draft_root.glob("**/draft_content.json"))
                    self.assertGreater(len(draft_files), 0)
                    draft = json.loads(draft_files[0].read_text(encoding="utf-8"))
                    extra = draft.get("extra", {})
                    self.assertEqual(extra.get("podcast_path"), "/tmp/podcast.mp3")
                    subs = []
                    for track in draft["tracks"]:
                        if track["type"] == "text":
                            subs.extend(track["segments"])
                    texts = [seg["content"] for seg in subs]
                    self.assertIn("A：你好", texts)
                    self.assertIn("B：今天聊 AI", texts)
                finally:
                    srv.shutdown(); srv.server_close()
            finally:
                s.DATA_DIR = orig_data; s.SETTINGS_PATH = orig_set


if __name__ == "__main__":
    unittest.main()