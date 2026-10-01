"""素材库：上传 / 列表 / 静态服务 / 删除 + step4_from_materials。"""

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


def _synth_png_bytes(color: str = "red") -> bytes:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise unittest.SkipTest("ffmpeg 不在 PATH")
    out = Path(tempfile.gettempdir()) / f"_mat_{uuid.uuid4().hex[:8]}.png"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi",
                    "-i", f"color=c={color}:s=64x64:d=0.04",
                    "-frames:v", "1", "-update", "1", str(out)],
                   capture_output=True, check=True, timeout=15)
    data = out.read_bytes()
    out.unlink(missing_ok=True)
    return data


def _multipart(boundary: str, parts: list[tuple[str, str, bytes | None, str | None]]) -> bytes:
    """构造 multipart/form-data body。
    parts: [(name, filename_or_empty, content_bytes_or_None, content_type_or_None)]
    """
    buf = bytearray()
    for name, filename, content, ctype in parts:
        buf += f"--{boundary}\r\n".encode()
        if filename:
            disp = f'form-data; name="{name}"; filename="{filename}"'
        else:
            disp = f'form-data; name="{name}"'
        buf += f"Content-Disposition: {disp}\r\n".encode()
        if ctype:
            buf += f"Content-Type: {ctype}\r\n".encode()
        buf += b"\r\n"
        if content is not None:
            buf += content if isinstance(content, bytes) else content.encode()
        buf += b"\r\n"
    buf += f"--{boundary}--\r\n".encode()
    return bytes(buf)


class MaterialsEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        tmp_path = Path(cls.tmp.name)
        cls.orig_data = s.DATA_DIR
        s.DATA_DIR = tmp_path / "data"
        s.DATA_DIR.mkdir()
        cls.port = 18860 + (uuid.getnode() % 100)
        ready = threading.Event()
        class _W(s.ThreadingHTTPServer):
            def server_bind(self):
                super().server_bind()
                ready.set()
        cls.srv = _W(("127.0.0.1", cls.port), s.Handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        ready.wait(timeout=3)
        time.sleep(1)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.srv.server_close()
        s.DATA_DIR = cls.orig_data
        cls.tmp.cleanup()

    def _post_multipart(self, path: str, boundary: bytes, length: int):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=15)
        conn.request("POST", path, body=b"", headers={
            "Content-Type": f"multipart/form-data; boundary={boundary.decode()}",
            "Content-Length": str(length),
        })
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp.status, json.loads(data.decode("utf-8")) if data else {}

    def _get(self, path: str):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=15)
        conn.request("GET", path)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp.status, json.loads(data.decode("utf-8")) if data else {}, resp

    def test_upload_png_saves_to_materials_dir(self):
        png = _synth_png_bytes("red")
        boundary = uuid.uuid4().hex
        body = _multipart(boundary, [("file", "test.png", png, "image/png")])
        # 自己直接调用 _handle_material_upload 避免 multipart HTTP 序列化复杂
        class FakeReq:
            pass
        # 直接调内部 handler
        class _H(s.Handler):
            def __init__(self): pass
        h = _H()
        h._json = lambda s, p: p
        form, files = {}, {"file": png}
        captured = {}
        def fake_json(status, payload):
            captured["status"] = status
            captured["payload"] = payload
        h._json = fake_json
        before_count = len(list((s.DATA_DIR / "materials").glob("*.json"))) if (s.DATA_DIR / "materials").exists() else 0
        h._handle_material_upload(form, files)
        self.assertEqual(captured["status"], 200)
        self.assertTrue(captured["payload"]["ok"])
        mid = captured["payload"]["material_id"]
        # meta 文件 + 图片文件应存在
        self.assertTrue((s.DATA_DIR / "materials" / f"{mid}.json").exists())
        self.assertTrue((s.DATA_DIR / "materials" / f"{mid}.png").exists())
        # 列表应包含本次上传的素材
        status, body, _ = self._get("/api/materials")
        self.assertEqual(status, 200)
        self.assertEqual(body["count"], before_count + 1)
        self.assertIn(mid, [m["id"] for m in body["materials"]])

    def test_upload_rejects_non_image(self):
        class _H(s.Handler):
            def __init__(self): pass
        h = _H()
        captured = {}
        h._json = lambda s, p: captured.setdefault("v", (s, p))
        with self.assertRaises(ValueError) as cm:
            h._handle_material_upload({}, {"file": b"this is not an image file at all"})
        self.assertIn("PNG", str(cm.exception))

    def test_upload_rejects_missing_file(self):
        class _H(s.Handler):
            def __init__(self): pass
        h = _H()
        with self.assertRaises(ValueError) as cm:
            h._handle_material_upload({}, {})
        self.assertIn("file", str(cm.exception))

    def test_material_static_serve(self):
        png = _synth_png_bytes("green")
        class _H(s.Handler):
            def __init__(self): pass
        h = _H()
        captured = {}
        h._json = lambda s, p: captured.setdefault("v", (s, p))
        h._handle_material_upload({}, {"file": png})
        mid = captured["v"][1]["material_id"]
        # GET /api/material/<file>
        conn = HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request("GET", f"/api/material/{mid}.png")
        resp = conn.getresponse()
        body = resp.read()
        conn.close()
        self.assertEqual(resp.status, 200)
        self.assertGreater(len(body), 0)

    def test_delete_material_removes_files(self):
        png = _synth_png_bytes("blue")
        class _H(s.Handler):
            def __init__(self): pass
        h = _H()
        captured = {}
        h._json = lambda s, p: captured.setdefault("v", (s, p))
        h._handle_material_upload({}, {"file": png})
        mid = captured["v"][1]["material_id"]
        # POST /api/materials/<id>
        status, body, _ = self._post_delete(f"/api/materials/{mid}")
        self.assertEqual(status, 200, body)
        self.assertTrue(body["ok"])
        # 列表应为空
        status, body, _ = self._get("/api/materials")
        self.assertEqual(body["count"], 0)

    def _post_delete(self, path: str):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request("POST", path, body=b"{}", headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp.status, json.loads(data.decode("utf-8")) if data else {}, resp

    def test_delete_invalid_id_returns_400(self):
        status, body, _ = self._post_delete("/api/materials/not-a-uuid")
        self.assertEqual(status, 400)

    def test_delete_nonexistent_material_returns_404(self):
        status, body, _ = self._post_delete("/api/materials/0123456789ab")
        self.assertEqual(status, 404)


class Step4FromMaterialsTests(unittest.TestCase):
    """step4_from_materials：把已上传的素材拷贝到 task_dir/covers/。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        tmp_path = Path(cls.tmp.name)
        cls.orig_data = s.DATA_DIR
        orig_set = s.SETTINGS_PATH
        s.DATA_DIR = tmp_path / "data"
        s.DATA_DIR.mkdir()
        s.SETTINGS_PATH = s.DATA_DIR / "settings.json"
        s.SETTINGS_PATH.write_text("{}", encoding="utf-8")
        cls.port = 18870 + (uuid.getnode() % 100)
        ready = threading.Event()
        class _W(s.ThreadingHTTPServer):
            def server_bind(self):
                super().server_bind(); ready.set()
        cls.srv = _W(("127.0.0.1", cls.port), s.Handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        ready.wait(timeout=3)
        time.sleep(1)
        cls.orig_set = orig_set

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.srv.server_close()
        s.DATA_DIR = cls.orig_data
        s.SETTINGS_PATH = cls.orig_set
        cls.tmp.cleanup()

    def _post_json(self, path, body):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request("POST", path, body=json.dumps(body).encode("utf-8"),
                     headers={"Content-Type": "application/json"})
        resp = conn.getresponse(); data = resp.read(); conn.close()
        return resp.status, json.loads(data.decode("utf-8")) if data else {}

    def _post_multipart_raw(self, path, body, boundary):
        conn = HTTPConnection("127.0.0.1", self.port, timeout=15)
        conn.request("POST", path, body=body, headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
        })
        resp = conn.getresponse(); data = resp.read(); conn.close()
        return resp.status, json.loads(data.decode("utf-8")) if data else {}

    def _upload(self, png_bytes: bytes) -> str:
        boundary = uuid.uuid4().hex
        body = _multipart(boundary, [("file", "test.png", png_bytes, "image/png")])
        status, body = self._post_multipart_raw("/api/materials/upload", body, boundary)
        self.assertEqual(status, 200, body)
        return body["material_id"]

    def test_step4_from_materials_copies_files(self):
        mid = self._upload(_synth_png_bytes("red"))
        status, body = self._post_json("/api/step4_from_materials", {
            "task_id": "t_mat_ok",
            "assignments": [{"idx": 1, "material_id": mid},
                            {"idx": 2, "material_id": mid}],
        })
        self.assertEqual(status, 200, body)
        self.assertEqual(body["ok_count"], 2)
        covers = s.DATA_DIR / "tasks" / "t_mat_ok" / "covers"
        self.assertTrue((covers / "1.png").exists())
        self.assertTrue((covers / "2.png").exists())

    def test_step4_from_materials_missing_material_returns_error(self):
        status, body = self._post_json("/api/step4_from_materials", {
            "task_id": "t_mat_miss",
            "assignments": [{"idx": 1, "material_id": "000000000000"}],
        })
        self.assertEqual(status, 200, body)
        self.assertEqual(body["ok_count"], 0)
        self.assertFalse(body["results"][0].get("ok"))
        self.assertIn("不存在", body["results"][0].get("error", ""))


if __name__ == "__main__":
    unittest.main()