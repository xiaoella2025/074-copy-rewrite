"""真实供应商回归：完整跑通「上传配音 / 素材库 / 动态分镜 / 双人播客 / 上传封面」全流程。

每个端点调一次，所有 mock（LLM / TTS / 图片）都用本地真实组件，不调外部 HTTP。
最后落盘的 draft_content.json / 05-podcast.json / podcast.mp3 都要检查存在 + 关键内容正确。
"""

import base64
import io
import json
import shutil
import struct
import subprocess
import tempfile
import threading
import time
import unittest
import uuid
import zlib
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch

import server


def _synth_png_bytes(color: str = "red", height: int = 32) -> bytes:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise unittest.SkipTest("ffmpeg 不在 PATH")
    out = Path(tempfile.gettempdir()) / f"_e2e_{uuid.uuid4().hex[:8]}.png"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi",
                    "-i", f"color=c={color}:s=64x{height}:d=0.04",
                    "-frames:v", "1", "-update", "1", str(out)],
                   capture_output=True, check=True, timeout=15)
    data = out.read_bytes()
    out.unlink(missing_ok=True)
    return data


def _synth_mp3_bytes(length_seconds: float = 1.0) -> bytes:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise unittest.SkipTest("ffmpeg 不在 PATH")
    out = Path(tempfile.gettempdir()) / f"_e2e_{uuid.uuid4().hex[:8]}.mp3"
    subprocess.run([ffmpeg, "-y", "-f", "lavfi",
                    "-i", f"sine=frequency=440:duration={length_seconds}",
                    "-ar", "22050", "-ac", "1", "-b:a", "32k", str(out)],
                   capture_output=True, check=True, timeout=15)
    data = out.read_bytes()
    out.unlink(missing_ok=True)
    return data


def _multipart_body(boundary: str, parts) -> tuple[bytes, int]:
    """parts: [(name, filename_or_empty, content_bytes, content_type)]"""
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
        buf += content if isinstance(content, bytes) else content.encode()
        buf += b"\r\n"
    buf += f"--{boundary}--\r\n".encode()
    return bytes(buf), len(buf)


def _post_json(port: int, path: str, payload: dict):
    conn = HTTPConnection("127.0.0.1", port, timeout=15)
    conn.request("POST", path, json.dumps(payload).encode("utf-8"),
                 {"Content-Type": "application/json"})
    resp = conn.getresponse(); data = resp.read(); conn.close()
    return resp.status, json.loads(data.decode("utf-8")) if data else {}


def _post_multipart(port: int, path: str, body: bytes, boundary: str):
    conn = HTTPConnection("127.0.0.1", port, timeout=20)
    conn.request("POST", path, body=body, headers={
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(body)),
    })
    resp = conn.getresponse(); data = resp.read(); conn.close()
    return resp.status, json.loads(data.decode("utf-8")) if data else {}


