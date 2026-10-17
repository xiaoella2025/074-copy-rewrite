"""Short subtitle lines and their timing, shared by preview and draft export."""
import difflib
from functools import lru_cache
import json
from pathlib import Path
import re


def plain(text):
    return re.sub(r"[\W_]+", "", str(text), flags=re.UNICODE)


@lru_cache(maxsize=1)
def _tokenizer():
    import jieba
    jieba.setLogLevel(40)
    return jieba.Tokenizer()


@lru_cache(maxsize=512)
def _word_units(text):
    raw = list(_tokenizer().cut(text, HMM=False))
    words = []
    i = 0
    while i < len(raw):
        word = plain(raw[i])
        # A number and its measure belong to the same reading unit.
        if word.isascii() and word.isdigit() and i + 1 < len(raw):
            unit = plain(raw[i + 1])
            if unit and re.fullmatch(r'[十百千万亿]*(?:年|月|日|时|分|秒|元|美元|米|公里|岁|人|名|个|次|天|小时|分钟|公斤|吨|万|亿)', unit):
                word += unit
                i += 1
        if word:
            words.append(word)
        i += 1
    return tuple(words)


def _pause_breaks(text, segment):
    recognized, pauses, last_end = '', [], None
    for item in (segment or {}).get('asr_segments') or []:
        word = plain(item.get('text', ''))
        if not word:
            continue
        start, end = float(item.get('start', 0)), float(item.get('end', 0))
        if last_end is not None and start - last_end >= .28:
            pauses.append(len(recognized))
        recognized += word
        last_end = end
    matcher = difflib.SequenceMatcher(None, text, recognized, autojunk=False)
    if not recognized or matcher.ratio() < .55:
        return set()
    reverse = {block.b + i:block.a + i for block in matcher.get_matching_blocks() for i in range(block.size)}
    return {reverse[p] for p in pauses if p in reverse and reverse.get(p - 1) == reverse[p] - 1}


def split_lines(text, limit=12, segment=None):
    text, limit = str(text), max(1, int(limit))
    clean = plain(text)
    if not clean:
        return []
    words = _word_units(text)
    positions, offset = {0}, 0
    for word in words:
        # A single oversized English token still has to fit the chosen canvas.
        for part in (word[i:i + limit] for i in range(0, len(word), limit)):
            offset += len(part)
            positions.add(offset)
    hard, soft, enumeration, offset = set(), set(), set(), 0
    for i, char in enumerate(text):
        offset += len(plain(char))
        if char in '。！？!?；;\n\r' or (char == '.' and not (i and i + 1 < len(text) and text[i-1].isdigit() and text[i+1].isdigit())):
            hard.add(offset)
        elif char in '，,：:':
            soft.add(offset)
        elif char == '、':
            enumeration.add(offset)
    hard.update(_pause_breaks(clean, segment).intersection(positions))
    hard.add(len(clean))
    fixed = set(hard)
    hard.update(soft)
    # Keep complete comma clauses. Only join very short fragments, such as a
    # one-word address, when no sentence end or audible pause separates them.
    while True:
        boundaries = [0] + sorted(p for p in hard if p > 0)
        removable = None
        for left, right in zip(boundaries, boundaries[1:]):
            if right - left < 3:
                if left and left not in fixed:
                    removable = left
                elif right not in fixed:
                    removable = right
                if removable is not None:
                    break
        if removable is None:
            break
        hard.remove(removable)
    lines, begin = [], 0
    for end in sorted(p for p in hard if p > 0):
        points = sorted({begin, end} | {p for p in positions if begin < p < end})
        costs, previous = {begin:0.0}, {}
        for point_index, finish in enumerate(points[1:], 1):
            candidates = []
            for start_index in range(point_index - 1, -1, -1):
                start = points[start_index]
                width = finish - start
                if width > limit:
                    break
                if start not in costs:
                    continue
                score = 2 + ((limit - width) / limit) ** 2
                if width < min(4, limit):
                    score += (min(4, limit) - width) * 2
                if start > begin and clean[start] in '的了地得着过吗呢吧啊和与及或':
                    score += 2
                if finish < end:
                    if clean[finish-1] in '把被在向给对从与和跟':
                        score += 1
                    if finish in soft:
                        score -= 1
                    if finish in enumeration:
                        score += 2
                candidates.append((costs[start] + score, start))
            if candidates:
                costs[finish], previous[finish] = min(candidates)
        chunks, cursor = [], end
        while cursor > begin:
            start = previous[cursor]
            chunks.append(clean[start:cursor])
            cursor = start
        lines.extend(reversed(chunks))
        begin = end
    return lines


