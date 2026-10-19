"""Story's per-scene started/finished state, scoped to live local workers.

Supplier receipts remain the sole authority for recovering paid jobs. This
display state never persists credentials, submits work, or survives a restart.
"""
from collections import Counter
from pathlib import Path
import threading
import time

_lock = threading.Lock()
_workers = {}
_local = threading.local()


def active(folder):
    key = str(Path(folder).resolve())
    with _lock:
        return sorted(_workers.get(key, {}))


def checkpoint():
    callback = getattr(_local, 'checkpoint', None)
    if callback:
        callback()


def resume_query(job, query):
    """Resume waiting for an already paid job whose polling was paused locally."""
    deadline = time.monotonic() + (180 if job['provider'] == 'modelscope' else 900)
    while True:
        checkpoint()
        response = query()
        if (not job.get('poll_interrupted') or response.get('status') not in ('RUNNING', 'PENDING', 'QUEUED')
                or time.monotonic() >= deadline):
            return response
        time.sleep(3)


def run(folder, index, check, work, *args):
    key, index = str(Path(folder).resolve()), int(index)
    previous = getattr(_local, 'checkpoint', None)
    _local.checkpoint = check
    try:
        checkpoint()
        with _lock:
            _workers.setdefault(key, Counter())[index] += 1
        try:
            return work(*args)
        finally:
            with _lock:
                counts = _workers[key]
                counts[index] -= 1
                if not counts[index]: del counts[index]
                if not counts: del _workers[key]
    finally:
        _local.checkpoint = previous
