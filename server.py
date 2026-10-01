"""app074 · 文案改写双线版（图文1号线 STORY / 图文2号线 USER）

独立运行，不读取 071/072/073 任何文件。
API Key 在 app074/data/settings.json 中由用户自己填写。
"""
import json
import os
import re
import sys
import tempfile
import time
import uuid
import urllib.error
import urllib.request
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
PROMPTS_DIR = ROOT / "prompts"
DATA_DIR = ROOT / "data"
SETTINGS_PATH = DATA_DIR / "settings.json"
PROFILES_PATH = DATA_DIR / "profiles.json"
PORT = 18801

LLM_PROVIDERS = {
    "deepseek": {"protocol": "openai", "base_url": "https://api.deepseek.com"},
    "bailian": {"protocol": "openai", "base_url": "https://dashscope.aliyuncs.com/compatible-mode"},
    "moonshot": {"protocol": "openai", "base_url": "https://api.moonshot.cn"},
    "zhipu": {"protocol": "openai", "base_url": "https://open.bigmodel.cn/api/paas"},
    "minimax": {"protocol": "openai", "base_url": "https://api.MiniMax.chat/v1"},
    "anthropic": {"protocol": "anthropic", "base_url": "https://api.anthropic.com"},
    "custom": {"protocol": "openai", "base_url": ""},
}


def load_settings():
    if not SETTINGS_PATH.exists():
        return {}
    try:
        raw = json.loads(SETTINGS_PATH.read_text("utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (ValueError, OSError):
        return {}


# ============================================================
# 任务管理 — 扫描 data/tasks/ 列出所有任务 + 单个任务详情
# 参考 STORY ao 函数（index-CXUXw7CE.js:41484）的产物扫描逻辑：
#   6 个产物文件 + 0/1/meta/2/3/4/5/6 完成度判断
# 074 数据布局：data/tasks/<task_id>/
#   - 02-rewrite.txt    (Step 1 改写)
#   - 02-meta.json     (Step 1 元信息)
#   - 03-shots.json    (Step 2 分镜)
#   - 04-prompts.json  (Step 3 出图 prompt)
#   - audio/seg_NNN.mp3 (Step 5 配音)
#   - 05-tts-segments.json
#   - covers/<n>.png   (Step 4 出图)
#   - 06-draft-meta.json
# ============================================================
def _tasks_root():
    return DATA_DIR / "tasks"

def _scan_task(task_dir):
    """扫描单个 task_dir 返回 {completed_steps:[...], files:{...}, title, has_draft, ...}"""
    if not task_dir.is_dir():
        return None
    info = {
        "task_id": task_dir.name,
        "completed_steps": [],
        "files": {},
        "shot_count": 0,
        "image_count": 0,
        "audio_count": 0,
        "total_duration_sec": 0,
        "title": "",
        "created_at": "",
        "draft_dir": "",
    }
    # 改写
    p = task_dir / "02-rewrite.txt"
    if p.exists():
        info["completed_steps"].append(1)
        info["files"]["rewrite"] = p.name
        try:
            txt = p.read_text(encoding="utf-8")
            info["files"]["rewrite_chars"] = len(txt)
        except OSError:
            pass
    # 元信息
    p = task_dir / "02-meta.json"
    if p.exists():
        info["completed_steps"].append("meta")
        info["files"]["meta"] = p.name
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
            info["title"] = m.get("title") or info["title"]
            info["files"]["cover_prompts"] = len(m.get("cover_image_prompts") or [])
        except (OSError, ValueError):
            pass
    # 分镜
    p = task_dir / "03-shots.json"
    if p.exists():
        info["completed_steps"].append(2)
        info["files"]["shots"] = p.name
        try:
            shots = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(shots, list):
                info["shot_count"] = len(shots)
        except (OSError, ValueError):
            pass
    # 出图 prompt
    p = task_dir / "04-prompts.json"
    if p.exists():
        info["completed_steps"].append(3)
        info["files"]["prompts"] = p.name
    # 出图实际文件
    covers_dir = task_dir / "covers"
    if covers_dir.exists() and covers_dir.is_dir():
        pngs = list(covers_dir.glob("*.png")) + list(covers_dir.glob("*.jpg"))
        if pngs:
            info["completed_steps"].append(4)
            info["image_count"] = len(pngs)
            info["files"]["covers_dir"] = "covers/"
    # 配音
    audio_dir = task_dir / "audio"
    if audio_dir.exists() and audio_dir.is_dir():
        mp3s = list(audio_dir.glob("*.mp3"))
        if mp3s:
            info["completed_steps"].append(5)
            info["audio_count"] = len(mp3s)
            info["files"]["audio_dir"] = "audio/"
    seg_json = task_dir / "05-tts-segments.json"
    if seg_json.exists():
        try:
            segs = json.loads(seg_json.read_text(encoding="utf-8"))
            if isinstance(segs, list):
                info["total_duration_sec"] = round(
                    sum(float(s.get("duration") or 0) for s in segs), 2
                )
        except (OSError, ValueError):
            pass
    # 剪映草稿
    draft_meta = task_dir / "06-draft-meta.json"
    if draft_meta.exists():
        info["completed_steps"].append(6)
        info["files"]["draft_meta"] = draft_meta.name
        try:
            dm = json.loads(draft_meta.read_text(encoding="utf-8"))
            info["draft_dir"] = dm.get("draft_dir", "")
            info["title"] = dm.get("title", info["title"])
        except (OSError, ValueError):
            pass
    # 创建时间（mtime）
    try:
        st = task_dir.stat()
        info["created_at"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime))
    except OSError:
        pass
    return info

def list_tasks():
    """列出所有任务（按 mtime 倒序）。"""
    root = _tasks_root()
    if not root.exists():
        return []
    out = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        info = _scan_task(child)
        if info:
            out.append(info)
    out.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return out

def get_task_detail(task_id):
    """获取单个任务详情（含每步具体数据）。"""
    task_dir = _tasks_root() / task_id
    info = _scan_task(task_dir)
    if not info:
        return None
    # 加载具体产物
    detail = {"info": info, "steps": {}}
    p = task_dir / "02-rewrite.txt"
    if p.exists():
        try:
            detail["steps"]["rewrite"] = p.read_text(encoding="utf-8")
        except OSError:
            pass
    p = task_dir / "02-meta.json"
    if p.exists():
        try:
            detail["steps"]["meta"] = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    p = task_dir / "03-shots.json"
    if p.exists():
        try:
            detail["steps"]["shots"] = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    p = task_dir / "04-prompts.json"
    if p.exists():
        try:
            detail["steps"]["prompts"] = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    p = task_dir / "05-tts-segments.json"
    if p.exists():
        try:
            detail["steps"]["segments"] = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    # 出图列表（filename + url）
    covers_dir = task_dir / "covers"
    if covers_dir.exists():
        imgs = []
        for png in sorted(covers_dir.glob("*.png")) + sorted(covers_dir.glob("*.jpg")):
            imgs.append({
                "name": png.name,
                "url": f"/api/task_image/{task_id}/{png.name}",
                "size": png.stat().st_size,
            })
        detail["steps"]["images"] = imgs
    # 配音列表
    audio_dir = task_dir / "audio"
    if audio_dir.exists():
        aud_files = []
        for mp3 in sorted(audio_dir.glob("*.mp3")):
            aud_files.append({
                "name": mp3.name,
                "url": f"/api/audio/{task_id}/{mp3.name}",
                "size": mp3.stat().st_size,
            })
        detail["steps"]["audios"] = aud_files
    # 草稿元数据
    p = task_dir / "06-draft-meta.json"
    if p.exists():
        try:
            detail["steps"]["draft"] = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    return detail


# ============================================================
# LLM 配置档案（list of profiles，匹配 STORY 1.24.0 Settings-XLgSTp15.js
#   line 938 Ta dict + 948 Aa component + 1019 wa editor + 1082 profile-list）
# 存储在 data/profiles.json，与 settings.json 的 image/tts/jy/ima 解耦
# ============================================================
def load_profiles():
    if not PROFILES_PATH.exists():
        return []
    try:
        raw = json.loads(PROFILES_PATH.read_text("utf-8"))
        return raw if isinstance(raw, list) else []
    except (ValueError, OSError):
        return []


def save_profiles(profiles):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not isinstance(profiles, list):
        raise ValueError("profiles 必须是数组")
    temp = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=DATA_DIR, delete=False
        ) as f:
            temp = Path(f.name)
            json.dump(profiles, f, ensure_ascii=False)
            f.flush(); os.fsync(f.fileno())
        os.replace(temp, PROFILES_PATH)
    finally:
        if temp and temp.exists():
            temp.unlink()


def public_profiles():
    """返回给前端：所有 profile 的元信息（key 脱敏到只显示前缀+后缀）。"""
    out = []
    for p in load_profiles():
        if not isinstance(p, dict): continue
        key = p.get("apiKey", "") or ""
        masked = ""
        if key:
            if len(key) <= 8: masked = "•" * len(key)
            else: masked = key[:4] + "•" * min(20, len(key) - 8) + key[-4:]
        out.append({
            "id":       p.get("id") or "",
            "name":     p.get("name") or "未命名",
            "provider": p.get("provider") or "deepseek",
            "protocol": p.get("protocol") or "openai",
            "model":    p.get("model") or "",
            "baseUrl":  p.get("baseUrl") or "",
            "apiKey":   masked,
            "fallback": p.get("fallback") or [],
            "proxyUrl": p.get("proxyUrl") or "",
            "enabled":  bool(p.get("enabled")),
        })
    return out


def resolve_active_llm_settings():
    """取当前激活的 profile，转成 settings 风格 dict（call_llm 期望的格式）。
    如果没有 profiles 或没有 enabled 的，回退到 settings.json 顶层字段。
    """
    profiles = load_profiles()
    active = next((p for p in profiles if p.get("enabled")), None)
    if not active and profiles:
        active = profiles[0]  # 兜底：拿第一个
    if active:
        return {
            "provider": active.get("provider", "deepseek"),
            "protocol": active.get("protocol", "openai"),
            "base_url": (active.get("baseUrl") or "").rstrip("/"),
            "model":    active.get("model", ""),
            "api_key":  active.get("apiKey", ""),
            "proxy":    active.get("proxyUrl", ""),
            "fallback": active.get("fallback", []) or [],
        }
    # 兜底：旧 settings.json 顶层字段
    s = load_settings()
    return {
        "provider": s.get("provider", ""),
        "protocol": s.get("protocol", "openai"),
        "base_url": (s.get("base_url") or "").rstrip("/"),
        "model":    s.get("model", ""),
        "api_key":  s.get("api_key", ""),
        "proxy":    s.get("proxy", ""),
        "fallback": s.get("fallback", []) or [],
    }


# 哨兵值：前端用此值表示「这一字段请保留原值，不要覆盖」
KEEP = "__KEEP__"


def _val(v, default=""):
    """取字段值；哨兵 __KEEP__ 直接返回 default（保留现有值）。空字符串当作缺失。"""
    if v is None:
        return default
    s = str(v)
    if s == KEEP:
        return default
    return s.strip() or default

def _val_int(v, default=0):
    """整数字段；KEEP 保留 default。"""
    if v is None:
        return default
    s = str(v)
    if s == KEEP:
        return default
    try:
        return int(s)
    except (ValueError, TypeError):
        return default

def _val_bool(v, default=False):
    """布尔字段；KEEP 保留 default。"""
    if v is None:
        return default
    s = str(v)
    if s == KEEP:
        return default
    if s.lower() in ("true", "1", "yes", "on", "async"):
        return True
    if s.lower() in ("false", "0", "no", "off", "sync"):
        return False
    return default


