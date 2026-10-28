"""Durable lab receipts; navigation never owns a generation worker."""
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import time
import uuid

_lock = threading.RLock()
_instance = uuid.uuid4().hex
_slots = threading.BoundedSemaphore(4)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False), 'utf8')
    os.replace(temporary, path)


def receipts(root):
    result = []
    for path in (Path(root) / 'image-lab-jobs').glob('*.json'):
        try:
            job = json.loads(path.read_text('utf8'))
        except (OSError, ValueError):
            continue
        if job['status'] in ('queued', 'running') and job['instance'] != _instance:
            job['status'] = 'interrupted'
            job['error'] = '软件曾重启，任务结果待核对；未自动重新提交扣费。'
        if job['status'] in ('queued', 'running', 'interrupted', 'failed'):
            result.append({k: v for k, v in job.items() if k not in ('instance', 'fingerprint')})
    return result


def submit(backend, data, generate):
    identity = data.get('request_id')
    if not isinstance(identity, str) or not re.fullmatch(r'[a-f0-9]{32}', identity):
        raise ValueError('缺少有效的提交编号，请刷新实验室后重试')
    if not str(data.get('prompt') or '').strip():
        raise ValueError('请填写画面提示词')
    request = {k: v for k, v in data.items() if k not in ('background', 'request_id')}
    fingerprint = hashlib.sha256(json.dumps(request, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    path = Path(backend.DATA_DIR) / 'image-lab-jobs' / (identity + '.json')
    with _lock:
        if path.exists():
            job = json.loads(path.read_text('utf8'))
            if job['fingerprint'] != fingerprint:
                raise ValueError('提交编号已用于其他内容，不能重复购买')
            return {'accepted': True, 'job_id': identity, 'items': []}
        job = dict(id=identity, kind='lab-job', createdAt=time.time(), status='queued',
                   instance=_instance, fingerprint=fingerprint, prompt=request['prompt'],
                   provider=request.get('provider') or '', ratio=' / '.join(request.get('ratios') or []))
        write(path, job)

        def work():
            try:
                with _slots:
                    job['status'] = 'running'
                    write(path, job)
                    result = generate(backend, {**request, '_lab_job_id': identity})
                job.update(status='complete', item_ids=[item['id'] for item in result['items']])
            except Exception as error:
                job.update(status='failed', error=str(error)[:500])
            finally:
                job['finishedAt'] = time.time()
                write(path, job)

        threading.Thread(target=work, name='image-lab-' + identity[:8], daemon=True).start()
    return {'accepted': True, 'job_id': identity, 'items': []}
