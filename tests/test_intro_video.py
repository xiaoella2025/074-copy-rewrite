"""动态分镜：make_intro_video + /api/step4_intro_video 端点。"""

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
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise unittest.SkipTest("ffmpeg 不在 PATH")
    subprocess.run([ffmpeg, "-y", "-f", "lavfi",
                    "-i", f"sine=frequency=440:duration={length_seconds}",
                    "-ar", "22050", "-ac", "1", "-b:a", "64k", str(path)],
                   capture_output=True, check=True, timeout=30)


def _synth_png(path: Path, color: str = "red"):
    """生成纯色 png（用 ffmpeg）。"""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise unittest.SkipTest("ffmpeg 不在 PATH")
    subprocess.run([ffmpeg, "-y", "-f", "lavfi",
                    "-i", f"color=c={color}:s=720x480:d=1",
                    "-frames:v", "1", "-update", "1", str(path)],
                   capture_output=True, check=True, timeout=15)


class MakeIntroVideoTests(unittest.TestCase):
    def test_make_intro_video_produces_playable_mp4(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_p = Path(tmp)
            img = tmp_p / "src.png"; _synth_png(img, "blue")
            aud = tmp_p / "src.mp3"; _synth_mp3(aud, 3.0)
            out = tmp_p / "out.mp4"
            s.make_intro_video(img, aud, out, duration=2.5)
            self.assertTrue(out.exists())
            self.assertGreater(out.stat().st_size, 0)
            d = s.probe_audio_duration(out)  # 这里 probe 会失败因为 out 是视频不是音频
            # ffprobe 默认输出视频时长（不限于音频），重新跑 ffprobe 直接调
            r = subprocess.run([shutil.which("ffprobe"), "-v", "error",
                                "-show_entries", "format=duration",
                                "-of", "default=noprint_wrappers=1:nokey=1", str(out)],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0)
            self.assertGreater(float(r.stdout.strip()), 1.5)


class Step4IntroVideoEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        tmp_path = Path(cls.tmp.name)
        cls.orig_data = s.DATA_DIR
        cls.orig_settings = s.SETTINGS_PATH
        s.DATA_DIR = tmp_path / "data"
        s.SETTINGS_PATH = s.DATA_DIR / "settings.json"
        s.DATA_DIR.mkdir()
        s.SETTINGS_PATH.write_text("{}", encoding="utf-8")
        cls.port = 18830 + (uuid.getnode() % 100)
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

    def test_intro_video_off_returns_empty(self):
        status, body = self._post("/api/step4_intro_video",
                                  {"task_id": "t_off", "mode": "off", "shots": []})
        self.assertEqual(status, 200)
        self.assertEqual(body["results"], [])

    def test_intro_video_accepts_task_image_url_from_browser_pipeline(self):
        task_dir = s.DATA_DIR / "tasks" / "t_url_image"
        covers = task_dir / "covers"
        covers.mkdir(parents=True, exist_ok=True)
        image = covers / "1.png"
        audio = task_dir / "seg_001.mp3"
        _synth_png(image)
        _synth_mp3(audio, 1.0)
        status, body = self._post("/api/step4_intro_video", {
            "task_id": "t_url_image", "mode": "3", "ratio": "9:16",
            "shots": [{"idx": 1, "image_path": "/api/task_image/t_url_image/1.png",
                       "audio_path": str(audio), "duration": 1.0}],
        })
        self.assertEqual(status, 200, body)
        self.assertTrue(body["results"][0]["ok"], body)

    def test_intro_video_3_makes_first_n_videos(self):
        with tempfile.TemporaryDirectory() as inner:
            inner_p = Path(inner)
            imgs = []
            auds = []
            for i in range(4):
                p = inner_p / f"img_{i}.png"; _synth_png(p, "blue"); imgs.append(str(p))
                a = inner_p / f"aud_{i}.mp3"; _synth_mp3(a, 2.0); auds.append(str(a))
            status, body = self._post("/api/step4_intro_video", {
                "task_id": "t_dyn_3", "mode": "3", "ratio": "9:16",
                "shots": [
                    {"idx": i+1, "image_path": imgs[i],
                     "audio_path": auds[i], "duration": 2.0}
                    for i in range(4)
                ],
            })
        self.assertEqual(status, 200, body)
        ok = [r for r in body["results"] if r.get("ok")]
        self.assertEqual(len(ok), 3)
        self.assertEqual([r["idx"] for r in ok], [1, 2, 3])
        # 落盘到 data/tasks/t_dyn_3/videos/
        for r in ok:
            self.assertTrue(Path(r["video_path"]).exists())

    def test_intro_video_custom_only_targets_listed_idxs(self):
        with tempfile.TemporaryDirectory() as inner:
            inner_p = Path(inner)
            imgs = []
            auds = []
            for i in range(4):
                p = inner_p / f"img_{i}.png"; _synth_png(p); imgs.append(str(p))
                a = inner_p / f"aud_{i}.mp3"; _synth_mp3(a, 2.0); auds.append(str(a))
            status, body = self._post("/api/step4_intro_video", {
                "task_id": "t_dyn_custom", "custom_idxs": [2, 4],
                "mode": "custom", "ratio": "9:16",
                "shots": [
                    {"idx": i+1, "image_path": imgs[i],
                     "audio_path": auds[i], "duration": 2.0}
                    for i in range(4)
                ],
            })
        self.assertEqual(status, 200, body)
        ok = [r for r in body["results"] if r.get("ok")]
        self.assertEqual([r["idx"] for r in ok], [2, 4])

    def test_step6_prefers_videos_over_images(self):
        """直接构造 payload 验证 step6 优先用 videos。"""
        with tempfile.TemporaryDirectory() as inner:
            inner_p = Path(inner)
            # 创建假剪映草稿目录
            draft_root = inner_p / "drafts"
            draft_root.mkdir()
            # 用 settings 注入 draft_path
            s.SETTINGS_PATH.write_text(json.dumps({
                "jianying": {"draft_path": str(draft_root)},
            }), encoding="utf-8")
            _synth_png(inner_p / "img1.png")
            _synth_mp3(inner_p / "aud1.mp3", 2.0)
            # 先调 step4_intro_video 生成视频
            video_status, _ = self._post("/api/step4_intro_video", {
                "task_id": "t_prio",
                "mode": "3",
                "ratio": "9:16",
                "shots": [{"idx": 1, "image_path": str(inner_p / "img1.png"),
                           "audio_path": str(inner_p / "aud1.mp3"),
                           "duration": 2.0}],
            })
            self.assertEqual(video_status, 200)
            # 拿 step6 草稿
            status, body = self._post("/api/step6_jianying_draft", {
                "task_id": "t_prio",
                "title": "测试",
                "shots": [{"idx": 1, "text": "一"}],
                "images": [{"idx": 1, "url": "/covers/dummy.png", "task_local": "/none.png"}],
                "videos": [{"idx": 1, "video_path": str(s.DATA_DIR / "tasks" / "t_prio" / "videos" / "seg_001.mp4"),
                            "video_url": "/api/task_video/t_prio/seg_001.mp4"}],
                "segments": [{"idx": 1, "duration": 2.0,
                              "path": str(inner_p / "aud1.mp3"),
                              "url": "/api/audio/t_prio/seg_001.mp3"}],
                "ratio": "9:16",
            })
            self.assertEqual(status, 200, body)
            # 验证草稿里 video material 是 video 类型
            draft_files = list(draft_root.glob("**/draft_content.json"))
            self.assertGreater(len(draft_files), 0)
            draft = json.loads(draft_files[0].read_text(encoding="utf-8"))
            video_segs = []
            for track in draft.get("tracks", []):
                for seg in track.get("segments", []):
                    if seg.get("type") == "video":
                        video_segs.append(seg)
            # 第一段应该用 video material（material_id 以 video_ 开头）
            self.assertTrue(any(s.get("material_id", "").startswith("video_")
                              for s in video_segs),
                          f"video segment should be used: {video_segs}")

    def test_step6_uses_task_local_for_material_library_image(self):
        with tempfile.TemporaryDirectory() as inner:
            draft_root = Path(inner) / "drafts"
            draft_root.mkdir()
            s.SETTINGS_PATH.write_text(json.dumps({
                "jianying": {"draft_path": str(draft_root)},
            }), encoding="utf-8")
            cover_dir = s.DATA_DIR / "tasks" / "t_material_draft" / "covers"
            cover_dir.mkdir(parents=True, exist_ok=True)
            image = cover_dir / "1.png"
            _synth_png(image)
            status, body = self._post("/api/step6_jianying_draft", {
                "task_id": "t_material_draft", "title": "素材路径测试",
                "shots": [{"idx": 1, "text": "一"}],
                "images": [{"idx": 1, "url": "/api/material/abc.png",
                            "task_local": "/api/task_image/t_material_draft/1.png"}],
                "segments": [{"idx": 1, "duration": 2.0, "path": "audio.mp3"}],
            })
            self.assertEqual(status, 200, body)
            draft = json.loads((Path(body["draft_dir"]) / "draft_content.json").read_text(encoding="utf-8"))
            video_track = next(track for track in draft["tracks"] if track["type"] == "video")
            self.assertEqual(video_track["segments"][0]["material_path"], str(image))


if __name__ == "__main__":
    unittest.main()