def _merged(values):
    """把新提交的值和现有 settings 合并；__KEEP__ 表示保留现有值。"""
    cur = load_settings()

    # LLM 顶层
    provider = values.get("provider")
    # 备选模型（custom 时来自 textarea 每行一个；normal 时也允许）
    fb_raw = values.get("fallback")
    if fb_raw is None:
        out_fallback = cur.get("fallback", [])
    elif not isinstance(fb_raw, list):
        out_fallback = []
    else:
        out_fallback = [str(x).strip() for x in fb_raw if str(x).strip()]

    if provider is not None and str(provider) != KEEP:
        out_provider = provider.strip()
        out_protocol = _val(values.get("protocol"), cur.get("protocol", "openai"))
        out_base_url = _val(values.get("base_url"), cur.get("base_url", ""))
        out_model    = _val(values.get("model"),    cur.get("model", ""))
        new_key      = _val(values.get("api_key"),  None)
        out_key      = cur.get("api_key", "") if new_key is None else new_key
        out_proxy    = _val(values.get("proxy"),    cur.get("proxy", ""))
        # custom 时：model 可空但 base_url 必须填；其他：全必填
        if out_provider == "custom":
            if not out_provider or not out_protocol or not out_base_url or not out_key:
                raise ValueError("自定义 LLM 必填：provider / protocol / base_url / api_key")
        else:
            if not out_provider or not out_protocol or not out_base_url or not out_model or not out_key:
                raise ValueError("LLM 必填字段：provider / protocol / base_url / model / api_key")
    else:
        out_provider = cur.get("provider", "")
        out_protocol = cur.get("protocol", "openai")
        out_base_url = cur.get("base_url", "")
        out_model    = cur.get("model", "")
        out_key      = cur.get("api_key", "")
        out_proxy    = _val(values.get("proxy"),    cur.get("proxy", ""))
        if out_provider == "custom":
            if not (out_provider and out_protocol and out_base_url and out_key):
                raise ValueError("首次配自定义 LLM 必须填齐：provider / protocol / base_url / api_key")
        else:
            if not (out_provider and out_protocol and out_base_url and out_model and out_key):
                raise ValueError("首次必须先配齐 LLM：provider / protocol / base_url / model / api_key")

    # 通用出图块（OpenAI 兼容通道：gpt_image / modelscope / custom_image）
    img_cur = cur.get("image", {}) or {}
    image = {
        "provider":    _val(values.get("image_provider"), img_cur.get("provider", "gpt_image")),
        "base_url":    _val(values.get("image_base_url"), img_cur.get("base_url", "https://api.openai.com")),
        "api_key":     _val(values.get("image_api_key"),  img_cur.get("api_key", "")) or "",
        "model":       _val(values.get("image_model"),    img_cur.get("model", "gpt-image-1")),
        "ratio":       _val(values.get("image_ratio"),    img_cur.get("ratio", "9:16")),
        "resolution":  _val(values.get("image_resolution"), img_cur.get("resolution", "1k")),
        "proxy_url":   _val(values.get("image_proxy_url"), img_cur.get("proxy_url", "")) or "",
        "concurrency": _val_int(values.get("image_concurrency"), img_cur.get("concurrency", 6)),
    }

    # jimeng 块（Session ID + 模型 + 比例 + 分辨率 + 并发数）
    jm_cur = cur.get("jimeng", {}) or {}
    jimeng = {
        "session_id":  _val(values.get("jimeng_session_id"), jm_cur.get("session_id", "")),
        "ak":          _val(values.get("jimeng_ak"),         jm_cur.get("ak", "")),    # 兼容旧 schema
        "sk":          _val(values.get("jimeng_sk"),         jm_cur.get("sk", "")) or "",
        "model":       _val(values.get("jimeng_model"),      jm_cur.get("model", "jimeng-4.5")),
        "ratio":       _val(values.get("jimeng_ratio"),      jm_cur.get("ratio", "9:16")),
        "resolution":  _val(values.get("jimeng_resolution"), jm_cur.get("resolution", "1k")),
        "concurrency": _val_int(values.get("jimeng_concurrency"), jm_cur.get("concurrency", 3)),
    }

    # modelscope 块（多 Token + 模型 + 比例 + 自动切积分 + 自定义模型）
    ms_cur = cur.get("modelscope", {}) or {}
    ms_tokens_in = values.get("modelscope_tokens")
    ms_cust_in   = values.get("modelscope_custom_models")
    modelscope = {
        "tokens":             ms_tokens_in if isinstance(ms_tokens_in, list) else ms_cur.get("tokens", []),
        "model":              _val(values.get("modelscope_model"),     ms_cur.get("model", "Tongyi-MAI/Z-Image-Turbo")),
        "ratio":              _val(values.get("modelscope_ratio"),     ms_cur.get("ratio", "9:16")),
        "auto_fallback_gpt":  _val_bool(values.get("modelscope_auto_fallback_gpt"), ms_cur.get("auto_fallback_gpt", False)),
        "custom_models":      ms_cust_in if isinstance(ms_cust_in, list) else ms_cur.get("custom_models", []),
    }

    # runninghub 块（Key + 3 个模型 + 比例 + 分辨率 + 并发数）
    rh_cur = cur.get("runninghub", {}) or {}
    runninghub = {
        "api_key":     _val(values.get("rh_api_key"),  rh_cur.get("api_key", "")) or "",
        "model":       _val(values.get("rh_model"),    rh_cur.get("model", "rh-image-g2")),
        "ratio":       _val(values.get("rh_ratio"),    rh_cur.get("ratio", "9:16")),
        "resolution":  _val(values.get("rh_resolution"), rh_cur.get("resolution", "1k")),
        "concurrency": _val_int(values.get("rh_concurrency"), rh_cur.get("concurrency", 3)),
        # 兼容旧 schema
        "base_url":    _val(values.get("rh_base_url"),    rh_cur.get("base_url", "https://www.runninghub.ai")),
        "workflow_id": _val(values.get("rh_workflow_id"), rh_cur.get("workflow_id", "")) or "",
    }

    # custom_image 块（自定义 OpenAI 兼容）
    cu_cur = cur.get("custom_image", {}) or {}
    custom_image = {
        "display_name":        _val(values.get("custom_display_name"), cu_cur.get("display_name", "")),
        "base_url":            _val(values.get("custom_base_url"),     cu_cur.get("base_url", "")),
        "api_key":             _val(values.get("custom_api_key"),      cu_cur.get("api_key", "")) or "",
        "model":               _val(values.get("custom_model"),        cu_cur.get("model", "")),
        "async_mode":          _val_bool(values.get("custom_protocol"), cu_cur.get("async_mode", False)) if isinstance(values.get("custom_protocol"), str) else cu_cur.get("async_mode", False),
        "ratio":               _val(values.get("custom_ratio"),        cu_cur.get("ratio", "9:16")),
        "concurrency":         _val_int(values.get("custom_concurrency"), cu_cur.get("concurrency", 5)),
        "ratio_mapping_json":  _val(values.get("custom_ratio_mapping_json"), cu_cur.get("ratio_mapping_json", "")),
    }

    tts_cur = cur.get("tts", {}) or {}
    volc_cur = tts_cur.get("volcengine", {}) or {}
    mx_cur = tts_cur.get("minimax", {}) or {}
    tts = {
        "provider": _val(values.get("tts_provider"), tts_cur.get("provider", "volcengine")),
        "volcengine": {
            "app_id":     _val(values.get("tts_volc_appid"),  volc_cur.get("app_id", "")),
            "access_key": _val(values.get("tts_volc_access"), volc_cur.get("access_key", "")),
            "speaker":    _val(values.get("tts_volc_speaker"), volc_cur.get("speaker", "zh_male_dongfanghaoran_moon_bigtts")),
        },
        "minimax": {
            "api_key":  _val(values.get("tts_minimax_key"),   mx_cur.get("api_key", "")),
            "model":    _val(values.get("tts_minimax_model"), mx_cur.get("model", "speech-2.8-hd")),
            "voice_id": _val(values.get("tts_minimax_voice"), mx_cur.get("voice_id", "")),
        },
    }

    jy_cur = cur.get("jianying", {}) or {}
    jianying = {
        "draft_path":   _val(values.get("jianying_draft_path"),  jy_cur.get("draft_path", "")),
        "bgm_path":     _val(values.get("jianying_bgm_path"),    jy_cur.get("bgm_path", "")),
        "auto_continue": _val_bool(values.get("jianying_auto_continue"), jy_cur.get("auto_continue", False)),
        "task_notify":   _val_bool(values.get("jianying_task_notify"),   jy_cur.get("task_notify", True)),
    }

    ima_cur = cur.get("ima", {}) or {}
    ima = {
        "client_id": _val(values.get("ima_client_id"), ima_cur.get("client_id", "")),
        "api_key":   _val(values.get("ima_api_key"),   ima_cur.get("api_key", "")),
        "kb_id":     _val(values.get("ima_kb_id"),     ima_cur.get("kb_id", "")),
        "kb_name":   _val(values.get("ima_kb_name"),   ima_cur.get("kb_name", "")),
    }

    # 语音识别（ASR）—— 图文 Step 5 配音对时间戳用
    asr_cur = cur.get("asr", {}) or {}
    asr = {
        "provider":   _val(values.get("asr_provider"),   asr_cur.get("provider", "volcengine")),
        "app_id":     _val(values.get("asr_app_id"),     asr_cur.get("app_id", "")),
        "access_key": _val(values.get("asr_access"),     asr_cur.get("access_key", "")),
    }

    # 激活码 —— 本软件不依赖官方激活码（所有 AI 走用户自己的 API Key），字段保留以便将来扩展
    lic_cur = cur.get("license", {}) or {}
    license_info = {"key": _val(values.get("license_key"), lic_cur.get("key", ""))}

    return {
        "provider": out_provider,
        "protocol": out_protocol,
        "base_url": out_base_url.rstrip("/"),
        "model":    out_model,
        "api_key":  out_key,
        "proxy":    out_proxy,
        "fallback": out_fallback,
        "image":    image,
        "jimeng":   jimeng,
        "runninghub": runninghub,
        "modelscope":   modelscope,
        "custom_image": custom_image,
        "tts":      tts,
        "jianying": jianying,
        "ima":      ima,
        "asr":      asr,
        "license":  license_info,
    }


def save_settings(values):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = _merged(values)
    if not re.match(r"^https?://", payload["base_url"]):
        raise ValueError("base_url 必须以 http:// 或 https:// 开头")
    if len(payload["model"]) > 300:
        raise ValueError("模型名过长")
    if payload["image"]["api_key"] and not re.match(r"^https?://", payload["image"]["base_url"]):
        raise ValueError("image_base_url 必须以 http:// 或 https:// 开头")
    temp = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=DATA_DIR, delete=False
        ) as f:
            temp = Path(f.name)
            json.dump(payload, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, SETTINGS_PATH)
    finally:
        if temp and temp.exists():
            temp.unlink()


def public_settings():
    s = load_settings()
    img = s.get("image", {})
    tts = s.get("tts", {})
    tts_volc = tts.get("volcengine", {})
    tts_mx = tts.get("minimax", {})
    jy = s.get("jianying", {})
    ima = s.get("ima", {})
    # LLM 「已配置」要求 4 个核心字段都填齐（不再只看 api_key；
    # 否则用户只填一个 Key 也会一直显示「已配置」，掩盖实际未配齐的事实）
    llm_provider = s.get("provider", "")
    llm_model    = s.get("model", "")
    llm_base_url = s.get("base_url", "")
    llm_api_key  = s.get("api_key", "")
    # 还要排除「过时模型」——用户 settings.json 里残留着旧版本默认值（如 deepseek-chat）
    # 时，不能算"已配置"，因为现在 STORY 1.24.0 已经没有这个模型了
    is_stale = llm_model in STALE_LLM_MODELS.get(llm_provider, set())
    llm_configured = bool(llm_provider and llm_api_key and llm_model and llm_base_url and not is_stale)
    # 出图：OpenAI 兼容通道需要 base_url + api_key + model；其它通道单独算
    img_provider = img.get("provider", "gpt_image")
    img_configured = bool(img.get("api_key") and img.get("model") and img.get("base_url"))
    return {
        "configured": llm_configured,
        "provider": llm_provider,
        "protocol": s.get("protocol", "openai"),
        "model": llm_model,
        "base_url": llm_base_url,
        "proxy": s.get("proxy", ""),
        "fallback": s.get("fallback", []) or [],
        "image": {
            "configured": img_configured,
            "provider": img_provider,
            "base_url": img.get("base_url", "https://api.openai.com"),
            "model": img.get("model", ""),
            "ratio": img.get("ratio", "9:16"),
            "resolution": img.get("resolution", "1k"),
            "proxy_url": img.get("proxy_url", ""),
            "concurrency": img.get("concurrency", 6),
        },
        "jimeng": {
            "configured": bool((s.get("jimeng") or {}).get("session_id") or ((s.get("jimeng") or {}).get("ak") and (s.get("jimeng") or {}).get("sk"))),
            "session_id": (s.get("jimeng") or {}).get("session_id", ""),
            "ak": (s.get("jimeng") or {}).get("ak", ""),
            "sk": (s.get("jimeng") or {}).get("sk", ""),
            "model": (s.get("jimeng") or {}).get("model", "jimeng-4.5"),
            "ratio": (s.get("jimeng") or {}).get("ratio", "9:16"),
            "resolution": (s.get("jimeng") or {}).get("resolution", "1k"),
            "concurrency": (s.get("jimeng") or {}).get("concurrency", 3),
        },
        "modelscope": {
            "configured": bool((s.get("modelscope") or {}).get("tokens")),
            "tokens": (s.get("modelscope") or {}).get("tokens", []),
            "model": (s.get("modelscope") or {}).get("model", "Tongyi-MAI/Z-Image-Turbo"),
            "ratio": (s.get("modelscope") or {}).get("ratio", "9:16"),
            "auto_fallback_gpt": (s.get("modelscope") or {}).get("auto_fallback_gpt", False),
            "custom_models": (s.get("modelscope") or {}).get("custom_models", []),
        },
        "runninghub": {
            "configured": bool((s.get("runninghub") or {}).get("api_key")),
            "api_key": (s.get("runninghub") or {}).get("api_key", ""),
            "model": (s.get("runninghub") or {}).get("model", "rh-image-g2"),
            "ratio": (s.get("runninghub") or {}).get("ratio", "9:16"),
            "resolution": (s.get("runninghub") or {}).get("resolution", "1k"),
            "concurrency": (s.get("runninghub") or {}).get("concurrency", 3),
            "base_url": (s.get("runninghub") or {}).get("base_url", ""),
            "workflow_id": (s.get("runninghub") or {}).get("workflow_id", ""),
        },
        "custom_image": {
            "configured": bool((s.get("custom_image") or {}).get("base_url") and (s.get("custom_image") or {}).get("api_key") and (s.get("custom_image") or {}).get("model")),
            "display_name": (s.get("custom_image") or {}).get("display_name", ""),
            "base_url": (s.get("custom_image") or {}).get("base_url", ""),
            "api_key": (s.get("custom_image") or {}).get("api_key", ""),
            "model": (s.get("custom_image") or {}).get("model", ""),
            "async_mode": (s.get("custom_image") or {}).get("async_mode", False),
            "ratio": (s.get("custom_image") or {}).get("ratio", "9:16"),
            "concurrency": (s.get("custom_image") or {}).get("concurrency", 5),
            "ratio_mapping_json": (s.get("custom_image") or {}).get("ratio_mapping_json", ""),
        },
        "tts": {
            "provider": tts.get("provider", "volcengine"),
            "volcengine_configured": bool(tts_volc.get("app_id") and tts_volc.get("access_key") and tts_volc.get("speaker")),
            "volcengine_app_id": tts_volc.get("app_id", ""),
            "volcengine_speaker": tts_volc.get("speaker", ""),
            "minimax_configured": bool(tts_mx.get("api_key") and tts_mx.get("model")),
            "minimax_model": tts_mx.get("model", ""),
            "minimax_voice_id": tts_mx.get("voice_id", ""),
        },
        "jianying": {
            "draft_path":   jy.get("draft_path", ""),
            "bgm_path":     jy.get("bgm_path", ""),
            "auto_continue": jy.get("auto_continue", False),
            "task_notify":   jy.get("task_notify", True),
            "configured":   bool(jy.get("draft_path")),
        },
        "ima": {
            "configured": bool(ima.get("api_key") and ima.get("kb_id") and ima.get("client_id")),
            "client_id": ima.get("client_id", ""),
            "kb_name": ima.get("kb_name", ""),
            "kb_id": ima.get("kb_id", ""),
        },
        "asr": {
            "provider": (s.get("asr") or {}).get("provider", "volcengine"),
            "app_id": (s.get("asr") or {}).get("app_id", ""),
            "configured": bool((s.get("asr") or {}).get("app_id")),
        },
        "license": {
            "key": (s.get("license") or {}).get("key", ""),
            "configured": bool((s.get("license") or {}).get("key")),
        },
    }


