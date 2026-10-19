"""Local-only audio import and catalog actions added for the 1.25 template flow."""
import base64
from functools import wraps
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit
import material_groups
import music_library
import image_lab

ROUTES = {'/api/template-sound/upload', '/api/music/delete', '/api/materials/open-folder', '/api/image_lab/delete'}


def upload_sound(backend, data):
    name = data.get('name')
    if not isinstance(name, str) or not name.strip() or len(name) > 200:
        raise ValueError('音效文件名无效')
    name = name.replace('\\', '/').split('/')[-1]
    extension = Path(name).suffix.lower()
    if extension not in ('.mp3', '.wav', '.m4a', '.aac', '.flac', '.ogg'):
        raise ValueError('请选择 MP3/WAV/M4A/AAC/FLAC/OGG 音频文件')
    uri = data.get('data_url')
    match = re.fullmatch(r'data:(?:audio/[\w.+-]+|application/octet-stream);base64,([A-Za-z0-9+/=]+)', uri) if isinstance(uri, str) else None
    if not match or len(match[1]) > 28_000_000: raise ValueError('音效必须是20MB以内的音频')
    try: raw = base64.b64decode(match[1], validate=True)
    except ValueError: raise ValueError('音频编码无效') from None
    if not raw or len(raw) > music_library.MAX_BYTES: raise ValueError('音效必须是20MB以内的音频')
    folder = Path(backend.DATA_DIR) / 'template-sounds'
    if not folder.resolve().is_relative_to(Path(backend.DATA_DIR).resolve()): raise ValueError('音效目录无效')
    if folder.is_symlink() or getattr(folder, 'is_junction', lambda: False)(): raise ValueError('音效目录不能使用链接')
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (hashlib.sha256(raw).hexdigest() + extension)
    if path.is_symlink(): raise ValueError('音效文件不能使用链接')
    # Inspect an owned temporary file before adding media to the permanent pool.
    import tempfile
    with tempfile.NamedTemporaryFile(dir=folder, suffix=extension, delete=False) as output:
        output.write(raw); temporary = Path(output.name)
    try:
        _, duration, _ = music_library._inspect_audio(backend, temporary)
        if path.exists(): temporary.unlink()
        else: os.replace(temporary, path)
    finally: temporary.unlink(missing_ok=True)
    return {'path': str(path), 'name': name, 'duration': duration}


def open_material_folder(backend, data):
    ident = data.get('material_id')
    root = material_groups.root(backend)
    if ident:
        if not isinstance(ident, str) or not re.fullmatch(r'[a-f0-9]{12}', ident): raise ValueError('素材编号无效')
        row = next((m for m in material_groups.list_all(backend)['materials'] if m['id'] == ident), None)
        if not row: raise ValueError('素材已不存在')
        target = material_groups.safe(root, row['filename']).parent
    else: target = root
    target = material_groups.safe(root, str(target.relative_to(root)))
    target.mkdir(parents=True, exist_ok=True)
    if os.name == 'nt': os.startfile(str(target))
    else: subprocess.Popen(['xdg-open', str(target)])
    return {'ok': True}


def install(backend):
    if getattr(backend.Handler, '_story1250_assets', False): return
    original = backend.Handler.do_POST
    @wraps(original)
    def post(handler):
        path = urlsplit(handler.path).path
        if path not in ROUTES: return original(handler)
        if not handler._desktop_authorized(): return
        try:
            size = int(handler.headers.get('Content-Length', '0'))
            limit = 29_000_000 if path.endswith('/upload') else 4096
            if not 0 <= size <= limit:
                handler.close_connection = True; handler._json(413, {'error': '请求内容过大'}); return
            data = json.loads(handler.rfile.read(size)) if size else {}
            if not isinstance(data, dict): raise ValueError('请求必须是 JSON 对象')
            if path == '/api/template-sound/upload': result = upload_sound(backend, data)
            elif path == '/api/music/delete': result = music_library.remove_track(backend, data.get('id'))
            elif path == '/api/image_lab/delete': result = image_lab.delete_history(backend.DATA_DIR, data.get('id'))
            else: result = open_material_folder(backend, data)
            handler._json(200, result)
        except (ValueError, RuntimeError, OSError) as error:
            handler._json(400, {'error': str(error) if not isinstance(error, (OSError, json.JSONDecodeError)) else '本地素材操作失败，请检查文件格式和目录权限'})
    backend.Handler.do_POST = post; backend.Handler._story1250_assets = True