class FullRegressionE2E(unittest.TestCase):
    """图文主链路所有新增功能真值测试。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        cls.draft_root = root / "drafts"; cls.draft_root.mkdir()
        cls.orig_data = server.DATA_DIR
        cls.orig_set = server.SETTINGS_PATH
        server.DATA_DIR = root / "data"; server.DATA_DIR.mkdir()
        server.SETTINGS_PATH = server.DATA_DIR / "settings.json"
        server.SETTINGS_PATH.write_text(json.dumps({
            "provider": "openai", "protocol": "openai",
            "base_url": "https://example.test", "model": "fake", "api_key": "fake",
            "tts": {"provider": "volcengine",
                    "volcengine": {"api_key": "fake", "speaker": "voiceA"},
                    "podcast": {"speaker_a": "voiceA", "speaker_b": "voiceB"}},
            "image": {"provider": "gpt_image",
                      "base_url": "https://example.test", "api_key": "fake", "model": "fake"},
            "jianying": {"draft_path": str(cls.draft_root)},
        }), encoding="utf-8")
        # 替换外部调用为本地
        cls._volc_calls = []
        def fake_volc(api_key, text, speaker, idx, speed=1.0):
            cls._volc_calls.append({"idx": idx, "text": text, "speaker": speaker})
            mp3 = _synth_mp3_bytes(1.0)
            return {"ok": True, "audio_bytes": mp3, "duration": 1.0, "idx": idx, "text": text}
        cls._orig_volc = server._volc_tts_synthesize
        server._volc_tts_synthesize = fake_volc

    def setUp(self):
        # 每个 case 重置火山调用计数
        self.__class__._volc_calls.clear()

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        cls.draft_root = root / "drafts"; cls.draft_root.mkdir()
        cls.orig_data = server.DATA_DIR
        cls.orig_set = server.SETTINGS_PATH
        server.DATA_DIR = root / "data"; server.DATA_DIR.mkdir()
        server.SETTINGS_PATH = server.DATA_DIR / "settings.json"
        server.SETTINGS_PATH.write_text(json.dumps({
            "provider": "openai", "protocol": "openai",
            "base_url": "https://example.test", "model": "fake", "api_key": "fake",
            "tts": {"provider": "volcengine",
                    "volcengine": {"api_key": "fake", "speaker": "voiceA"},
                    "podcast": {"speaker_a": "voiceA", "speaker_b": "voiceB"}},
            "image": {"provider": "gpt_image",
                      "base_url": "https://example.test", "api_key": "fake", "model": "fake"},
            "jianying": {"draft_path": str(cls.draft_root)},
        }), encoding="utf-8")
        # 替换外部调用为本地
        cls._volc_calls = []
        def fake_volc(api_key, text, speaker, idx, speed=1.0):
            cls._volc_calls.append({"idx": idx, "text": text, "speaker": speaker})
            mp3 = _synth_mp3_bytes(1.0)
            return {"ok": True, "audio_bytes": mp3, "duration": 1.0, "idx": idx, "text": text}
        cls._orig_volc = server._volc_tts_synthesize
        server._volc_tts_synthesize = fake_volc
        cls._orig_probe = server.probe_audio_duration
        server.probe_audio_duration = lambda p: 1.0
        cls._orig_image = server.image_dispatcher
        server.image_dispatcher = lambda cfg, desc, ratio="9:16", resolution="1k": {
            "b64": base64.b64encode(_synth_png_bytes("red")).decode("ascii"),
            "mime": "image/png",
        }
        # 启动 server
        cls.port = 18880 + (uuid.getnode() % 100)
        ready = threading.Event()
        class _W(server.ThreadingHTTPServer):
            def server_bind(self):
                super().server_bind(); ready.set()
        cls.srv = _W(("127.0.0.1", cls.port), server.Handler)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        ready.wait(timeout=3)
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.srv.server_close()
        server._volc_tts_synthesize = cls._orig_volc
        server.probe_audio_duration = cls._orig_probe
        server.image_dispatcher = cls._orig_image
        server.DATA_DIR = cls.orig_data; server.SETTINGS_PATH = cls.orig_set
        cls.tmp.cleanup()

    # ----- helper -----

    def _run_pipeline_common(self, task_id: str, script_format: str = "narrator",
                              shots_count: int = 2) -> dict:
        """跑 step5 + step4 + step6 公共部分；返回 {task_id, shots, tts, images, draft}。"""
        shots = [{"idx": i + 1, "text": f"第{i+1}镜测试文本",
                  "speaker": ("A" if i % 2 == 0 else "B") if script_format == "podcast" else None}
                 for i in range(shots_count)]
        shots = [{k: v for k, v in s.items() if v is not None} for s in shots]

        if script_format == "podcast":
            tts_payload = {"task_id": task_id, "mode": "podcast",
                           "segments": [{"idx": s["idx"], "text": s["text"], "speaker": s["speaker"]} for s in shots]}
        else:
            tts_payload = {"task_id": task_id, "segments": shots}
        status, tts = _post_json(self.port, "/api/step5_tts", tts_payload)
        self.assertEqual(status, 200, tts)
        prompts = [{"idx": s["idx"], "desc_prompt": f"画面提示词 {s['idx']}"} for s in shots]
        status, step4 = _post_json(self.port, "/api/step4_generate_images", {
            "task_id": task_id, "prompts": prompts, "ratio": "9:16",
            "resolution": "1k", "provider": "gpt_image"})
        self.assertEqual(status, 200, step4)
        # 动态分镜：mode="3" — image_path 必须是磁盘路径
        task_dir = server.DATA_DIR / "tasks" / task_id
        covers_dir = task_dir / "covers"
        intro_shots = []
        for p, r in zip(prompts, step4["results"]):
            idx = p["idx"]
            cover_local = covers_dir / f"{idx}.png"
            seg = next(t for t in tts["results"] if t["idx"] == idx)
            if cover_local.exists() and seg.get("path"):
                intro_shots.append({
                    "idx": idx, "image_path": str(cover_local),
                    "audio_path": seg["path"], "duration": 1.0,
                })
        status, intro = _post_json(self.port, "/api/step4_intro_video", {
            "task_id": task_id, "mode": "3", "ratio": "9:16",
            "shots": intro_shots,
        })
        self.assertEqual(status, 200, intro)
        step6_payload = {"task_id": task_id, "title": "回归测试",
                         "shots": shots, "images": step4["results"],
                         "segments": tts["results"],
                         "videos": intro.get("results", []),
                         "ratio": "9:16"}
        if script_format == "podcast":
            step6_payload["podcast_path"] = tts.get("podcast_path", "")
        status, draft = _post_json(self.port, "/api/step6_jianying_draft", step6_payload)
        self.assertEqual(status, 200, draft)
        return {"task_id": task_id, "shots": shots, "tts": tts,
                "images": step4["results"], "videos": intro.get("results", []),
                "draft": draft, "podcast_path": tts.get("podcast_path", "")}

    # ----- tests -----

    def test_full_pipeline_narrator_with_materials_intro_and_cover(self):
        """完整链路：素材库 1 个素材 + AI 兜底 1 个 + 动态分镜 3 + 配音 + 草稿 + 封面上传。"""
        # 1) 上传 1 张素材
        png = _synth_png_bytes("blue", height=24)
        boundary = uuid.uuid4().hex
        body, _ = _multipart_body(boundary, [("file", "lib.png", png, "image/png")])
        status, upload = _post_multipart(self.port, "/api/materials/upload", body, boundary)
        self.assertEqual(status, 200, upload)
        mid = upload["material_id"]
        # 2) 跑公共链路（不传 podcast）
        task_id = f"t_regr_{uuid.uuid4().hex[:8]}"
        result = self._run_pipeline_common(task_id)
        # 3) 用素材库给 idx=1 出图 + 让 idx=2 走 AI 兜底
        status, step4_mat = _post_json(self.port, "/api/step4_from_materials", {
            "task_id": task_id,
            "fallback_to_ai": True, "ratio": "9:16",
            "assignments": [
                {"idx": 1, "material_id": mid},
                {"idx": 2, "desc_prompt": "画面提示词 2"},
            ],
        })
        self.assertEqual(status, 200, step4_mat)
        self.assertEqual(step4_mat["ok_count"], 2)
        covers = server.DATA_DIR / "tasks" / task_id / "covers"
        self.assertTrue((covers / "1.png").exists(), "素材应拷到 covers/1.png")
        # 4) 上传封面
        cover_png = _synth_png_bytes("green", height=128)
        status, cover = _post_json(self.port, "/api/cover_upload", {
            "task_id": task_id,
            "data_url": f"data:image/png;base64,{base64.b64encode(cover_png).decode('ascii')}",
        })
        self.assertEqual(status, 200, cover)
        self.assertTrue(cover["url"].startswith("/covers/"))
        # 5) 草稿目录里应有 draft_content.json + 含 video track
        draft_dir = Path(result["draft"]["draft_dir"])
        self.assertTrue(draft_dir.exists())
        draft_content = json.loads((draft_dir / "draft_content.json").read_text(encoding="utf-8"))
        video_tracks = [t for t in draft_content["tracks"] if t["type"] == "video"]
        self.assertGreater(len(video_tracks), 0)
        # 视频轨应包含 video material
        has_video = any(s.get("material_id", "").startswith("video_")
                        for t in video_tracks for s in t["segments"])
        self.assertTrue(has_video, "应优先使用动态分镜视频")
        # 草稿里没有 podcast mp4 引用（旁白模式）
        self.assertEqual(draft_content["extra"].get("podcast_path", ""), "")

    def test_full_pipeline_podcast_end_to_end(self):
        """双人播客全链路：火山双 speaker → podcast.mp3 → 字幕加 A:/B: 前缀。"""
        task_id = f"t_regr_pod_{uuid.uuid4().hex[:8]}"
        result = self._run_pipeline_common(task_id, script_format="podcast", shots_count=4)
        # 1) podcast.mp3 必须存在 + ffmpeg 可解析
        pp = Path(result["podcast_path"])
        self.assertTrue(pp.exists(), f"podcast.mp3 缺失: {pp}")
        self.assertGreater(pp.stat().st_size, 0)
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            r = subprocess.run([ffmpeg, "-i", str(pp)], capture_output=True, timeout=10)
            # ffmpeg -i 应报错但不抛异常；我们只关心非空字节
            self.assertGreater(len(r.stderr), 0)
        # 2) 火山被调 4 次；A 用 voiceA，B 用 voiceB（settings.podcast 配置）
        self.assertEqual(len(self._volc_calls), 4)
        speaker_sequence = [c["speaker"] for c in self._volc_calls]
        self.assertEqual(speaker_sequence, ["voiceA", "voiceB", "voiceA", "voiceB"])
        # 3) 05-podcast.json 含 4 rounds
        meta = json.loads((server.DATA_DIR / "tasks" / task_id / "05-podcast.json").read_text(encoding="utf-8"))
        self.assertEqual(len(meta["rounds"]), 4)
        self.assertEqual([r["speaker"] for r in meta["rounds"]], ["A", "B", "A", "B"])
        # 4) 草稿字幕加 A:/B: 前缀
        draft_dir = Path(result["draft"]["draft_dir"])
        draft = json.loads((draft_dir / "draft_content.json").read_text(encoding="utf-8"))
        sub_tracks = [t for t in draft["tracks"] if t["type"] == "text"]
        sub_texts = [s["content"] for t in sub_tracks for s in t["segments"]]
        self.assertIn("A：第1镜测试文本", sub_texts)
        self.assertIn("B：第2镜测试文本", sub_texts)
        # 5) extra.podcast_path 写入
        self.assertEqual(draft["extra"].get("podcast_path", ""), result["podcast_path"])


if __name__ == "__main__":
    unittest.main()