def load_prompt_module(rel_path):
    """载入 prompts/ 下的 Python 模块，调用其 get() 返回文本。"""
    import importlib.util

    full = PROMPTS_DIR / rel_path
    if not full.exists():
        return ""
    spec = importlib.util.spec_from_file_location(
        rel_path.replace("/", "_").replace(".py", ""), full
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.get() if hasattr(mod, "get") else ""


# 两线对应的提示词组合
# 已知「过时」的 LLM 模型名（从前版本遗留下来的默认值；现在不算"已配置"）
# 例如 STORY 1.24.0 把 deepseek-chat 升级到了 deepseek-v4-pro；用户 settings.json 里
# 还残留着旧值时，应该提示重新选择，而不是继续当作"已配置"
STALE_LLM_MODELS = {
    "deepseek": {"deepseek-chat", "deepseek-reasoner", "deepseek-coder"},
    "bailian":  {"qwen-max", "qwen-plus", "qwen-turbo",
                 "qwen2-max", "qwen2.5-max", "qwen2.5-plus", "qwen2.5-turbo",
                 "qwen3-max", "qwen3-plus", "qwen3-turbo"},
    "moonshot": {"moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k",
                 "kimi-k2", "kimi-k2-thinking"},
    "zhipu":    {"glm-4", "glm-4-plus", "glm-4-air", "glm-4-flash", "glm-4-airx"},
    "minimax":  {"abab6.5-chat", "abab6.5s-chat", "abab5.5-chat", "MiniMax-M2"},
    "custom":   set(),
}


STORY_LEVELS = {
    "standard": {
        "label": "标准改写",
        "diff": "目标差异化 ~40%",
        "base": "story/base_rewrite.py",
        "track": "story/track_rewrite.py",
        "technique": "story/technique_standard.py",
        "needs_reference": True,
    },
    "deep": {
        "label": "深度改写",
        "diff": "目标差异化 ~60%",
        "base": "story/base_rewrite.py",
        "track": "story/track_rewrite.py",
        "technique": "story/technique_deep.py",
        "needs_reference": True,
    },
    "original": {
        "label": "高度原创",
        "diff": "目标差异化 ~80%",
        "base": "story/base_rewrite.py",
        "track": "story/track_rewrite.py",
        "technique": "story/technique_original.py",
        "needs_reference": True,
    },
}

USER_LEVELS = {
    "surface": {
        "label": "改表层",
        "diff": "差异化 ≥ 50%",
        "technique": "user/surface.py",
        "needs_reference": True,
    },
    "creative_surface": {
        "label": "创意改表层",
        "diff": "差异化 ≥ 70%",
        "technique": "user/creative_surface.py",
        "needs_reference": True,
    },
    "skeleton": {
        "label": "改骨架",
        "diff": "差异化 ≥ 80%",
        "technique": "user/skeleton.py",
        "needs_reference": True,
    },
    "original": {
        "label": "原创",
        "diff": "独立创作",
        "technique": "user/original.py",
        "needs_reference": False,
    },
}

VIEWPOINT_MODULES = {
    "keep": "",  # 保持原文：不追加
    "first": "story/viewpoint_first.py",
    "third": "story/viewpoint_third.py",
}


TRACK_LABEL = {
    "character": "人物故事",
    "health":    "健康图书",
    "folk":      "民间故事",
    "culture":   "文化科普",
    "picture":   "绘本故事",
    "ecom":      "电商带货",
    "soul":      "心灵鸡汤",
}

HOOK_LABEL = {
    "subvert":   "颠覆认知型",
    "resonate":  "扎心共鸣型",
    "cost":      "代价悬念型",
    "reveal":    "内幕揭秘型",
    "contrast":  "反差独白型",
}

SOURCE_LABEL = {
    "search": "全网搜索",
    "kb":     "AI 内置知识库补充",
    "ima":    "IMA 知识库",
}


def build_context_block(ctx):
    """把前端的丰富字段拼成一个 context 块，附加到提示词后面。"""
    lines = []
    track = TRACK_LABEL.get(ctx.get("track"), "")
    if track:
        lines.append(f"- 内容赛道：{track}")
    hooks = [HOOK_LABEL[h] for h in ctx.get("hooks", []) if h in HOOK_LABEL]
    if hooks:
        lines.append(f"- 黄金 3 秒钩子：{' / '.join(hooks)}")
    sources = [SOURCE_LABEL[s] for s in ctx.get("sources", []) if s in SOURCE_LABEL]
    if sources:
        lines.append(f"- 数据源：{' / '.join(sources)}")
    if ctx.get("keywords"):
        lines.append(f"- 关键词：{ctx['keywords'].strip()}")
    if ctx.get("product"):
        lines.append(f"- 带货商品信息：{ctx['product'].strip()}")
    if ctx.get("fixed_opening"):
        lines.append(f"- 固定开头（必须原样保留）：{ctx['fixed_opening'].strip()}")
    if ctx.get("tail_guide"):
        lines.append(f"- 尾部引导（结尾必须拼接）：{ctx['tail_guide'].strip()}")
    if not lines:
        return ""
    return "\n## 任务上下文\n" + "\n".join(lines)


def build_story_prompt(level_key, viewpoint, reference, ctx):
    cfg = STORY_LEVELS[level_key]
    parts = [
        "你是一名资深短视频文案改写专家。请严格遵循以下改写规则：",
        load_prompt_module("story/base_rewrite.py"),
        load_prompt_module("story/track_rewrite.py"),
        load_prompt_module("hook.py"),
        load_prompt_module(cfg["technique"]),
    ]
    if viewpoint == "first":
        parts.append(load_prompt_module(VIEWPOINT_MODULES["first"]))
    elif viewpoint == "third":
        parts.append(load_prompt_module(VIEWPOINT_MODULES["third"]))
    elif viewpoint == "overview":
        parts.append("## 叙事视角\n用全知视角概述故事，不再拘泥于第一人称/第三人称。")
    parts.append("\n## 输出硬约束\n1. 纯配音口播稿，最终交给 TTS 朗读，禁止任何剧本式/分镜式标注。\n2. 段落之间用空行分隔。\n3. 字数与原文大致相当（±20%）。")
    ctx_block = build_context_block(ctx)
    if ctx_block:
        parts.append(ctx_block)
    if ctx.get("extra"):
        parts.append(f"\n## 用户补充要求\n{ctx['extra'].strip()}")
    parts.append(f"\n## 原文\n{reference.strip()}")
    parts.append("\n## 改写后文案\n")
    return "\n\n".join(parts)


def build_user_prompt(level_key, viewpoint, reference, topic, ctx):
    cfg = USER_LEVELS[level_key]
    parts = [
        "你是一名短视频文案作者，使用用户的自定义方法论改写或原创文案。",
        load_prompt_module("hook.py"),
        load_prompt_module(cfg["technique"]),
    ]
    if viewpoint == "first":
        parts.append(load_prompt_module(VIEWPOINT_MODULES["first"]))
    elif viewpoint == "third":
        parts.append(load_prompt_module(VIEWPOINT_MODULES["third"]))
    elif viewpoint == "overview":
        parts.append("## 叙事视角\n用全知视角概述故事，不再拘泥于第一人称/第三人称。")
    parts.append("\n## 输出硬约束\n1. 纯配音口播稿，最终交给 TTS 朗读。\n2. 段落之间用空行分隔。\n3. 字数 1800-2200 字之间。")
    ctx_block = build_context_block(ctx)
    if ctx_block:
        parts.append(ctx_block)
    if ctx.get("extra"):
        parts.append(f"\n## 用户补充要求\n{ctx['extra'].strip()}")
    if cfg["needs_reference"]:
        if not reference.strip():
            raise ValueError(f"{cfg['label']}需要参考文案")
        parts.append(f"\n## 参考文案\n{reference.strip()}")
    else:
        if not topic.strip():
            raise ValueError(f"{cfg['label']}需要选题/标题")
        parts.append(f"\n## 选题/标题\n{topic.strip()}")
        if reference.strip():
            parts.append(f"\n## 参考文案（可作灵感，不直接引用）\n{reference.strip()}")
    parts.append("\n## 输出文案\n")
    return "\n\n".join(parts)


def call_image_gen(image_cfg, prompt, size="1024x1792"):
    """调出图 API（OpenAI 兼容 images/generations 协议）。"""
    base_url = image_cfg["base_url"].rstrip("/")
    api_key = image_cfg["api_key"]
    model = image_cfg["model"]
    if base_url.endswith("/v1/images/generations"):
        url = base_url
    elif base_url.endswith("/v1"):
        url = base_url + "/images/generations"
    else:
        url = base_url + "/v1/images/generations"
    payload = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "n": 1,
        "response_format": "b64_json",
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + api_key,
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"出图 API 失败 HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:500]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"出图 API 连接失败: {e.reason}")
    data = json.loads(body)
    choices = data.get("data") or []
    if not choices:
        raise RuntimeError(f"出图 API 返回空: {body[:300]}")
    item = choices[0]
    if item.get("b64_json"):
        return {"b64": item["b64_json"], "mime": "image/png"}
    if item.get("url"):
        return {"url": item["url"], "mime": "image/png"}
    raise RuntimeError(f"出图 API 返回格式异常: {body[:300]}")


# ============================================================
# 全能绘图师 dispatcher（模仿 STORY 的多 provider 调度架构）
# ============================================================
# 支持的 provider:
#   gpt_image    → OpenAI gpt-image-1，走 OpenAI 兼容协议
#   modelscope   → 魔搭，走 OpenAI 兼容协议
#   custom_image → 任意 OpenAI 兼容（豆包/wanx/自部署）
#   jimeng       → 火山引擎 visual API（jimeng-4.5 / jimeng-3.0），V4 HMAC-SHA256 签名
#   runninghub   → runninghub.cn 异步任务（提交 + 轮询）
# ============================================================

RATIO_MAP = {
    "9:16":  (1024, 1792),
    "16:9":  (1792, 1024),
    "1:1":   (1024, 1024),
    "3:4":   (1024, 1360),
    "4:3":   (1360, 1024),
    "2:3":   (1024, 1536),
}


def parse_ratio(ratio, fallback_size="1024x1792"):
    """9:16 → (1024,1792)  1024x1792 → (1024,1792)"""
    if not ratio:
        ratio = fallback_size
    if ":" in str(ratio):
        return RATIO_MAP.get(str(ratio), tuple(int(x) for x in fallback_size.split("x")))
    try:
        w, h = str(ratio).lower().split("x")
        return int(w), int(h)
    except (ValueError, AttributeError):
        return tuple(int(x) for x in fallback_size.split("x"))


def _http_post_json(url, headers, body_bytes, timeout=180):
    req = urllib.request.Request(url, data=body_bytes, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:500]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"连接失败: {e.reason}")


def _http_get_json(url, headers, timeout=60):
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:500]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"连接失败: {e.reason}")


