"""Local Obsidian and IMA knowledge access for the image-text workflow."""

import hashlib
import html
import itertools
import json
import os
import re
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path


_EXPORT_LOCK = threading.Lock()


def _digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write_json(path, value):
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temp = Path(stream.name)
            json.dump(value, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if temp and temp.exists():
            temp.unlink()


def _vault(config):
    path = Path(config.get("vault") or "").expanduser()
    if not path.is_absolute() or not path.is_dir() or not (path / ".obsidian").is_dir():
        raise ValueError("请先配置已有 Obsidian 仓库根目录（包含 .obsidian 文件夹）")
    return path.resolve()


def _folder(config):
    root = _vault(config)
    name = config.get("folder") or "图文创作"
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                *(f"LPT{i}" for i in range(1, 10))}
    if (not isinstance(name, str) or len(name) > 120 or name.startswith(".") or name.endswith((" ", "."))
            or re.search(r'[\\/:*?"<>|\x00-\x1f]', name) or name.split(".")[0].upper() in reserved):
        raise ValueError("Obsidian 系列文件夹须为仓库内的单个普通文件夹名称")
    folder = root / name
    if folder.resolve().parent != root:
        raise ValueError("Obsidian 文件夹不能跳出所选仓库")
    return folder


def _search_terms(query):
    terms = [part.lower() for part in re.findall(r"[\u4e00-\u9fff]{2,8}|[A-Za-z0-9]{2,30}", query or "")]
    return terms[:8]


def search_obsidian(config, query):
    """Search bounded Markdown files in the selected series folder, without following links."""
    folder = _folder(config)
    if not folder.is_dir():
        return []
    terms = _search_terms(query)
    if not terms:
        return []
    root = _vault(config)
    matches = []
    for path in itertools.islice(folder.rglob("*.md"), 500):
        if path.is_symlink() or root not in path.resolve().parents or path.stat().st_size > 1024 * 1024:
            continue
        content = path.read_text(encoding="utf-8", errors="replace")
        haystack = (path.stem + "\n" + content).lower()
        score = sum(min(haystack.count(term), 5) for term in terms)
        if score:
            first = min((haystack.find(term) for term in terms if term in haystack), default=0)
            excerpt = content[max(0, first - 100):first + 900].strip()
            matches.append((score, {"title": path.stem, "excerpt": excerpt, "source": "Obsidian"}))
    matches.sort(key=lambda item: item[0], reverse=True)
    return [item for _, item in matches[:5]]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def _ima_call(path, payload, config):
    client = config.get("client_id") or ""
    key = config.get("api_key") or ""
    if not client or not key:
        raise ValueError("请先保存 IMA Client ID 和 API Key")
    request = urllib.request.Request(
        "https://ima.qq.com/" + path,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "ima-openapi-clientid": client,
                 "ima-openapi-apikey": key},
        method="POST",
    )
    try:
        with urllib.request.build_opener(_NoRedirect).open(request, timeout=25) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
    except urllib.error.HTTPError as error:
        raise ValueError(f"IMA 请求失败（HTTP {error.code}）") from None
    except urllib.error.URLError:
        raise ValueError("IMA 网络请求失败，请检查连接") from None
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError("IMA 响应超过大小上限")
    try:
        result = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        raise ValueError("IMA 返回了无法解析的响应") from None
    if not isinstance(result, dict) or result.get("code") != 0:
        raise ValueError("IMA 返回业务错误；请检查权限和知识库 ID")
    return result.get("data") or {}


def search_ima(config, query):
    kb_id = config.get("kb_id") or ""
    if not kb_id:
        raise ValueError("请先填写 IMA 知识库 ID")
    if not query.strip():
        return []
    data = _ima_call("openapi/wiki/v1/search_knowledge", {
        "query": query[:200], "cursor": "", "knowledge_base_id": kb_id,
    }, config)
    results = []
    for item in (data.get("info_list") or [])[:5]:
        if not isinstance(item, dict):
            continue
        excerpt = re.sub(r"<[^>]+>", "", item.get("highlight_content") or "")
        results.append({"title": str(item.get("title") or "IMA 知识")[:120],
                        "excerpt": html.unescape(excerpt)[:900], "source": "IMA"})
    return results


