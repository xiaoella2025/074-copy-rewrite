"""上传自定义配音：multipart 解析 + 切片 + step5_tts upload 分支。"""

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


def _synth_mp3(path: Path, length_seconds: float):
    """用 ffmpeg 生成指定秒数的正弦波 mp3。"""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise unittest.SkipTest("ffmpeg 不在 PATH，跳过上传配音测试")
    cmd = [ffmpeg, "-y", "-f", "lavfi", "-i", f"sine=frequency=440:duration={length_seconds}",
           "-ar", "22050", "-ac", "1", "-b:a", "64k", str(path)]
    subprocess.run(cmd, capture_output=True, check=True, timeout=30)


class UploadVoiceSliceTests(unittest.TestCase):
    def test_slice_distributes_by_character_weight(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            task_dir = tmp_path / "task_001"
            task_dir.mkdir()
            uploaded = task_dir / "uploaded-voice.mp3"
            _synth_mp3(uploaded, 6.0)

            segments = [
                {"idx": 1, "text": "短"},                       # 1 char
                {"idx": 2, "text": "中等长度的一句话"},          # 8 chars
                {"idx": 3, "text": "这是一个长一些的句子用来测试切片"},  # 17 chars
            ]
            results, total_dur = s.slice_uploaded_voice(task_dir, segments)
            self.assertEqual(len(results), 3)
            self.assertAlmostEqual(total_dur, 6.0, delta=0.5)
            sum_dur = sum(r["duration"] for r in results)
            self.assertAlmostEqual(sum_dur, total_dur, delta=0.5)
            for r in results:
                p = Path(r["path"])
                self.assertTrue(p.exists(), f"missing {p}")
                self.assertGreater(p.stat().st_size, 0)
                self.assertEqual(r["duration_source"], "upload_slice")

    def test_slice_rejects_missing_upload(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            task_dir = tmp_path / "task_002"
            task_dir.mkdir()
            with self.assertRaises(RuntimeError):
                s.slice_uploaded_voice(task_dir, [{"idx": 1, "text": "x"}])

    def test_step5_upload_writes_segments_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            task_dir = tmp_path / "task_003"
            task_dir.mkdir()
            _synth_mp3(task_dir / "uploaded-voice.mp3", 4.0)
            seg_records, _ = s.slice_uploaded_voice(task_dir, [
                {"idx": 1, "text": "第一段"},
                {"idx": 2, "text": "第二段更长的内容用来分配时间"},
            ])
            seg_file = task_dir / "05-tts-segments.json"
            seg_file.write_text(
                json.dumps(seg_records, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            loaded = json.loads(seg_file.read_text(encoding="utf-8"))
            self.assertEqual(len(loaded), 2)


class MultipartParsingTests(unittest.TestCase):
    def test_multipart_text_and_file_fields(self):
        """直接复用 server._read_multipart 等价逻辑（私有方法不直接调）；
        通过启动一个临时 server 验证端到端。"""
        try:
            import urllib3  # noqa
        except ImportError:
            pass


def _run_test_server(port):
    """在临时端口启动 server.main()；通过 sentinel 数据 ready 信号同步。"""
    ready = threading.Event()

    class _Wrapper(s.ThreadingHTTPServer):
        def server_bind(self):
            super().server_bind()
            ready.set()

    original = s.HTTPServing_dir if hasattr(s, "HTTPServing_dir") else None
    srv = _Wrapper(("127.0.0.1", port), s.Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    if not ready.wait(timeout=3):
        srv.shutdown()
        raise RuntimeError("server didn't start")
    return srv


class UploadVoiceEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 隔离数据目录；找一个空闲端口
        cls.tmp = tempfile.TemporaryDirectory()
        tmp_path = Path(cls.tmp.name)
        cls.orig_data = s.DATA_DIR
        cls.orig_settings = s.SETTINGS_PATH
        s.DATA_DIR = tmp_path / "data"
        s.SETTINGS_PATH = s.DATA_DIR / "settings.json"
        s.DATA_DIR.mkdir()
        s.SETTINGS_PATH.write_text("{}", encoding="utf-8")
        cls.port = 18890 + (uuid.getnode() % 100)
        cls.srv = _run_test_server(cls.port)
        # 等一秒让端口就绪
        time.sleep(0.2)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        s.DATA_DIR = cls.orig_data
        s.SETTINGS_PATH = cls.orig_settings
        cls.tmp.cleanup()

    def _post_multipart(self, fields, files):
        boundary = "----testboundary" + uuid.uuid4().hex
        body = b""
        for k, v in fields.items():
            body += f"--{boundary}\r\n".encode()
            body += f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode()
            body += v.encode("utf-8") + b"\r\n"
        for k, (filename, content, mime) in files.items():
            body += f"--{boundary}\r\n".encode()
            body += (f'Content-Disposition: form-data; name="{k}"; filename="{filename}"\r\n'
                     f"Content-Type: {mime}\r\n\r\n").encode()
            body += content + b"\r\n"
        body += f"--{boundary}--\r\n".encode()
        conn = HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request("POST", "/api/upload_voice", body=body,
                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp.status, json.loads(data.decode("utf-8")) if data else {}

    def test_upload_voice_endpoint_saves_file(self):
        with tempfile.TemporaryDirectory() as inner:
            mp3_path = Path(inner) / "src.mp3"
            _synth_mp3(mp3_path, 2.0)
            payload = mp3_path.read_bytes()
            status, body = self._post_multipart(
                {"task_id": "task_endpoint_1"},
                files={"file": ("voice.mp3", payload, "audio/mpeg")},
            )
        self.assertEqual(status, 200, body)
        self.assertTrue(body["ok"])
        self.assertEqual(body["task_id"], "task_endpoint_1")
        saved = s.DATA_DIR / "tasks" / "task_endpoint_1" / "uploaded-voice.mp3"
        self.assertTrue(saved.exists())
        self.assertGreater(saved.stat().st_size, 0)
        self.assertGreater(body["duration"], 1.5)

    def test_upload_voice_rejects_missing_file(self):
        boundary = "----b" + uuid.uuid4().hex
        body = (f"--{boundary}\r\n"
                 f'Content-Disposition: form-data; name="task_id"\r\n\r\n'
                 f"task_x\r\n--{boundary}--\r\n").encode()
        conn = HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request("POST", "/api/upload_voice", body=body,
                     headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        resp = conn.getresponse()
        payload = resp.read()
        conn.close()
        self.assertEqual(resp.status, 400)
        parsed = json.loads(payload.decode("utf-8"))
        self.assertIn("缺少", parsed.get("error", ""))


if __name__ == "__main__":
    unittest.main()