# -------- 火山引擎 jimeng（即梦） V4 签名 --------
def _volc_v4_sign(method, host, path, query, body_bytes, ak, sk, region="cn-north-1", service="cv"):
    """火山引擎 V4 HMAC-SHA256 签名。返回 Authorization 头。"""
    import hashlib
    import hmac
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    x_date = now.strftime("%Y%m%dT%H%M%SZ")
    short_date = x_date[:8]

    # 1. 规范化 query
    canonical_query = ""
    if query:
        items = sorted((k, "".join(v) if isinstance(v, list) else str(v)) for k, v in query.items())
        canonical_query = "&".join(f"{urllib.parse.quote(k, safe='-_.~')}={urllib.parse.quote(v, safe='-_.~')}" for k, v in items)

    # 2. 签名头
    signed_headers = "content-type;host;x-date"
    content_type = "application/json"

    # 3. 拼 canonical request
    payload_hash = hashlib.sha256(body_bytes).hexdigest()
    canonical_request = "\n".join([
        method,
        path,
        canonical_query,
        f"content-type:{content_type}",
        f"host:{host}",
        f"x-date:{x_date}",
        "",
        signed_headers,
        payload_hash,
    ])

    # 4. 拼 string to sign
    credential_scope = f"{short_date}/{region}/{service}/ak-request"
    hashed_canonical = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
    string_to_sign = f"HMAC-SHA256\n{x_date}\n{credential_scope}\n{hashed_canonical}"

    # 5. 计算签名
    k_date = hmac.new(sk.encode("utf-8"), short_date.encode("utf-8"), hashlib.sha256).digest()
    k_region = hmac.new(k_date, region.encode("utf-8"), hashlib.sha256).digest()
    k_service = hmac.new(k_region, service.encode("utf-8"), hashlib.sha256).digest()
    k_signing = hmac.new(k_service, b"ak-request", hashlib.sha256).digest()
    signature = hmac.new(k_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    # 6. 拼 Authorization
    return (
        f"HMAC-SHA256 Credential={ak}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )


def _call_jimeng(cfg, prompt, ratio, resolution):
    """火山引擎即梦（jimeng）。同步模式 CVProcess。"""
    ak = cfg.get("ak") or cfg.get("access_key") or ""
    sk = cfg.get("sk") or cfg.get("secret_key") or ""
    model = cfg.get("model") or "jimeng-4.5"
    width, height = parse_ratio(ratio, "1024x1792")
    # 分辨率：1k/2k 映射到 jimeng 的 req_key 后缀或 width 倍率
    if str(resolution).lower() == "2k":
        width, height = width * 2, height * 2

    body = json.dumps({
        "req_key": model,
        "prompt": prompt,
        "width": width,
        "height": height,
        "return_url": True,
    }).encode("utf-8")

    host = "visual.volcengineapi.com"
    path = "/"
    auth = _volc_v4_sign("POST", host, path, {}, body, ak, sk)

    status, text = _http_post_json(
        f"https://{host}{path}",
        {
            "Authorization": auth,
            "Content-Type": "application/json",
            "X-Date": "",  # 签名里已带
        },
        body,
    )
    data = json.loads(text)
    # 火山引擎返回结构: {"code":10000, "data":{"image_urls":[...]}, ...}
    if data.get("code") not in (10000, 0, "10000"):
        msg = data.get("message") or data.get("msg") or text[:300]
        raise RuntimeError(f"即梦失败 code={data.get('code')}: {msg}")
    inner = data.get("data") or {}
    urls = inner.get("image_urls") or []
    if not urls:
        b64_list = inner.get("binary_data_base64") or []
        if b64_list:
            return {"b64": b64_list[0], "mime": "image/png"}
        raise RuntimeError(f"即梦返回无图: {text[:300]}")
    return {"url": urls[0], "mime": "image/png"}


# -------- runninghub 异步任务 --------
def _call_runninghub(cfg, prompt, ratio, resolution, max_wait=180):
    """runninghub.cn 提交任务 + 轮询拿图。"""
    api_key = cfg.get("api_key", "").strip()
    workflow_id = cfg.get("model") or cfg.get("workflow_id") or ""
    base_url = cfg.get("base_url") or "https://www.runninghub.cn"
    if not api_key or not workflow_id:
        raise RuntimeError("runninghub 需要 api_key 和 workflow_id（即 model 字段）")

    # 1. 提交
    submit_url = base_url.rstrip("/") + "/api/v1/run"
    submit_body = json.dumps({
        "apiKey": api_key,
        "workflowId": workflow_id,
        "inputs": {
            "prompt": prompt,
            "ratio": ratio or "9:16",
            "resolution": resolution or "1k",
        },
    }).encode("utf-8")
    status, text = _http_post_json(submit_url, {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + api_key,
    }, submit_body)
    sub = json.loads(text)
    task_id = sub.get("data", {}).get("taskId") or sub.get("taskId") or sub.get("data")
    if not task_id:
        raise RuntimeError(f"runninghub 提交失败: {text[:300]}")
    if isinstance(task_id, dict):
        task_id = task_id.get("taskId") or str(task_id)

    # 2. 轮询
    poll_url = base_url.rstrip("/") + f"/api/v1/status/{task_id}"
    import time as _time
    deadline = _time.time() + max_wait
    while _time.time() < deadline:
        _time.sleep(3)
        try:
            _, ptext = _http_get_json(poll_url, {"Authorization": "Bearer " + api_key})
            pres = json.loads(ptext)
        except RuntimeError:
            continue
        state = (pres.get("data") or {}).get("status") or pres.get("status") or ""
        if state in ("SUCCESS", "success", "completed", "COMPLETED"):
            outputs = (pres.get("data") or {}).get("outputs") or pres.get("outputs") or []
            if outputs:
                # runninghub 输出形如 [{"nodeId": "...", "field": "image", "value": "https://..."}]
                for o in outputs:
                    val = o.get("value") if isinstance(o, dict) else o
                    if isinstance(val, str) and (val.startswith("http") or val.startswith("data:")):
                        if val.startswith("data:image"):
                            import base64
                            b64 = val.split(",", 1)[1]
                            return {"b64": b64, "mime": "image/png"}
                        return {"url": val, "mime": "image/png"}
            raise RuntimeError(f"runninghub 完成但无图: {ptext[:300]}")
        if state in ("FAILED", "failed", "error"):
            raise RuntimeError(f"runninghub 任务失败: {ptext[:300]}")
    raise RuntimeError(f"runninghub 任务 {task_id} 超时（{max_wait}s）")


def image_dispatcher(image_cfg, prompt, ratio="9:16", resolution="1k"):
    """根据 image_cfg.provider 派发到对应 provider。"""
    provider = image_cfg.get("provider", "gpt_image")
    if provider in ("gpt_image", "modelscope", "custom_image", "openai"):
        # OpenAI 兼容协议
        width, height = parse_ratio(ratio, "1024x1792")
        size = f"{width}x{height}"
        return call_image_gen(image_cfg, prompt, size=size)
    if provider == "jimeng":
        return _call_jimeng(image_cfg, prompt, ratio, resolution)
    if provider == "runninghub":
        return _call_runninghub(image_cfg, prompt, ratio, resolution)
    raise RuntimeError(f"未知出图 provider: {provider}")


# ============================================================
# 火山引擎 TTS — 真值函数（参考 STORY ZC 37857-L37857.js:1-219）
#   POST {L5}，header X-Api-Key + X-Api-Resource-Id (seed-tts-1.0/2.0)
#   响应：NDJSON 流，code=0 → data:base64(audio/mp3)
# ============================================================
VOLC_TTS_URL = "https://openspeech.bytedance.com/api/v1/tts"

def _volc_tts_resource(speaker):
    """speaker id 后缀 '_2.0' / '_moon_bigtts' / '_mars_bigtts' 等映射到 seed-tts-2.0；其他 → 1.0"""
    sp = (speaker or "").lower()
    if "2.0" in sp or "moon" in sp:
        return "seed-tts-2.0"
    return "seed-tts-1.0"

def _volc_tts_synthesize(api_key, text, speaker, idx, speed=1.0):
    """调火山豆包语音 TTS 单句合成，返回 {idx, ok, audio_bytes, text, error}。
    协议：POST https://openspeech.bytedance.com/api/v1/tts
      header: X-Api-Key, X-Api-Resource-Id=seed-tts-1.0/2.0
      body: {app:{appid,token,cluster}, user:{uid}, audio:{voice_type,encoding,speed_rate,...},
             request:{reqid,text,operation:"query",with_timestamp,extra_voice_config}}
    注：STORY 用 `req_params` 简化封装，最终在网关层展开成上面这套协议。这里直接发展开版。"""
    speed_rate = max(0.5, min(2.0, float(speed)))
    body_obj = {
        "app": {
            "appid": "default",
            "token": api_key,
            "cluster": _volc_tts_resource(speaker),
        },
        "user": {"uid": "app074_volcengine"},
        "audio": {
            "voice_type": speaker,
            "encoding": "mp3",
            "speed_rate": speed_rate,
            "volume_rate": 1.0,
            "pitch_rate": 0,
        },
        "request": {
            "reqid": str(uuid.uuid4()),
            "text": text,
            "text_type": "plain",
            "operation": "query",
            "with_timestamp": "1",
        },
    }
    body_bytes = json.dumps(body_obj, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        VOLC_TTS_URL,
        data=body_bytes,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer; {api_key}",
            "X-Api-Key": api_key,
            "X-Api-Request-Id": str(uuid.uuid4()),
            "X-Api-Resource-Id": _volc_tts_resource(speaker),
            "Connection": "keep-alive",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status = resp.status
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")[:200]
        return {"idx": idx, "ok": False, "text": text, "error": f"火山 TTS HTTP {e.code}: {err_body}"}
    except Exception as e:
        return {"idx": idx, "ok": False, "text": text, "error": f"火山 TTS 网络错误: {e}"}
    if status >= 400:
        return {"idx": idx, "ok": False, "text": text, "error": f"火山 TTS HTTP {status}: {raw[:200]}"}
    # 解析 NDJSON（参考 ZC.r）
    audio_chunks = []
    last_error = None
    total_len = 0
    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        code = obj.get("code", 0)
        if code == 0:
            data_b64 = obj.get("data")
            if isinstance(data_b64, str) and data_b64:
                chunk = base64.b64decode(data_b64)
                audio_chunks.append(chunk)
                total_len += len(chunk)
        elif code == 20000000:  # 火山流式结束标记
            continue
        else:
            last_error = obj.get("message") or obj.get("msg") or f"TTS 错误 code={code}"
    if last_error and not audio_chunks:
        return {"idx": idx, "ok": False, "text": text, "error": f"火山 TTS: {last_error}"}
    if total_len == 0:
        return {"idx": idx, "ok": False, "text": text, "error": "火山 TTS 返回空音频"}
    audio = b"".join(audio_chunks)
    return {"idx": idx, "ok": True, "text": text, "audio_bytes": audio}


# ============================================================
# MiniMax TTS — 真值函数（参考 STORY Y0 38231-L38231.js:1-169）
#   POST {_m}/v1/t2a_v2，header Authorization Bearer
#   响应：{base_resp, data:{audio:"hex..."}}
# ============================================================
MINIMAX_TTS_URL = "https://api.minimax.chat/v1/t2a_v2"

def _minimax_tts_synthesize(api_key, text, voice_id, idx, speed=1.0, mx_cfg=None):
    """调 MiniMax TTS 单句合成，返回 {idx, ok, audio_bytes, text, error}。"""
    model = (mx_cfg or {}).get("model") or "speech-02-hd"
    rate = max(0.5, min(2.0, float(speed)))
    body_obj = {
        "model": model,
        "text": text,
        "stream": False,
        "language_boost": "auto",
        "voice_setting": {"voice_id": voice_id, "speed": rate, "vol": 1, "pitch": 0},
        "audio_setting": {"sample_rate": 32000, "bitrate": 128000, "format": "mp3", "channel": 1},
        "output_format": "hex",
    }
    body_bytes = json.dumps(body_obj, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        MINIMAX_TTS_URL,
        data=body_bytes,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status = resp.status
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")[:200]
        return {"idx": idx, "ok": False, "text": text, "error": f"MiniMax HTTP {e.code}: {err_body}"}
    except Exception as e:
        return {"idx": idx, "ok": False, "text": text, "error": f"MiniMax 网络错误: {e}"}
    if status >= 400:
        return {"idx": idx, "ok": False, "text": text, "error": f"MiniMax HTTP {status}: {raw[:200]}"}
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return {"idx": idx, "ok": False, "text": text, "error": "MiniMax 响应非 JSON"}
    br = obj.get("base_resp") or {}
    if br.get("status_code", 0) != 0:
        return {"idx": idx, "ok": False, "text": text, "error": f"MiniMax: {br.get('status_msg', '未知错误')}"}
    hex_audio = ((obj.get("data") or {}).get("audio") or "").strip()
    if not hex_audio:
        return {"idx": idx, "ok": False, "text": text, "error": "MiniMax 响应缺少 audio 字段"}
    try:
        audio = bytes.fromhex(hex_audio)
    except ValueError:
        return {"idx": idx, "ok": False, "text": text, "error": "MiniMax audio 字段非 hex"}
    return {"idx": idx, "ok": True, "text": text, "audio_bytes": audio}


# ============================================================
# 火山 ASR — 真值函数（参考 STORY H6 40002-L40002.js + index-CXUXw7CE.js:39983-40068）
#   submit: POST .../auc/bigmodel/submit → 20000000 立即成功 / 否则错误
#   query:  POST .../auc/bigmodel/query  → 20000000 完成 / 20000001|002 处理中
#   响应：result.utterances[]=[{text, start_time(ms), end_time(ms), words[]}]
# ============================================================
VOLC_ASR_SUBMIT_URL = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit"
VOLC_ASR_QUERY_URL = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/query"
VOLC_ASR_RESOURCE_ID = "volc.seedasr.auc"

def _volc_asr_transcribe(api_key, audio_path, timeout_sec=60):
    """调火山录音文件识别（bigmodel），返回 segments[{text, start, end}] 秒。
    失败抛 RuntimeError，调用方回退到 chars/sec 估算。"""
    if not api_key:
        raise RuntimeError("缺少火山 API Key（设置 → TTS 配音 → 火山引擎）")
    p = Path(audio_path)
    if not p.exists():
        raise RuntimeError(f"音频文件不存在: {audio_path}")
    audio_bytes = p.read_bytes()
    ext = p.suffix.lstrip(".").lower() or "mp3"
    if ext not in ("mp3", "wav", "ogg", "raw"):
        ext = "mp3"
    audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
    req_id = str(uuid.uuid4())
    submit_headers = {
        "Content-Type": "application/json",
        "X-Api-Key": api_key,
        "X-Api-Resource-Id": VOLC_ASR_RESOURCE_ID,
        "X-Api-Request-Id": req_id,
        "X-Api-Sequence": "-1",
    }
    submit_body = json.dumps({
        "user": {"uid": "app074"},
        "audio": {"data": audio_b64, "format": ext},
        "request": {
            "model_name": "bigmodel",
            "show_utterances": True,
            "enable_punc": False,
            "enable_itn": False,
        },
    }).encode("utf-8")
    req = urllib.request.Request(VOLC_ASR_SUBMIT_URL, data=submit_body, method="POST", headers=submit_headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            submit_status_code = next((v for k, v in resp.headers.items()
                                      if k.lower() == "x-api-status-code"), "")
            submit_body_resp = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"火山 ASR submit HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:200]}")
    except Exception as e:
        raise RuntimeError(f"火山 ASR submit 网络错误: {e}")
    if submit_status_code != "20000000":
        raise RuntimeError(f"火山 ASR submit 失败（status={submit_status_code}）：{submit_body_resp[:200]}")
    # 轮询
    poll_headers = {
        "Content-Type": "application/json",
        "X-Api-Key": api_key,
        "X-Api-Resource-Id": VOLC_ASR_RESOURCE_ID,
        "X-Api-Request-Id": req_id,
    }
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        time.sleep(2)
        try:
            poll_req = urllib.request.Request(VOLC_ASR_QUERY_URL, data=b"{}", method="POST", headers=poll_headers)
            with urllib.request.urlopen(poll_req, timeout=30) as resp:
                poll_code = next((v for k, v in resp.headers.items()
                                  if k.lower() == "x-api-status-code"), "")
                poll_body = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"火山 ASR query HTTP {e.code}")
        except Exception as e:
            raise RuntimeError(f"火山 ASR query 网络错误: {e}")
        if poll_code in ("20000001", "20000002"):
            continue
        if poll_code == "20000000":
            try:
                obj = json.loads(poll_body)
            except json.JSONDecodeError:
                raise RuntimeError(f"火山 ASR 返回非 JSON: {poll_body[:200]}")
            utterances = ((obj.get("result") or {}).get("utterances") or [])
            if not utterances:
                raise RuntimeError("火山 ASR 未返回任何句子")
            return [
                {
                    "text": (u.get("text") or "").strip(),
                    "start": float(u.get("start_time", 0)) / 1000.0,
                    "end": float(u.get("end_time", 0)) / 1000.0,
                }
                for u in utterances if (u.get("text") or "").strip()
            ]
        raise RuntimeError(f"火山 ASR query 失败（status={poll_code}）：{poll_body[:200]}")
    raise RuntimeError("火山 ASR 轮询超时")


def parse_llm_json(text):
    """从 LLM 文本里抠出 JSON 对象/数组（即使带了 ``` 或前后说明）。"""
    text = text.strip()
    # 去 markdown 包裹
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    # 找第一个 { 或 [
    for opener, closer in [("{", "}"), ("[", "]")]:
        s = text.find(opener)
        if s < 0:
            continue
        # 从 s 开始尝试匹配（考虑嵌套）
        depth = 0
        in_str = False
        escape = False
        for i in range(s, len(text)):
            c = text[i]
            if escape:
                escape = False
                continue
            if c == "\\":
                escape = True
                continue
            if c == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if c == opener:
                depth += 1
            elif c == closer:
                depth -= 1
                if depth == 0:
                    candidate = text[s : i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break
    raise ValueError(f"LLM 返回值不是合法 JSON: {text[:200]}")


def extract_after_marker(text, marker):
    """STORY ZD 风格：按 marker 切分。marker 后面的就是「整理后全文」。"""
    idx = text.find(marker)
    if idx < 0:
        return None
    after = text[idx + len(marker):].lstrip("\n\r \t　")
    return after.strip() if after.strip() else None


# ====================== STORY 图文 Step 0/元/2/3 helpers ======================
# 全部从 Storybound 1.24.0 focused snippets 移植，简化掉 retry loop / 复活 / 敏感词字典。

# 画面风格 UI label → 出图 prompt 里的英文 token（STYLE 前缀/后缀合并）
STYLE_TOKENS = {
    "黑白摄影":   {"prefix": "black and white photography, documentary style, high contrast", "suffix": "", "allow_color": False},
    "写实彩色":   {"prefix": "realistic photography, vivid natural colors, sharp details", "suffix": "", "allow_color": True},
    "油画风格":   {"prefix": "oil painting style, impressionistic brushstrokes, rich texture", "suffix": "", "allow_color": True},
    "现代电影":   {"prefix": "modern cinematic photography, Asian color grading, cinematic lighting", "suffix": "", "allow_color": True},
    "古风电影":   {"prefix": "ancient Chinese cinema, epic historical atmosphere, period-accurate costuming", "suffix": "", "allow_color": True},
    "复古胶片":   {"prefix": "retro 1980s film grain, nostalgic warm tones, vintage photography", "suffix": "", "allow_color": True},
    "水彩治愈":   {"prefix": "soft watercolor painting, healing pastel tones, gentle brushstrokes", "suffix": "", "allow_color": True},
    "杂志漫画":   {"prefix": "pop art comic style, bold flat colors, dramatic composition", "suffix": "", "allow_color": True},
    "皮克斯 3D": {"prefix": "Pixar 3D animation, cinematic render, soft volumetric lighting", "suffix": "", "allow_color": True},
    "中国水墨":   {"prefix": "Chinese ink wash painting, literati aesthetic, minimalist brushwork", "suffix": "", "allow_color": False},
    "民间故事工笔风": {"prefix": "Chinese folk story fine-brush painting, intricate details, traditional gongi-bi technique", "suffix": "", "allow_color": True},
    "宫 1 十":    {"prefix": "Chinese palace style, gentle white waves aesthetic, soft warm palette", "suffix": "", "allow_color": True},
    "黑暗橙焰":   {"prefix": "dark orange flame aesthetic, intense dramatic contrast, knowledge intensity", "suffix": "", "allow_color": True},
    "自定义":     {"prefix": "cinematic photography", "suffix": "", "allow_color": True},
}


def step0_pre_review(llm_settings, reference):
    """Step 0：调 LLM「整理」原文（ZD 语义：clean not gate）。
    返回 {reviewed_text, cleaned(bool), original_length, cleaned_length, notes}。
    LLM 不按 marker 输出 → 兜底用原文。"""
    if not reference.strip():
        return {"reviewed_text": "", "cleaned": False, "original_length": 0, "cleaned_length": 0, "notes": "原文为空"}
    sys_mod = load_prompt_module_raw("step0_pre_review.py")
    sys_p = sys_mod["text"]
    marker = sys_mod["marker"]
    user_p = f"## 原文\n{reference.strip()[:8000]}"
    try:
        text = call_llm(llm_settings, sys_p, user_p)
    except (RuntimeError, ValueError) as e:
        return {
            "reviewed_text": reference.strip(),
            "cleaned": False,
            "original_length": len(reference.strip()),
            "cleaned_length": len(reference.strip()),
            "notes": f"LLM 调用失败，原文进入下一步：{e}",
        }
    after = extract_after_marker(text, marker)
    if after is None:
        # LLM 没按格式输出（兜底：原文进下一步）
        return {
            "reviewed_text": reference.strip(),
            "cleaned": False,
            "original_length": len(reference.strip()),
            "cleaned_length": len(reference.strip()),
            "notes": "LLM 未按 marker 格式输出，已用原文",
        }
    # 过短 / 缩成 < 原文 30% → 视为摘要失败，兜底原文（STORY WD 函数的行为）
    if len(after) < 20 or (len(reference.strip()) >= 200 and len(after) < len(reference.strip()) * 0.3):
        return {
            "reviewed_text": reference.strip(),
            "cleaned": False,
            "original_length": len(reference.strip()),
            "cleaned_length": len(after),
            "notes": "整理稿疑似摘要，已用原文",
        }
    return {
        "reviewed_text": after,
        "cleaned": True,
        "original_length": len(reference.strip()),
        "cleaned_length": len(after),
        "notes": f"已整理（{len(reference.strip())} → {len(after)} 字）",
    }


def step1_meta(llm_settings, title, content, hooks, track):
    """Step 1 元信息：title / short_title / summary / tags / comments / cover_image_prompts。
    字段定义照搬 Ag 真值结构。"""
    if not content.strip():
        return {"title": title.strip()[:22], "short_title": "", "summary": "", "tags": [], "comments": [], "cover_image_prompts": []}
    sys_p = load_prompt_module("step1_meta.py")
    hooks_str = " / ".join(hooks) if hooks else "无"
    user_p = (
        f"## 标题\n{title.strip() or '(未填)'}\n\n"
        f"## 赛道\n{track}\n\n"
        f"## 黄金 3 秒钩子\n{hooks_str}\n\n"
        f"## 改写后文案\n{content.strip()[:4000]}"
    )
    try:
        text = call_llm(llm_settings, sys_p, user_p)
    except (RuntimeError, ValueError) as e:
        return {"title": title.strip()[:22], "short_title": "", "summary": content.strip()[:180], "tags": [], "comments": [], "cover_image_prompts": [], "notes": f"LLM 失败：{e}"}
    try:
        result = parse_llm_json(text)
    except ValueError:
        return {"title": title.strip()[:22], "short_title": "", "summary": content.strip()[:180], "tags": [], "comments": [], "cover_image_prompts": [], "notes": "LLM 未返回 JSON"}
    # 兜底
    result.setdefault("title", title.strip()[:22])
    result.setdefault("short_title", "")
    result.setdefault("summary", "")
    result.setdefault("tags", [])
    result.setdefault("comments", [])
    result.setdefault("cover_image_prompts", [])
    for k in ("tags", "comments", "cover_image_prompts"):
        if not isinstance(result[k], list):
            result[k] = []
    # 强约束：short_title ≤ 16 字 + 去标点空格
    st = re.sub(r"[^\w一-鿿]", "", result.get("short_title", ""))[:16]
    result["short_title"] = st
    return result


def step2_split(llm_settings, content, target_shots=None, target_words=None):
    """Step 2 智能分镜：PA 真值算法的简化版。
    真值：LLM 输出尾部锚点（10-20 字精确原文）→ 锚点匹配原文切片。
    简化：单轮 LLM 调用 → 解析锚点数组 → 锚点切片；匹配失败回退到按段落+标点切。
    返回 {shots, notes, match_rate}。match_rate: 0~1，LLM 锚点匹配率（用于前端 UI 显示）。"""
    text = content.strip()
    if not text:
        return {"shots": [], "notes": "", "match_rate": 0}

    sys_p = load_prompt_module("step2_split.py")

    # 计算期望分镜数（参考 STORY z0 函数的 count min/max 逻辑）
    text_len = len(text)
    if target_shots and int(target_shots) > 0:
        expected = int(target_shots)
    else:
        # 默认：45 字/镜
        expected = max(1, round(text_len / 45))

    user_p = (
        f"## 目标分镜数\n{expected}\n\n"
        f"## 原文\n{text}\n\n"
        f"请输出 JSON 字符串数组，每项 10-20 字，是该分镜在原文中的尾部锚点（精确含标点）。"
    )
    anchors = None
    notes = ""
    match_rate = 0
    try:
        out = call_llm(llm_settings, sys_p, user_p)
        try:
            arr = parse_llm_json(out)
        except ValueError:
            arr = None
        if isinstance(arr, list) and arr:
            # 校验：每项是 10-20 字符串
            clean = [str(x).strip() for x in arr if isinstance(x, str) and 10 <= len(x.strip()) <= 20]
            if clean:
                # 按锚点切片原文
                cuts = []
                cursor = 0
                miss = 0
                for a in clean:
                    pos = text.find(a, cursor)
                    if pos < 0:
                        pos = text.find(a)
                    if pos < 0:
                        miss += 1
                        continue
                    # 这一镜的终点 = 锚点末尾
                    end = pos + len(a)
                    if end > cursor:
                        seg = text[cursor:end].strip()
                        if seg:
                            cuts.append(seg)
                        cursor = end
                # 收尾
                tail = text[cursor:].strip()
                if tail:
                    cuts.append(tail)
                if clean:
                    match_rate = round((len(clean) - miss) / len(clean), 3)
                if miss / max(1, len(clean)) < 0.3 and cuts:
                    anchors = cuts
                    notes = f"LLM 锚点切分（{len(cuts)} 镜，{miss}/{len(clean)} 个锚点未匹配，匹配率 {match_rate*100:.0f}%）"
    except (RuntimeError, ValueError) as e:
        notes = f"LLM 失败，回退段落切分：{e}"

    # 兜底：按段落 + 标点切
    if anchors is None:
        import re as _re
        paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
        anchors = []
        for p in paragraphs:
            parts = _re.split(r"(?<=[。！？!?；;])\s*", p)
            anchors.extend([s.strip() for s in parts if s.strip()])
        notes = (notes + "；" if notes else "") + f"段落+标点切分（{len(anchors)} 镜，匹配率 —）"

    # 兜底：target_words 强制拆分
    if target_words and int(target_words) > 0:
        tw = int(target_words)
        normalized = []
        for s in anchors:
            if len(s) <= tw:
                normalized.append(s)
                continue
            for i in range(0, len(s), tw):
                piece = s[i : i + tw].strip()
                if piece:
                    normalized.append(piece)
        anchors = normalized

    shots = [{"idx": i + 1, "text": s, "chars": len(s)} for i, s in enumerate(anchors) if s.strip()]
    return {"shots": shots, "notes": notes, "match_rate": match_rate}


def step3_image_prompts(llm_settings, shots, track, style_label, story_context="", character_card=None):
    """Step 3 出图 prompt：mS 风格的简化版。
    真值：分批并发 + 风格前后缀 + 角色档案 + 敏感词字典。
    简化：串行分批 + 风格前缀/后缀（STYLE_TOKENS）+ 角色档案（c$ 格式化）+ SENSITIVE_DICT。
    character_card（dict）来自 Step 1 meta.characters[0]，含 identity + ageStages[stage/appearance/eraVisuals]。
    返回 [{idx, text, desc_prompt}]，desc_prompt 是中文视觉描述。"""
    if not shots:
        return []

    sys_p = load_prompt_module("step3_image_prompt.py")
    style = STYLE_TOKENS.get(style_label, STYLE_TOKENS["写实彩色"])
    style_prefix = style["prefix"]
    style_suffix = style["suffix"]
    allow_color = style["allow_color"]

    # c$ 格式化角色档案（Storybound index-CXUXw7CE.js:902189 真值复制）
    char_block = ""
    if character_card and character_card.get("identity") and isinstance(character_card.get("ageStages"), list):
        try:
            from prompts.step3_image_prompt import format_character_card
            char_block = format_character_card(character_card)
        except Exception:
            char_block = ""

    BATCH = 4  # 简化版每批 4 个（STORY yi 估计是 5-8，这里保守点）
    all_results = {}
    for i in range(0, len(shots), BATCH):
        batch = shots[i : i + BATCH]
        shots_json = json.dumps(
            [{"id": s["idx"], "cap": s["text"][:200]} for s in batch],
            ensure_ascii=False,
        )
        char_section = f"\n## character_card\n{char_block}\n\n" if char_block else ""
        user_p = (
            f"## Track\n{track or '通用故事'}\n\n"
            f"## style_prefix\n{style_prefix}\n\n"
            f"## style_suffix\n{style_suffix or '(空)'}\n\n"
            f"## style_allow_color\n{'true' if allow_color else 'false'}\n\n"
            f"## story_context\n{story_context or '通用'}\n\n"
            f"{char_section}"
            f"## shots\n{shots_json}\n\n"
            f"返回 JSON 数组（长度 {len(batch)}），每项含 id/cap/desc_prompt。"
        )
        try:
            text = call_llm(llm_settings, sys_p, user_p)
            arr = parse_llm_json(text)
        except (RuntimeError, ValueError, json.JSONDecodeError):
            arr = None
        if isinstance(arr, dict):
            arr = [arr]
        if isinstance(arr, list):
            for item in arr:
                if not isinstance(item, dict):
                    continue
                idx = item.get("id")
                p = str(item.get("desc_prompt", "")).strip()
                if idx is None or not p:
                    continue
                # 强约束：末尾追加 9:16 后缀（如果漏了）
                tail = "竖屏构图，9:16 画幅比例，无文字、无水印"
                if "9:16" not in p and "竖屏" not in p:
                    p = p.rstrip("。. ") + "。" + tail
                # 禁色（如黑白）
                if not allow_color:
                    import re as _re
                    p = _re.sub(r"(红色|蓝色|绿色|黄色|紫色|橙色|粉色|金色|银色|白色|黑色|暖色|冷色)", "中性色调", p)
                all_results[int(idx)] = p

    # 兜底：未生成的用模板
    for s in shots:
        if s["idx"] not in all_results:
            all_results[s["idx"]] = (
                f"{style_prefix}，{s['text'][:30]}的画面，竖屏构图，9:16 画幅比例，无文字、无水印"
            )

    return [
        {"idx": s["idx"], "text": s["text"], "desc_prompt": all_results.get(s["idx"], "")}
        for s in shots
    ]


def load_module_with_extras(rel_path):
    """载 module 并返回 {text, marker?}。step0 用 marker，其他只读 text。"""
    if rel_path == "step0_pre_review.py":
        return {"text": load_prompt_module(rel_path), "marker": "---整理稿---"}
    return {"text": load_prompt_module(rel_path)}


# 兼容旧名
def load_prompt_module_raw(rel_path):
    return load_module_with_extras(rel_path)


def load_tasks():
    p = DATA_DIR / "tasks.json"
    if not p.exists():
        return {"tasks": []}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"tasks": []}


def save_tasks(data):
    p = DATA_DIR / "tasks.json"
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def save_task_record(record):
    """存一条任务到 tasks.json。"""
    data = load_tasks()
    data["tasks"].insert(0, record)
    data["tasks"] = data["tasks"][:100]
    save_tasks(data)


def build_cover_prompt(llm_settings, title, content, style, hooks):
    """让 LLM 根据标题/文案/风格/钩子写一段英文出图 prompt。"""
    hooks_str = " / ".join(hooks) if hooks else ""
    style_str = style or "现代电影"
    sys_p = "你是一名短视频封面 prompt 工程师，根据用户提供的中文信息写一段适合图像生成的英文 prompt。直接返回 prompt 文本，不要任何解释、Markdown、引号。"
    user_p = (
        f"## 标题\n{title.strip() or '(未填)'}\n\n"
        f"## 内容赛道\n自动\n\n"
        f"## 画面风格\n{style_str}\n\n"
        f"## 黄金 3 秒钩子\n{hooks_str}\n\n"
        f"## 文案片段（前 200 字）\n{content.strip()[:200]}\n\n"
        f"要求：\n"
        f"1. 输出 1 段不超过 120 词的英文 prompt\n"
        f"2. 描述主体场景、构图、光线、镜头、情绪、画面风格\n"
        f"3. 不要出现中文、不要任何额外说明\n"
    )
    text = call_llm(llm_settings, sys_p, user_p)
    # 去掉可能的引号
    text = text.strip().strip('"').strip("'").strip()
    return text


def save_cover_image(b64_or_url, mime="image/png"):
    """把 base64 或 URL 落盘到 data/covers/ 下，返回相对 URL。"""
    covers_dir = DATA_DIR / "covers"
    covers_dir.mkdir(parents=True, exist_ok=True)
    fname = f"cover_{int(time.time())}_{os.urandom(3).hex()}.png"
    fpath = covers_dir / fname
    if b64_or_url.startswith("http://") or b64_or_url.startswith("https://"):
        # 下载
        req = urllib.request.Request(b64_or_url)
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
        fpath.write_bytes(data)
    else:
        # base64
        import base64
        fpath.write_bytes(base64.b64decode(b64_or_url))
    return f"/covers/{fname}"


def call_llm(settings, system_prompt, user_prompt):
    protocol = settings.get("protocol", "openai")
    base_url = settings["base_url"].rstrip("/")
    api_key = settings["api_key"]
    model = settings["model"]

    if protocol == "anthropic":
        url = base_url
        if base_url.endswith("/v1/messages"):
            pass
        elif base_url.endswith("/v1"):
            url = base_url + "/messages"
        else:
            url = base_url + "/v1/messages"
        payload = {
            "model": model,
            "max_tokens": 8192,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
    else:  # openai-compatible
        url = base_url
        if base_url.endswith("/v1/chat/completions"):
            pass
        elif base_url.endswith("/v1"):
            url = base_url + "/chat/completions"
        else:
            url = base_url + "/v1/chat/completions"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 8192,
        }
        headers = {
            "Authorization": "Bearer " + api_key,
            "content-type": "application/json",
        }

    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"LLM 调用失败 HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:500]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"LLM 连接失败: {e.reason}")

    data = json.loads(body)
    if protocol == "anthropic":
        content = data.get("content", [])
        text = "".join(block.get("text", "") for block in content if block.get("type") == "text")
    else:
        choices = data.get("choices", [])
        if not choices:
            raise RuntimeError(f"LLM 返回空 choices: {body[:300]}")
        text = choices[0].get("message", {}).get("content", "")
    return text.strip()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # pythonw.exe 没有控制台，stderr 可能为 NULL，写入会抛异常 → handler 线程崩溃
        # 这里只写文件，不写 stderr
        try:
            with open(DATA_DIR / "access.log", "a", encoding="utf-8") as f:
                f.write(f"[{self.log_date_time_string()}] {format % args}\n")
        except OSError:
            pass

    def _json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.send_header("cache-control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path, ctype):
        if not path.exists():
            self.send_error(404)
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("content-type", ctype)
        self.send_header("content-length", str(len(body)))
        self.send_header("cache-control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self._file(ROOT / "index.html", "text/html; charset=utf-8")
            return
        if self.path == "/settings.html":
            self._file(ROOT / "settings.html", "text/html; charset=utf-8")
            return
        if self.path == "/tasks.html" or self.path == "/tasks":
            self._file(ROOT / "tasks.html", "text/html; charset=utf-8")
            return
        if self.path.startswith("/assets/"):
            # /assets/<sub>/<file> — 静态资源（CSS / JS / 图标）
            rel = self.path.lstrip("/")
            f = ROOT / rel
            if f.exists() and f.is_file():
                ext = f.suffix.lower()
                mime = {
                    ".css": "text/css; charset=utf-8",
                    ".js": "application/javascript; charset=utf-8",
                    ".svg": "image/svg+xml",
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".webp": "image/webp",
                    ".ico": "image/x-icon",
                }.get(ext, "application/octet-stream")
                self._file(f, mime)
            else:
                self._json(404, {"error": f"资源不存在: {rel}"})
            return
        if self.path.startswith("/covers/"):
            self._file(DATA_DIR / self.path.lstrip("/"), "image/png")
            return
        if self.path.startswith("/api/task_image/"):
            # /api/task_image/<task_id>/<filename> → data/tasks/<task_id>/covers/<filename>
            rel = self.path[len("/api/task_image/"):]
            img_path = DATA_DIR / "tasks" / rel
            if img_path.exists() and img_path.is_file():
                mime = "image/jpeg" if img_path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
                self._file(img_path, mime)
            else:
                self._json(404, {"error": "图片不存在"})
            return
        if self.path.startswith("/api/audio/"):
            # /api/audio/<task_id>/<file>.mp3 → data/tasks/<task_id>/audio/<file>
            rel = self.path[len("/api/audio/"):]
            audio_path = DATA_DIR / "tasks" / rel
            if audio_path.exists() and audio_path.is_file():
                self._file(audio_path, "audio/mpeg")
            else:
                self._json(404, {"error": "audio 不存在"})
            return
        if self.path.startswith("/tasks/"):
            # /tasks/<task_id>/<filename> — 让前端能 fetch 任务产物 JSON / 文本
            rel = self.path.lstrip("/")
            f = DATA_DIR / rel
            if f.exists() and f.is_file():
                self._file(f, "application/json; charset=utf-8" if f.suffix == ".json" else "text/plain; charset=utf-8")
            else:
                self._json(404, {"error": "文件不存在"})
            return
        if self.path == "/api/settings":
            self._json(200, public_settings())
            return
        if self.path == "/api/profiles":
            self._json(200, {"profiles": public_profiles(), "active_id": next((p["id"] for p in load_profiles() if p.get("enabled")), "")})
            return
        if self.path == "/api/levels":
            self._json(200, {
                "story": [{"key": k, "label": v["label"], "diff": v["diff"], "needs_reference": v["needs_reference"]} for k, v in STORY_LEVELS.items()],
                "user": [{"key": k, "label": v["label"], "diff": v["diff"], "needs_reference": v["needs_reference"]} for k, v in USER_LEVELS.items()],
            })
            return
        if self.path == "/api/providers":
            self._json(200, LLM_PROVIDERS)
            return
        if self.path == "/api/tasks":
            # 列出所有任务（参考 STORY ao 41484 的产物扫描）
            self._json(200, {"tasks": list_tasks()})
            return
        if self.path.startswith("/api/task/"):
            # /api/task/<task_id>
            task_id = self.path[len("/api/task/"):].strip("/")
            if not task_id:
                self._json(400, {"error": "task_id 不能为空"})
                return
            detail = get_task_detail(task_id)
            if not detail:
                self._json(404, {"error": f"任务不存在: {task_id}"})
                return
            self._json(200, detail)
            return
        self.send_error(404)

    def do_POST(self):
        length = int(self.headers.get("content-length", "0") or "0")
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        except ValueError:
            self._json(400, {"error": "请求体不是合法 JSON"})
            return

        if self.path == "/api/settings":
            try:
                save_settings(data)
            except ValueError as e:
                self._json(400, {"error": str(e)})
                return
            self._json(200, {"ok": True, "settings": public_settings()})
            return

        if self.path == "/api/profiles":
            # 接收 {profiles: [...]}；支持增量（保留未提交的 apiKey）
            try:
                incoming = data.get("profiles")
                if not isinstance(incoming, list):
                    raise ValueError("profiles 必须是数组")
                # 校验：至少 1 个 profile、至少 1 个 enabled
                if len(incoming) == 0:
                    raise ValueError("至少保留 1 个 profile")
                if not any(p.get("enabled") for p in incoming):
                    incoming[0]["enabled"] = True
                # 校验每个 profile 必填字段（如果是 active 状态，必须有 apiKey）
                active = next((p for p in incoming if p.get("enabled")), None)
                if active and not (active.get("apiKey") or "").strip():
                    raise ValueError("当前激活的 profile 必须填写 API Key")
                save_profiles(incoming)
            except ValueError as e:
                self._json(400, {"error": str(e)})
                return
            self._json(200, {"ok": True, "profiles": public_profiles()})
            return

        if self.path == "/api/test_llm":
            # 用请求里直接给的凭据做一次真实调用（不依赖 settings）
            provider = (data.get("provider") or "").strip()
            protocol = (data.get("protocol") or "openai").strip()
            base_url = (data.get("base_url") or "").strip().rstrip("/")
            api_key  = (data.get("api_key") or "").strip()
            model    = (data.get("model") or "").strip()
            if not (provider and base_url and api_key and model):
                self._json(400, {"ok": False, "error": "缺少 provider / base_url / api_key / model"})
                return
            test_settings = {
                "provider": provider, "protocol": protocol,
                "base_url": base_url, "api_key": api_key, "model": model,
            }
            try:
                t0 = time.time()
                text = call_llm(test_settings, "你是测试助手。请用一句中文回复「测试成功」即可，不要超过 10 个字。", "ping")
                elapsed = round(time.time() - t0, 1)
                self._json(200, {"ok": True, "text": text.strip(), "elapsed": elapsed})
            except (ValueError, RuntimeError) as e:
                self._json(200, {"ok": False, "error": str(e)})
            return

        if self.path == "/api/test_image":
            # 仅做字段完整性检查 + ping 阶段占位（真正出图测试在创建任务时再验）
            provider = (data.get("provider") or "").strip()
            s = load_settings()
            t0 = time.time()
            try:
                if provider == "jimeng":
                    jm = s.get("jimeng") or {}
                    if not (jm.get("session_id") or (jm.get("ak") and jm.get("sk"))):
                        raise ValueError("即梦 Session ID 未配置")
                elif provider == "gpt_image":
                    img = s.get("image") or {}
                    if not (img.get("api_key") and img.get("model") and img.get("base_url")):
                        raise ValueError("全能绘图 API Key / 模型 / Base URL 未配齐")
                elif provider == "modelscope":
                    ms = s.get("modelscope") or {}
                    if not ms.get("tokens"):
                        raise ValueError("魔搭 Access Token 未配置")
                elif provider == "runninghub":
                    rh = s.get("runninghub") or {}
                    if not rh.get("api_key"):
                        raise ValueError("RunningHub API Key 未配置")
                elif provider == "custom":
                    cu = s.get("custom_image") or {}
                    if not (cu.get("api_key") and cu.get("model") and cu.get("base_url")):
                        raise ValueError("自定义平台 Base URL / API Key / 模型 未配齐")
                else:
                    raise ValueError(f"未知 provider: {provider}")
                elapsed = round(time.time() - t0, 1)
                self._json(200, {"ok": True, "elapsed": elapsed, "provider": provider})
            except ValueError as e:
                self._json(200, {"ok": False, "error": str(e)})
            return

        if self.path == "/api/tasks/clear":
            try:
                tasks_p = DATA_DIR / "tasks.json"
                hist_p  = DATA_DIR / "history.json"
                if tasks_p.exists():
                    tasks_p.write_text("[]", encoding="utf-8")
                if hist_p.exists():
                    hist_p.write_text("[]", encoding="utf-8")
            except OSError as e:
                self._json(500, {"error": f"写入失败: {e}"})
                return
            self._json(200, {"ok": True})
            return

        if self.path == "/api/cover":
            try:
                s = load_settings()
                llm = resolve_active_llm_settings()
                if not llm.get("api_key"):
                    self._json(400, {"error": "未配置 LLM，请先到设置页填写"})
                    return
                # 按 provider 选 image 配置
                provider = (data.get("provider") or "").strip()
                if not provider:
                    provider = (s.get("image") or {}).get("provider", "gpt_image")
                if provider in ("gpt_image", "modelscope", "custom_image", "openai"):
                    img = s.get("image") or {}
                    if not img.get("api_key"):
                        self._json(400, {"error": "未配置出图 API（OpenAI 兼容通道）"})
                        return
                    ratio = img.get("ratio") or "9:16"
                    resolution = img.get("resolution") or "1k"
                    image_cfg = img
                elif provider == "jimeng":
                    img = s.get("jimeng") or {}
                    if not (img.get("ak") and img.get("sk")):
                        self._json(400, {"error": "未配置 jimeng（AK / SK 必填）"})
                        return
                    ratio = img.get("ratio") or "9:16"
                    resolution = img.get("resolution") or "1k"
                    image_cfg = img
                elif provider == "runninghub":
                    img = s.get("runninghub") or {}
                    if not (img.get("api_key") and img.get("workflow_id")):
                        self._json(400, {"error": "未配置 runninghub（api_key / workflow_id 必填）"})
                        return
                    ratio = img.get("ratio") or "9:16"
                    resolution = img.get("resolution") or "1k"
                    image_cfg = img
                else:
                    self._json(400, {"error": f"未知出图 provider: {provider}"})
                    return

                title = (data.get("title") or "").strip()
                content = (data.get("content") or "").strip()
                style = (data.get("style") or "现代电影").strip()
                hooks = data.get("hooks") or []
                if not content and not title:
                    self._json(400, {"error": "文案和标题至少填一个"})
                    return
                t0 = time.time()
                prompt = build_cover_prompt(llm, title, content, style, hooks)
                result = image_dispatcher(image_cfg, prompt, ratio=ratio, resolution=resolution)
                if "b64" in result:
                    cover_url = save_cover_image(result["b64"], result.get("mime", "image/png"))
                else:
                    cover_url = save_cover_image(result["url"], result.get("mime", "image/png"))
                elapsed = time.time() - t0
                self._json(200, {
                    "url": cover_url,
                    "prompt": prompt,
                    "elapsed": round(elapsed, 1),
                    "provider": provider,
                })
            except ValueError as e:
                self._json(400, {"error": str(e)})
            except RuntimeError as e:
                self._json(502, {"error": str(e)})
            return

        if self.path == "/api/rewrite":
            try:
                settings = resolve_active_llm_settings()
                if not settings.get("api_key"):
                    self._json(400, {"error": "未配置 API Key，请先到设置页填写"})
                    return
                line = data.get("line")
                level = data.get("level")
                viewpoint = data.get("viewpoint", "keep")
                reference = data.get("reference", "")
                topic = data.get("topic", "")
                ctx = {
                    "track":         data.get("track", ""),
                    "hooks":         data.get("hooks", []),
                    "sources":       data.get("sources", []),
                    "keywords":      data.get("keywords", ""),
                    "product":       data.get("product", ""),
                    "fixed_opening": data.get("fixed_opening", ""),
                    "tail_guide":    data.get("tail_guide", ""),
                    "extra":         data.get("extra", ""),
                }
                if line == "story":
                    if level not in STORY_LEVELS:
                        self._json(400, {"error": "未知 STORY 等级"})
                        return
                    system_prompt = load_prompt_module("story/base_rewrite.py")
                    user_prompt = build_story_prompt(level, viewpoint, reference, ctx)
                elif line == "user":
                    if level not in USER_LEVELS:
                        self._json(400, {"error": "未知 USER 等级"})
                        return
                    system_prompt = load_prompt_module("hook.py")
                    user_prompt = build_user_prompt(level, viewpoint, reference, topic, ctx)
                else:
                    self._json(400, {"error": "line 必须是 story 或 user"})
                    return
                t0 = time.time()
                text = call_llm(settings, system_prompt, user_prompt)
                elapsed = time.time() - t0
                self._json(200, {"text": text, "elapsed": round(elapsed, 1), "line": line, "level": level})
            except ValueError as e:
                self._json(400, {"error": str(e)})
            except RuntimeError as e:
                self._json(502, {"error": str(e)})
            return

        if self.path == "/api/generate":
            # STORY 图文全链路：Step 0 预审 + Step 1 改写 + Step 1 元 + Step 2 分镜 + Step 3 出图 prompt
            try:
                settings = resolve_active_llm_settings()
                if not settings.get("api_key"):
                    self._json(400, {"error": "未配置 LLM API Key，请先到设置页填写"})
                    return
                line = data.get("line") or "story"
                level = data.get("level") or "standard"
                viewpoint = data.get("viewpoint", "keep")
                reference = (data.get("reference") or "").strip()
                topic = (data.get("topic") or "").strip()
                title_in = (data.get("title") or "").strip()
                track = data.get("track", "")
                hooks = data.get("hooks", []) or []
                targets = data.get("targets", {}) or {}
                style_label = (data.get("style") or "现代电影").strip()
                style_en = (data.get("style_en") or "").strip()
                run_steps = set(data.get("run_steps") or ["0", "1", "meta", "2", "3"])
                product = (data.get("product") or "").strip()
                keywords = (data.get("keywords") or "").strip()
                fixed_opening = (data.get("fixed_opening") or "").strip()
                tail_guide = (data.get("tail_guide") or "").strip()
                extra = (data.get("extra") or "").strip()

                t0_total = time.time()
                out = {"steps": {}, "line": line, "level": level}
                ctx = {
                    "track": track,
                    "hooks": hooks,
                    "sources": data.get("sources", []) or [],
                    "keywords": keywords,
                    "product": product,
                    "fixed_opening": fixed_opening,
                    "tail_guide": tail_guide,
                    "extra": extra,
                }

                # Step 0 文案预审
                if "0" in run_steps and reference:
                    out["steps"]["0"] = step0_pre_review(settings, reference)
                else:
                    out["steps"]["0"] = {"passed": True, "quality": "medium", "issues": [], "suggestion": ""}

                # Step 1 改写（用 Step 0 整理后的文本，如果 cleaned）
                s0 = out["steps"].get("0") or {}
                s0_text = s0.get("reviewed_text") if isinstance(s0, dict) else ""
                base_text = s0_text if (isinstance(s0, dict) and s0.get("cleaned") and s0_text) else reference

                if "1" in run_steps:
                    if line == "story":
                        if level not in STORY_LEVELS:
                            self._json(400, {"error": "未知 STORY 等级"})
                            return
                        sys_p = load_prompt_module("story/base_rewrite.py")
                        user_p = build_story_prompt(level, viewpoint, base_text, ctx)
                    elif line == "user":
                        if level not in USER_LEVELS:
                            self._json(400, {"error": "未知 USER 等级"})
                            return
                        sys_p = load_prompt_module("hook.py")
                        user_p = build_user_prompt(level, viewpoint, base_text, topic, ctx)
                    else:
                        self._json(400, {"error": "line 必须是 story 或 user"})
                        return
                    out["steps"]["1"] = {"text": call_llm(settings, sys_p, user_p)}
                else:
                    # 不重跑改写：用前端已有的改写稿
                    out["steps"]["1"] = {"text": (data.get("rewritten") or "").strip()}

                rewritten = out["steps"]["1"]["text"].strip()

                # Step 1 元信息
                if "meta" in run_steps and rewritten:
                    out["steps"]["meta"] = step1_meta(settings, title_in, rewritten, hooks, track)
                else:
                    out["steps"]["meta"] = data.get("meta") or {
                        "title": title_in, "short_title": "", "summary": "",
                        "tags": [], "comments": [], "cover_image_prompts": [],
                    }

                # Step 2 智能分镜
                if "2" in run_steps and rewritten:
                    target_shots = targets.get("shots")
                    target_words = targets.get("words")
                    if target_shots in ("auto", "", None):
                        target_shots = None
                    if target_words in ("auto", "", None):
                        target_words = None
                    out["steps"]["2"] = step2_split(settings, rewritten, target_shots=target_shots, target_words=target_words)
                else:
                    out["steps"]["2"] = {"shots": data.get("shots") or [], "notes": "前端传入"}

                shots = out["steps"]["2"].get("shots") or []

                # Step 3 出图 prompt
                if "3" in run_steps and shots:
                    meta_for_ctx = out["steps"]["meta"] or {}
                    story_ctx = (title_in + " / " + (meta_for_ctx.get("title") or "")).strip(" /")
                    # 角色档案（来自 Step 1 meta.characters[0]）注入 Step 3
                    chars = meta_for_ctx.get("characters") or []
                    character_card = chars[0] if isinstance(chars, list) and chars and isinstance(chars[0], dict) else None
                    out["steps"]["3"] = step3_image_prompts(settings, shots, track, style_label, story_ctx, character_card)
                else:
                    out["steps"]["3"] = data.get("image_prompts") or []

                # 持久化到 tasks.json + 落盘到 data/tasks/<id>/（让 Task 页能加载）
                meta = out["steps"]["meta"]
                task_id = (data.get("task_id") or f"task_{int(time.time())}_{os.urandom(3).hex()}").strip()
                task_dir = _tasks_root() / task_id
                task_dir.mkdir(parents=True, exist_ok=True)
                # Step 1 改写
                if rewritten:
                    (task_dir / "02-rewrite.txt").write_text(rewritten, encoding="utf-8")
                # Step 1 元信息
                if meta:
                    (task_dir / "02-meta.json").write_text(
                        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
                    )
                # Step 2 分镜
                if shots:
                    (task_dir / "03-shots.json").write_text(
                        json.dumps(shots, ensure_ascii=False, indent=2), encoding="utf-8"
                    )
                # Step 3 出图 prompt
                if isinstance(out["steps"]["3"], list) and out["steps"]["3"]:
                    (task_dir / "04-prompts.json").write_text(
                        json.dumps(out["steps"]["3"], ensure_ascii=False, indent=2), encoding="utf-8"
                    )
                save_task_record({
                    "id": task_id,
                    "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "title": (meta.get("title") or title_in)[:60],
                    "short_title": meta.get("short_title", ""),
                    "line": line,
                    "level": level,
                    "track": track,
                    "rewritten_chars": len(rewritten),
                    "shots_count": len(shots),
                    "image_prompts_count": len(out["steps"]["3"]) if isinstance(out["steps"]["3"], list) else 0,
                    "elapsed_total": round(time.time() - t0_total, 1),
                })
                out["task_id"] = task_id
                out["task_dir"] = str(task_dir)
                self._json(200, out)
            except ValueError as e:
                self._json(400, {"error": str(e)})
            except RuntimeError as e:
                self._json(502, {"error": str(e)})
            return

        if self.path == "/api/tasks":
            # 兼容旧：返回 history.json 内容
            self._json(200, load_tasks())
            return

        # ============================================================
        # Step 4 出图（批量调出图 API，参考 M_ 函数并发 3 路 + 失败兜底）
        #   body: {"prompts": [{"idx":1,"desc_prompt":"..."}], "ratio":"9:16", "resolution":"1k", "concurrency":3}
        # ============================================================
        if self.path == "/api/step4_generate_images":
            try:
                s = load_settings()
                prompts_in = data.get("prompts") or []
                ratio = (data.get("ratio") or "9:16").strip()
                resolution = (data.get("resolution") or "1k").strip()
                provider = (data.get("provider") or "").strip()
                task_id = (data.get("task_id") or f"task_{int(time.time())}").strip()
                # 若指定 task_id → 同时落盘到 task_dir/covers/（让 Task 页能加载）
                task_dir = (_tasks_root() / task_id) if task_id else None
                if task_dir is not None:
                    (task_dir / "covers").mkdir(parents=True, exist_ok=True)
                # 并发数：参考 M_ 默认 3；外部可传
                concurrency = int(data.get("concurrency") or 3)
                concurrency = max(1, min(10, concurrency))
                if not prompts_in:
                    self._json(400, {"error": "prompts 不能为空"})
                    return
                # 选 image 配置
                if not provider:
                    provider = (s.get("image") or {}).get("provider", "gpt_image")
                if provider in ("gpt_image", "modelscope", "custom_image", "openai"):
                    img_cfg = s.get("image") or {}
                    if not (img_cfg.get("api_key") and img_cfg.get("base_url")):
                        self._json(400, {"error": "未配置出图 API（OpenAI 兼容通道）"})
                        return
                elif provider == "jimeng":
                    img_cfg = s.get("jimeng") or {}
                    if not (img_cfg.get("ak") and img_cfg.get("sk")):
                        self._json(400, {"error": "未配置即梦 jimeng（AK / SK 必填）"})
                        return
                elif provider == "runninghub":
                    img_cfg = s.get("runninghub") or {}
                    if not (img_cfg.get("api_key") and img_cfg.get("workflow_id")):
                        self._json(400, {"error": "未配置 runninghub（api_key / workflow_id 必填）"})
                        return
                else:
                    self._json(400, {"error": f"未知 provider: {provider}"})
                    return
                # 并发生成（参考 M_ 函数：用线程池 + 信号量限流；失败后兜底重试 1 次）
                from concurrent.futures import ThreadPoolExecutor, as_completed
                out = [None] * len(prompts_in)
                def gen_one(slot, p):
                    idx = p.get("idx")
                    desc = (p.get("desc_prompt") or "").strip()
                    if not desc:
                        return slot, {"idx": idx, "ok": False, "error": "desc_prompt 为空"}
                    # 单次重试（复活 1 次）
                    last_err = None
                    for attempt in (1, 2):
                        try:
                            t0 = time.time()
                            r = image_dispatcher(img_cfg, desc, ratio=ratio, resolution=resolution)
                            # 落盘到 data/covers/（公开 URL）
                            if "b64" in r:
                                url = save_cover_image(r["b64"], r.get("mime", "image/png"))
                            else:
                                url = save_cover_image(r["url"], r.get("mime", "image/png"))
                            # 同时落到 task_dir/covers/（Task 页加载用）
                            task_local = ""
                            if task_dir is not None:
                                fname = f"{idx}.png"
                                target = task_dir / "covers" / fname
                                if url.startswith("/covers/"):
                                    # 从源 covers 拷过去
                                    src = DATA_DIR / url.lstrip("/")
                                    try:
                                        target.write_bytes(src.read_bytes())
                                        task_local = f"/api/task_image/{task_id}/{fname}"
                                    except OSError:
                                        pass
                            return slot, {"idx": idx, "ok": True, "url": url, "task_local": task_local, "elapsed": round(time.time()-t0, 1), "attempt": attempt}
                        except Exception as e:
                            last_err = str(e)
                    return slot, {"idx": idx, "ok": False, "error": last_err, "attempts": 2}
                t_total = time.time()
                with ThreadPoolExecutor(max_workers=concurrency) as ex:
                    futs = [ex.submit(gen_one, i, p) for i, p in enumerate(prompts_in)]
                    for f in as_completed(futs):
                        slot, r = f.result()
                        out[slot] = r
                self._json(200, {
                    "results": out,
                    "provider": provider,
                    "concurrency": concurrency,
                    "total_elapsed": round(time.time() - t_total, 1),
                })
            except ValueError as e:
                self._json(400, {"error": str(e)})
            except RuntimeError as e:
                self._json(502, {"error": str(e)})
            return

        # ============================================================
        # Step 5 TTS 配音 — 真实调用（参考 STORY ZC 37857 + R6 39519）
        #   body: {"segments":[{"idx":1,"text":"..."}], "speaker":"zh_male_...",
        #          "task_id":"...", "speed":1.0}
        #   响应: {"results":[{"idx","text","ok","url","duration","error"}],
        #          "task_dir":"..."}
        # ============================================================
        if self.path == "/api/step5_tts":
            try:
                s = load_settings()
                segments = data.get("segments") or []
                speaker = (data.get("speaker") or "").strip()
                task_id = (data.get("task_id") or f"task_{int(time.time())}").strip()
                speed = float(data.get("speed") or 1.0)
                provider = (data.get("provider") or s.get("tts", {}).get("provider", "volcengine")).strip()
                if not segments:
                    self._json(400, {"error": "segments 不能为空"})
                    return
                # 取配置
                tts = s.get("tts") or {}
                if provider == "volcengine":
                    volc = tts.get("volcengine") or {}
                    # 字段兼容：api_key (新) OR access_key (旧 settings)
                    api_key = (volc.get("api_key") or volc.get("access_key") or "").strip()
                    if not api_key:
                        self._json(400, {"error": "未配置火山引擎 TTS（设置 → TTS 配音 → 火山引擎 → API Key 必填）"})
                        return
                    if not speaker:
                        speaker = (volc.get("speaker") or volc.get("volcengine_speaker") or "zh_male_dongfanghaoran_moon_bigtts").strip()
                elif provider == "minimax":
                    mx = tts.get("minimax") or {}
                    api_key = (mx.get("api_key") or "").strip()
                    if not api_key:
                        self._json(400, {"error": "未配置 MiniMax TTS（API Key 必填）"})
                        return
                    if not speaker:
                        speaker = (mx.get("voice_id") or "").strip()
                    if not speaker:
                        self._json(400, {"error": "MiniMax TTS 需要指定 voice_id（设置 → TTS 配音 → 默认发音人）"})
                        return
                else:
                    self._json(400, {"error": f"暂不支持 TTS provider: {provider}（当前仅支持 volcengine / minimax）"})
                    return

                # 任务目录：data/tasks/<task_id>/audio/
                task_dir = DATA_DIR / "tasks" / task_id
                audio_dir = task_dir / "audio"
                audio_dir.mkdir(parents=True, exist_ok=True)
                # 保存输入元数据（参考 R6 的 SEGMENTS JSON）
                seg_meta = [
                    {"idx": seg.get("idx"), "text": seg.get("text", ""), "speaker": speaker}
                    for seg in segments
                ]
                (task_dir / "05-tts-input.json").write_text(
                    json.dumps(seg_meta, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )

                # 单条 TTS 调用（参考 ZC.n 函数）
                def synth_one(seg):
                    idx = seg.get("idx")
                    text = (seg.get("text") or "").strip()
                    if not text:
                        return {"idx": idx, "ok": False, "error": "text 为空"}
                    if provider == "volcengine":
                        return _volc_tts_synthesize(api_key, text, speaker, idx, speed)
                    elif provider == "minimax":
                        return _minimax_tts_synthesize(api_key, text, speaker, idx, speed, mx)
                    return {"idx": idx, "ok": False, "error": f"未知 provider: {provider}"}

                # 并发合成（参考 R6 的 _ = max(3, floor(h.length/3))；上限 3 路）
                from concurrent.futures import ThreadPoolExecutor, as_completed
                concurrency = min(3, len(segments))
                results = [None] * len(segments)
                t0 = time.time()
                with ThreadPoolExecutor(max_workers=concurrency) as ex:
                    futs = {ex.submit(synth_one, seg): i for i, seg in enumerate(segments)}
                    for f in as_completed(futs):
                        slot = futs[f]
                        try:
                            results[slot] = f.result()
                        except Exception as e:
                            results[slot] = {"idx": segments[slot].get("idx"), "ok": False, "error": str(e)}
                # 落盘每段 audio 到 audio/ 目录 + 更新 url
                seg_json = []
                for r in results:
                    if r and r.get("ok") and r.get("audio_bytes"):
                        audio_path = audio_dir / f"seg_{r['idx']:03d}.mp3"
                        audio_path.write_bytes(r["audio_bytes"])
                        r["url"] = f"/api/audio/{task_id}/seg_{r['idx']:03d}.mp3"
                        r["path"] = str(audio_path)
                        # 时长估算：先用 chars*0.18 占位，再用火山 ASR（若已配置且 key 一致）替换为真实时间戳
                        text_chars = sum(1 for ch in (r.get("text") or "") if ch.strip())
                        r["duration"] = round(max(1.0, text_chars * 0.18), 2)
                        r["duration_source"] = "chars_est"
                        # 火山 ASR 对齐（仅当 TTS provider = volcengine 且有 key 时启用；其他 provider 跳过）
                        if provider == "volcengine" and api_key:
                            try:
                                asr_segs = _volc_asr_transcribe(api_key, audio_path, timeout_sec=45)
                                # 取最后一个 utterance 的 end_time 作为该段总时长（utils 真实音频长度）
                                if asr_segs:
                                    last_end = max(s["end"] for s in asr_segs)
                                    if last_end > 0.5:
                                        r["duration"] = round(last_end, 2)
                                        r["duration_source"] = "volc_asr"
                                        r["asr_segments"] = asr_segs
                            except Exception as asr_e:
                                r["asr_error"] = str(asr_e)
                        seg_json.append({
                            "index": r["idx"], "path": r["path"],
                            "duration": r["duration"], "text": r.get("text", ""),
                            "duration_source": r.get("duration_source", "chars_est"),
                            "asr_segments": r.get("asr_segments", []),
                        })
                        r.pop("audio_bytes", None)
                    else:
                        r = r or {"ok": False, "error": "未知错误"}
                # 保存 05-tts-segments.json（参考 R6 的 SEGMENTS 持久化）
                (task_dir / "05-tts-segments.json").write_text(
                    json.dumps(seg_json, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
                ok_count = sum(1 for r in results if r and r.get("ok"))
                self._json(200, {
                    "results": results,
                    "task_id": task_id,
                    "task_dir": str(task_dir),
                    "provider": provider,
                    "speaker": speaker,
                    "ok_count": ok_count,
                    "total": len(segments),
                    "elapsed": round(time.time() - t0, 1),
                })
            except ValueError as e:
                self._json(400, {"error": str(e)})
            except RuntimeError as e:
                self._json(502, {"error": str(e)})
            return

        # ============================================================
        # Step 6 剪映草稿打包（参考 STORY U_ 41177 真值结构）
        #   body: {"shots":[...], "images":[...], "segments":[{"idx","text","duration"}],
        #          "title":"...", "task_id":"...", "ratio":"9:16",
        #          "bgm_path":"...", "cover_title":{...}}
        #   输出：剪映草稿目录/<task_id>/draft_content.json + draft_meta_info.json
        # ============================================================
        if self.path == "/api/step6_jianying_draft":
            try:
                s = load_settings()
                jy = s.get("jianying") or {}
                if not jy.get("draft_path"):
                    self._json(400, {"error": "未配置剪映草稿目录（去设置页填「剪映 → 草稿目录」）"})
                    return
                shots = data.get("shots") or []
                images = data.get("images") or []
                segments = data.get("segments") or []
                title = (data.get("title") or "未命名任务").strip()
                task_id = (data.get("task_id") or f"app074_{int(time.time())}").strip()
                ratio = (data.get("ratio") or "9:16").strip()
                bgm_path = (data.get("bgm_path") or jy.get("bgm_path") or "").strip()
                bgm_volume = float(data.get("bgm_volume") or jy.get("bgm_volume") or 0.3)
                bgm_fade_sec = float(data.get("bgm_fade_sec") or jy.get("bgm_fade_sec") or 1.5)
                cover_title = data.get("cover_title") or {}
                if not shots:
                    self._json(400, {"error": "shots 不能为空"})
                    return
                # 校验草稿根目录
                draft_root = Path(jy["draft_path"])
                if not draft_root.exists():
                    self._json(400, {"error": f"剪映草稿目录不存在：{draft_root}"})
                    return
                # 把 idx 序对齐
                seg_by_idx = {seg.get("idx"): seg for seg in segments if seg.get("idx") is not None}
                img_by_idx = {img.get("idx"): img for img in images if img.get("idx") is not None}
                # 构建时间轴（参考 U_ 中 x payload 的 assignments/lyrics 结构）
                tracks = []
                # 视频轨：每个分镜一张图 + 时长（按 Step 5 配音时长，无则按字数 * 0.18 + 1s）
                video_segments = []
                cur_t = 0.0
                total_dur = 0.0
                for i, sh in enumerate(shots):
                    idx = sh.get("idx", i + 1)
                    img = img_by_idx.get(idx) or {}
                    seg = seg_by_idx.get(idx) or {}
                    dur = float(seg.get("duration") or 0)
                    if dur <= 0:
                        # 兜底：按字数估算（中文 ~3.3 字/秒）
                        chars = len((sh.get("text") or "").strip())
                        dur = max(2.0, round(chars / 3.3, 2))
                    img_url = img.get("url") or ""
                    img_local = ""
                    if img_url.startswith("/covers/"):
                        img_local = str(DATA_DIR / img_url.lstrip("/"))
                    video_segments.append({
                        "id": f"video_seg_{idx}",
                        "type": "video",
                        "material_id": f"img_{idx}",
                        "material_path": img_local,
                        "material_url": img_url,
                        "target_timerange": {
                            "start": round(cur_t * 1_000_000),
                            "duration": round(dur * 1_000_000),
                        },
                        "speed": 1.0,
                        "volume": 0.0,
                        "visible": True,
                    })
                    cur_t += dur
                    total_dur += dur
                tracks.append({
                    "id": "video_track_main",
                    "type": "video",
                    "attribute": 0,
                    "flag": 0,
                    "segments": video_segments,
                })
                # 音频轨：每段配音 + 字幕
                audio_segments = []
                subtitle_segments = []
                cur_t = 0.0
                for i, sh in enumerate(shots):
                    idx = sh.get("idx", i + 1)
                    seg = seg_by_idx.get(idx) or {}
                    dur = float(seg.get("duration") or 0)
                    if dur <= 0:
                        chars = len((sh.get("text") or "").strip())
                        dur = max(2.0, round(chars / 3.3, 2))
                    audio_path = seg.get("path") or ""
                    audio_url = seg.get("url") or ""
                    audio_segments.append({
                        "id": f"audio_seg_{idx}",
                        "type": "audio",
                        "material_id": f"audio_{idx}",
                        "material_path": audio_path,
                        "material_url": audio_url,
                        "target_timerange": {
                            "start": round(cur_t * 1_000_000),
                            "duration": round(dur * 1_000_000),
                        },
                        "speed": 1.0,
                        "volume": 1.0,
                        "visible": True,
                    })
                    text = (sh.get("text") or "").strip()
                    if text:
                        subtitle_segments.append({
                            "id": f"subtitle_seg_{idx}",
                            "type": "text",
                            "material_id": f"subtitle_{idx}",
                            "content": text,
                            "target_timerange": {
                                "start": round(cur_t * 1_000_000),
                                "duration": round(dur * 1_000_000),
                            },
                            # 字幕样式（参考 STORY 默认字幕风格：白字 + 黑描边 + 阴影，底部居中）
                            "font_size": 18,
                            "font_color": "#FFFFFF",
                            "stroke_color": "#000000",
                            "stroke_width": 2,
                            "shadow_enabled": True,
                            "shadow_color": "#000000",
                            "shadow_offset": {"x": 0, "y": 2},
                            "alignment": 1,  # 居中
                            "position": {"x": 0.5, "y": 0.88},  # 偏下，不挡主体
                        })
                    cur_t += dur
                tracks.append({
                    "id": "audio_track_main",
                    "type": "audio",
                    "attribute": 0,
                    "flag": 0,
                    "segments": audio_segments,
                })
                tracks.append({
                    "id": "subtitle_track_main",
                    "type": "text",
                    "attribute": 0,
                    "flag": 0,
                    "segments": subtitle_segments,
                })
                # BGM 轨（全局铺底 30% 音量 + 头尾 1.5s 淡入淡出）
                if bgm_path and Path(bgm_path).exists():
                    bgm_duration_us = round(max(total_dur, 1.0) * 1_000_000)
                    fade_us = int(bgm_fade_sec * 1_000_000)
                    tracks.append({
                        "id": "bgm_track",
                        "type": "audio",
                        "attribute": 0,
                        "flag": 0,
                        "segments": [{
                            "id": "bgm_seg",
                            "type": "audio",
                            "material_id": "bgm",
                            "material_path": bgm_path,
                            "target_timerange": {
                                "start": 0,
                                "duration": bgm_duration_us,
                            },
                            "speed": 1.0,
                            "volume": bgm_volume,
                            # 音量关键帧：开头 0 → bgm_volume（淡入），结尾 bgm_volume → 0（淡出）
                            "keyframes": [
                                {"type": "volume", "time": 0, "value": 0.0},
                                {"type": "volume", "time": min(fade_us, bgm_duration_us), "value": bgm_volume},
                                {"type": "volume", "time": max(0, bgm_duration_us - fade_us), "value": bgm_volume},
                                {"type": "volume", "time": bgm_duration_us, "value": 0.0},
                            ],
                            "visible": True,
                        }],
                    })
                # draft_content.json（剪映私有格式）
                draft_content = {
                    "id": task_id,
                    "title": title,
                    "version": 360000,  # 剪映 4.x 兼容版本号
                    "cover": cover_title.get("cover_path") or "",
                    "fps": 30.0,
                    "duration": round(total_dur * 1_000_000),
                    "ratio": ratio,
                    "width": 1080 if ratio == "9:16" else (1920 if ratio == "16:9" else 1080),
                    "height": 1920 if ratio == "9:16" else (1080 if ratio == "16:9" else 1080),
                    "tracks": tracks,
                    "extra": {
                        "app074_version": "1.0.0",
                        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "source": "STORY-bound (U_ 41177 简化版)",
                    },
                }
                # draft_meta_info.json（剪映元信息）
                draft_meta = {
                    "draft_id": task_id,
                    "draft_name": title,
                    "draft_fold_path": "",
                    "draft_materials": [],
                    "draft_cover": cover_title.get("cover_path") or "",
                    "draft_removable_storage_device": "",
                    "tm_draft_cloud_completed": "",
                    "draft_root_path": "",
                    "draft_segment_extra_info": [],
                    "draft_materials_not_support": [],
                }
                # 落盘到剪映草稿目录/<task_id>/
                proj_dir = draft_root / task_id
                proj_dir.mkdir(parents=True, exist_ok=True)
                (proj_dir / "draft_content.json").write_text(
                    json.dumps(draft_content, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                (proj_dir / "draft_meta_info.json").write_text(
                    json.dumps(draft_meta, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                # 同时保存产物元数据到 074 data
                task_meta = {
                    "task_id": task_id,
                    "title": title,
                    "shot_count": len(shots),
                    "image_count": sum(1 for img in images if img.get("ok")),
                    "segment_count": len([s for s in segments if s.get("ok") is not False]),
                    "total_duration_sec": round(total_dur, 2),
                    "draft_dir": str(proj_dir),
                    "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
                (DATA_DIR / "tasks" / task_id).mkdir(parents=True, exist_ok=True)
                (DATA_DIR / "tasks" / task_id / "06-draft-meta.json").write_text(
                    json.dumps(task_meta, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                self._json(200, {
                    "ok": True,
                    "task_id": task_id,
                    "draft_dir": str(proj_dir),
                    "draft_content_path": str(proj_dir / "draft_content.json"),
                    "draft_meta_info_path": str(proj_dir / "draft_meta_info.json"),
                    "shot_count": len(shots),
                    "image_count": sum(1 for img in images if img.get("ok")),
                    "segment_count": len([s for s in segments if s.get("ok") is not False]),
                    "total_duration_sec": round(total_dur, 2),
                    "tracks": [{"id": t["id"], "type": t["type"], "segment_count": len(t["segments"])} for t in tracks],
                    "note": "完整 U_ 函数（draft_content + draft_meta_info + 时间轴 + 字幕 + BGM）；可手动导入剪映查看",
                })
            except ValueError as e:
                self._json(400, {"error": str(e)})
            except RuntimeError as e:
                self._json(502, {"error": str(e)})
            return

        self.send_error(404)


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    msg = f"app074 listening on http://127.0.0.1:{PORT}"
    # pythonw.exe 没控制台，print 会抛异常，只写文件
    try:
        (DATA_DIR / "startup.log").write_text(
            f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n", encoding="utf-8"
        )
    except OSError:
        pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        try:
            (DATA_DIR / "startup.log").write_text(
                f"{time.strftime('%Y-%m-%d %H:%M:%S')} CRASH: {e}\n", encoding="utf-8"
            )
        except OSError:
            pass
        raise
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