def lookup(settings, sources, query):
    sources = sources if isinstance(sources, list) else []
    results = []
    if "ima" in sources:
        results.extend(search_ima(settings.get("ima") or {}, query))
    if "obsidian" in sources:
        results.extend(search_obsidian(settings.get("obsidian") or {}, query))
    return results[:8]


def _task_document(task_dir):
    rewrite = task_dir / "02-rewrite.txt"
    if not rewrite.is_file():
        raise ValueError("此任务还没有可保存的改写文案")
    text = rewrite.read_text(encoding="utf-8")
    meta_path = task_dir / "02-meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}
    title = str(meta.get("title") or task_dir.name).strip()[:120]
    return title, f"# {title}\n\n- 来源：074 图文创作\n- 任务 ID：{task_dir.name}\n\n{text}\n"


def save_obsidian(task_dir, config):
    folder = _folder(config)
    title, document = _task_document(task_dir)
    folder.mkdir(exist_ok=True)
    # Recheck after mkdir to reject an unexpected junction or symlink.
    if folder.resolve().parent != _vault(config):
        raise ValueError("Obsidian 文件夹不能跳出所选仓库")
    safe_title = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", title)[:45].strip(" .") or "图文创作"
    target = folder / f"{safe_title}-{_digest(task_dir.name)[:10]}-{_digest(document)[:8]}.md"
    content = document.encode("utf-8")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=folder, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError:
            if target.is_symlink() or target.read_bytes() != content:
                raise ValueError("同名笔记已存在且内容不同，未覆盖")
    finally:
        if temporary and temporary.exists():
            temporary.unlink()
    return {"ok": True, "path": str(target), "status": "saved"}


def save_ima(task_dir, config):
    """073-style note import: no automatic retry after an uncertain write."""
    if not config.get("client_id") or not config.get("api_key"):
        raise ValueError("请先保存 IMA Client ID 和 API Key")
    title, document = _task_document(task_dir)
    receipt_path = task_dir / "ima-export.json"
    signature = _digest(document + "|" + (config.get("kb_id") or "") + "|"
                        + (config.get("notebook_id") or "") + "|" + (config.get("client_id") or ""))
    with _EXPORT_LOCK:
        previous = json.loads(receipt_path.read_text("utf-8")) if receipt_path.is_file() else {}
        if previous.get("signature") == signature:
            if previous.get("status") == "complete":
                return {"ok": True, "status": "already_saved"}
            raise ValueError("上次 IMA 写入尚未完整确认，请先在 IMA 核对；未重复发送")
        receipt = {"signature": signature, "status": "pending"}
        _write_json(receipt_path, receipt)
        chunks = [document[index:index + 2000] for index in range(0, len(document), 2000)]
        try:
            payload = {"content_format": 1, "content": chunks[0]}
            if config.get("notebook_id"):
                payload["folder_id"] = config["notebook_id"]
            note_id = _ima_call("openapi/note/v1/import_doc", payload, config).get("note_id")
            if not isinstance(note_id, str) or not note_id:
                raise ValueError("IMA 未返回笔记 ID")
            receipt.update(note_id=note_id, status="partial", chunks=1)
            _write_json(receipt_path, receipt)
            for chunk in chunks[1:]:
                _ima_call("openapi/note/v1/append_doc", {"note_id": note_id,
                    "content_format": 1, "content": chunk}, config)
                receipt["chunks"] += 1
                _write_json(receipt_path, receipt)
            if config.get("kb_id"):
                _ima_call("openapi/wiki/v1/add_knowledge", {"media_type": 11,
                    "title": title, "knowledge_base_id": config["kb_id"],
                    "note_info": {"content_id": note_id}}, config)
            receipt["status"] = "complete"
            _write_json(receipt_path, receipt)
            return {"ok": True, "status": "saved", "note_id": note_id}
        except Exception:
            receipt["status"] = "unconfirmed"
            _write_json(receipt_path, receipt)
            raise ValueError("IMA 写入未完整确认，请在 IMA 核对；未自动重试") from None
