"""Passive component checks and disjoint draft storage for the 074 runtime.

Installation only adds adapters; it reads no settings, starts no process and
performs no exports. Health checks inspect component files, never credentials.
"""
from functools import wraps
import hashlib
import json
import ntpath
import os
from pathlib import Path
import re
import shutil
from urllib.parse import parse_qs, urlsplit

HEALTH_PATH = '/api/runtime/health'
DRAFT_CHECK_PATH = '/api/runtime/draft-path-check'
PATH_CONFLICT = '剪映草稿目录与 074 任务数据目录重叠，请选择独立目录；两者不能相同或互相包含'


def _without_namespace(value):
    if value[:8].casefold() == '\\\\?\\unc\\':
        return '\\\\' + value[8:]
    if value.startswith('\\\\?\\'):
        return value[4:]
    return value


def _canonical_path(value):
    """Resolve existing junction ancestors, then compare Windows components.

    ``strict=False`` also resolves the existing parent of a proposed new folder.
    ntpath keeps Windows drive/UNC comparisons usable in isolated POSIX tests.
    """
    value = _without_namespace(str(value).strip().replace('/', '\\') if os.name == 'nt' else str(value).strip())
    windows = os.name == 'nt' or bool(ntpath.splitdrive(value)[0])
    if windows:
        value = _without_namespace(value.replace('/', '\\'))
        if value.startswith('\\\\.\\') or not ntpath.isabs(value) or not ntpath.splitdrive(value)[0]:
            raise ValueError('请填写完整的剪映草稿目录绝对路径')
        if re.search(r'[<>"|?*\x00-\x1f]', value) or ':' in ntpath.splitdrive(value)[1]:
            raise ValueError('剪映草稿目录包含无效字符')
        # Win32 treats trailing dots/spaces as the same directory name.
        value = ntpath.normpath(value)
        parts = [part.rstrip(' ') for part in value.split('\\')]
        value = '\\'.join(part.rstrip('.') if part not in ('.', '..') else part for part in parts)
        if os.name == 'nt':
            value = str(Path(value).resolve(strict=False))
        return ntpath.normcase(ntpath.normpath(_without_namespace(value))).casefold()
    if not Path(value).is_absolute() or '\x00' in value:
        raise ValueError('请填写完整的剪映草稿目录绝对路径')
    return str(Path(value).resolve(strict=False))


def validate_draft_path(draft_path, data_dir):
    """Reject equal/nested roots without moving or changing fixed task storage."""
    if draft_path is None or draft_path == '':
        return
    if not isinstance(draft_path, (str, os.PathLike)):
        raise ValueError('剪映草稿目录必须是路径文字')
    if not str(draft_path).strip():
        return
    if len(str(draft_path)) > 32767:
        raise ValueError('剪映草稿目录过长')
    try:
        draft, data = _canonical_path(draft_path), _canonical_path(data_dir)
        path_module = ntpath if os.name == 'nt' or bool(ntpath.splitdrive(draft)[0]) else os.path
        try:
            common = path_module.commonpath((draft, data))
        except ValueError:  # Different drives/shares are necessarily disjoint.
            return
        if common in (draft, data):
            raise ValueError(PATH_CONFLICT)
    except (OSError, RuntimeError) as error:
        raise ValueError('无法核对剪映草稿目录，请检查目录权限和路径') from error


def _component(status, message):
    return {'status': status, 'message': message}


def _manifest_digest(root, executable):
    for parent in (root, root.parent):
        manifest = parent / 'backend-runtime.json'
        if not manifest.is_file():
            continue
        if manifest.stat().st_size > 8 * 1024 * 1024:
            return None
        value = json.loads(manifest.read_text('utf8'))
        files = value.get('files', {}) if isinstance(value, dict) else {}
        if not isinstance(files, dict):
            return None
        relative = executable.relative_to(parent).as_posix().casefold()
        for name, digest in files.items():
            if str(name).replace('\\', '/').casefold() == relative:
                return digest if isinstance(digest, str) and re.fullmatch(r'[a-fA-F0-9]{64}', digest) else None
    return None


def _generator_health(root):
    executable = root / 'draft-generator.exe'
    if not executable.is_file():
        executable = root / '.desktop-tools/story-reference/draft-generator.exe'
    if not executable.is_file():
        return _component('missing', '缺少草稿生成组件，请从可信安装包重新安装；文字工作可继续')
    try:
        expected = _manifest_digest(root, executable)
        if not expected:
            return _component('unverified', '草稿生成组件缺少有效安装清单，请从可信安装包重新安装后核验')
        if executable.stat().st_size > 256 * 1024 * 1024:
            return _component('invalid', '草稿生成组件大小异常，请从可信安装包重新安装')
        with executable.open('rb') as stream:
            signature = stream.read(2)
            stream.seek(0)
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if signature != b'MZ' or digest != expected.lower():
            return _component('invalid', '草稿生成组件校验失败，请从可信安装包重新安装')
        return _component('ready', '草稿生成组件文件校验通过；尚未执行草稿导出')
    except (OSError, ValueError, RuntimeError):
        return _component('unverified', '无法校验草稿生成组件，请检查安装文件和目录权限或重新安装')


def health(backend):
    """Read only component metadata/bytes; never run executables or load settings."""
    root = Path(backend.ROOT)
    generator = _generator_health(root)
    try:
        ffmpeg = root / 'ffmpeg.exe'
        if not ffmpeg.is_file():
            located = shutil.which('ffmpeg')
            ffmpeg = Path(located) if located else None
        available = ffmpeg is not None and ffmpeg.is_file()
        media = _component('ready' if available else 'missing',
                           'ffmpeg 文件可用；尚未执行音视频合成' if available else
                           '缺少 ffmpeg，音视频合成可能失败，请从可信安装包修复；文字工作可继续')
    except (OSError, ValueError):
        media = _component('unverified', '无法检查 ffmpeg，请检查安装文件和目录权限')
    return {'ok': generator['status'] == media['status'] == 'ready',
            'draft_generator': generator, 'ffmpeg': media}


def install(backend):
    """Add authenticated GET checks and validate merged settings before save."""
    if getattr(backend, '_story1250_safety_installed', False):
        return
    original_merge, original_get = backend._merged, backend.Handler.do_GET

    @wraps(original_merge)
    def merged(values):
        result = original_merge(values)
        validate_draft_path((result.get('jianying') or {}).get('draft_path'), backend.DATA_DIR)
        return result

    @wraps(original_get)
    def do_get(handler):
        parsed = urlsplit(handler.path)
        if parsed.path not in (HEALTH_PATH, DRAFT_CHECK_PATH):
            return original_get(handler)
        if not handler._desktop_authorized():
            return
        if parsed.path == HEALTH_PATH:
            handler._json(200, health(backend))
            return
        try:
            draft = parse_qs(parsed.query, keep_blank_values=True).get('path', [''])[0]
            validate_draft_path(draft, backend.DATA_DIR)
            result = {'valid': True}
        except ValueError as error:
            result = {'valid': False, 'error': str(error)}
        handler._json(200, result)

    backend._merged, backend.Handler.do_GET = merged, do_get
    backend._story1250_safety_installed = True