def timed_lines(text, lines, segment):
    duration = float(segment.get("duration") or 0)
    original = plain(text)
    recognized, stamps = "", []
    for word in segment.get("asr_segments") or []:
        value = plain(word.get("text", ""))
        start, end = float(word.get("start", 0)), float(word.get("end", 0))
        for i, char in enumerate(value):
            recognized += char
            stamps.append((start + (end - start) * i / len(value), start + (end - start) * (i + 1) / len(value)))
    mapping = {}
    matcher = difflib.SequenceMatcher(None, original, recognized, autojunk=False)
    if recognized and matcher.ratio() >= .55:
        for block in matcher.get_matching_blocks():
            for i in range(block.size): mapping[block.a + i] = stamps[block.b + i]
    cues, offset, previous = [], 0, 0.0
    for line in lines:
        width = len(plain(line))
        found = [mapping[i] for i in range(offset, offset + width) if i in mapping]
        start = found[0][0] if found else duration * offset / max(1, len(original))
        end = found[-1][1] if found else duration * (offset + width) / max(1, len(original))
        start = max(previous, min(start, max(0, duration - .001)))
        end = max(start + .001, min(duration, end))
        cues.append({"text": line, "start": round(start, 3), "end": round(end, 3),
                     "timing_source": "asr" if found else "estimated"})
        previous = end; offset += width
    return cues


def build_captions(shots, segments, saved=None, limit=12):
    segs = {int(s.get("idx", s.get("index", i + 1))): s for i, s in enumerate(segments)}
    previous = {int(x["id"]): x for x in (saved or {}).get("items", [])}
    items = []
    for i, shot in enumerate(shots):
        idx = int(shot.get("idx", shot.get("id", i + 1)))
        text = shot.get("text", shot.get("cap", ""))
        segment = segs.get(idx, {})
        lines = previous.get(idx, {}).get("lines") if (saved or {}).get('source') == 'manual' else None
        lines = lines or split_lines(text, limit, segment)
        if plain("".join(lines)) != plain(text): lines = split_lines(text, limit, segment)
        elif any(len(plain(line))>limit for line in lines):
            lines=[part for line in lines for part in split_lines(line,limit)]
        items.append({"id": idx, "text": text, "lines": lines,
                      "cues": timed_lines(text, lines, segs.get(idx, {}))})
    return {"source": (saved or {}).get("source", "rules"), "max_chars": limit, "items": items}


def task_captions(task_dir, shots, segments, limit=None):
    path = Path(task_dir) / "05-captions.json"
    try: saved = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError): saved = None
    limit = limit or (saved or {}).get("max_chars", 12)
    if saved and saved.get("max_chars", 12) != limit and saved.get("source") != "manual": saved = None
    return build_captions(shots, segments, saved, limit)


def save_captions(task_dir, shots, segments, items):
    limit = task_captions(task_dir, shots, segments)["max_chars"]
    by_id = {int(x["id"]): x for x in items}
    for i, shot in enumerate(shots):
        idx = int(shot.get("idx", i + 1))
        lines = by_id.get(idx, {}).get("lines", [])
        if not lines or plain("".join(lines)) != plain(shot.get("text", "")):
            raise ValueError(f"第 {idx} 镜字幕与原文不一致，请只调整断行")
        if any(len(plain(line)) > limit for line in lines):
            raise ValueError(f"第 {idx} 镜字幕超过每行 {limit} 字")
    data = build_captions(shots, segments, {"source": "manual", "items": items}, limit)
    (Path(task_dir) / "05-captions.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
    return data
