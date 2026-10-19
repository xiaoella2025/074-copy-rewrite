"""One durable, per-scene retry after confirmed failure, with original-job recovery."""
import json
import re
import time
from pathlib import Path
import task_cover
import task_queue


def read_record(path):
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text('utf8'))
        if not isinstance(value, dict):
            raise ValueError('not an object')
        return value
    except (OSError, ValueError) as error:
        raise RuntimeError('出图恢复记录损坏，请核对原任务；不会重复提交') from error


def serious(message):
    return bool(re.search(
        r'HTTP\s*(?:400|401|402|403|404|422)\b|api.?key|unauthori[sz]ed|forbidden|'
        r'quota|balance|insufficient|payment|credit|content.?policy|moderation|safety|'
        r'sensitive|nsfw|invalid.?param|not.?support|verification|'
        r'余额|额度|欠费|积分不足|未配置|凭据|认证|审核|违规|敏感|不支持|参数无效|参数错误|模型不存在',
        str(message), re.I))


def query_original(backend, cfg, path, job):
    """Only query using the original supplier/account; never replace an unknown job."""
    actual = backend.resolve_image_config(backend.load_settings(), job['provider'])
    if job['provider'] == 'modelscope':
        actual = next(({**actual, 'api_key': token} for token in actual.get('tokens') or []
                       if task_cover.credential({**actual, 'api_key': token}) == job.get('credential')), actual)
    if task_cover.credential(actual) != job.get('credential'):
        raise RuntimeError('绘图凭据或服务地址已变化，请恢复原设置再查询')
    response = task_cover.query_provider(backend, actual, job['taskId'])
    if response.get('status') == 'SUCCESS':
        result = next((r for r in response.get('results', []) if isinstance(r, dict) and r.get('url')), None)
        if not result:
            raise RuntimeError('上游成功但未返回图片地址，请查原任务；不会再次购买')
        saved = {'url': result['url'], 'provider': job['provider']}
        if job.get('fallback_from'):
            saved.update(fallback_from=job['fallback_from'], fallback_reason=job.get('fallback_reason', 'quota_exhausted'))
        job.update(status='download_pending', result=saved)
    elif response.get('status') == 'FAILED':
        reason = next((response[k] for k in ('failReason', 'errorMessage', 'errorCode', 'error', 'message') if response.get(k)), '')
        job.update(status='failed', lastError=str(reason or job.get('lastError') or '上游确认生成失败')[:1000])
    else:
        raise RuntimeError('原出图任务仍在途或状态不明，已保留原任务编号，请稍后查图；不会重复购买')
    task_queue.atomic_json(path, job)
    return job


def generate(backend, cfg, prompt, index, ratio, resolution, folder, reference=None, *, retry=True, checkpoint=lambda: None):
    path = Path(folder) / 'image-jobs' / f'{index}.json'
    journal = path.parent / '.auto-retry' / f'{index}.json'
    checkpoint()
    job = read_record(path)
    claim = read_record(journal)
    if job.get('prompt') and (job['prompt'] != prompt or job.get('ratio') != ratio or job.get('resolution') != resolution):
        raise RuntimeError('已有出图任务参数不同，请先核对原任务；不会再次提交')
    if claim and not job:
        raise RuntimeError('自动重试已登记但提交状态不明，请核对原任务；不会重复购买')
    if not path.exists():
        # Synchronous APIs also get a durable submitting/unknown record.
        task_queue.atomic_json(path, {})
    try:
        if job.get('status') in ('failed', 'rejected') and not job.get('result'):
            raise RuntimeError(job.get('lastError') or '上游确认生成失败')
        return backend.batch_image_result(cfg, prompt, index, ratio, resolution, folder, reference)
    except Exception as error:
        checkpoint()
        job = read_record(path)
        if not retry or job.get('result'):
            raise
        job['lastError'] = str(error)[:1000] if not job.get('lastError') else job['lastError']
        if job.get('taskId') and job.get('status') in ('pending', 'failed'):
            job = query_original(backend, cfg, path, job)
            if job.get('result'):
                return backend.batch_image_result(cfg, prompt, index, ratio, resolution, folder, reference)
        if job.get('status') not in ('failed', 'rejected'):
            raise
        if serious(job.get('lastError')):
            task_queue.atomic_json(path, job)
            raise RuntimeError(f"出图需要处理：{job['lastError']}；成功图片已保留，未自动重购") from None
        if claim:
            raise RuntimeError(f'第 {index} 镜已自动重试 1 次仍未完成；成功图片已保留，可单独补这张图') from None
        checkpoint()
        # Claim and archive the terminal receipt BEFORE replacing it or buying.
        task_queue.atomic_json(journal, {'attempts': 1, 'status': 'claimed', 'previous': job, 'createdAt': time.time()})
        task_queue.atomic_json(path, {})
        # A short backoff gives a transient worker failure time to clear.
        try:
            time.sleep(2)
            checkpoint()
        except Exception:
            # Pausing before submission is known to be unpaid. Restore the
            # terminal receipt so explicit single-image recovery stays usable.
            task_queue.atomic_json(path, job)
            raise
        try:
            result = backend.batch_image_result(cfg, prompt, index, ratio, resolution, folder, reference)
        except Exception as error:
            current = read_record(path)
            # Keep pending/unknown receipts intact, even if this request failed.
            task_queue.atomic_json(journal, {**read_record(journal), 'status': current.get('status') or 'unknown'})
            raise RuntimeError(f'第 {index} 镜已自动重试 1 次仍未完成：{error}；成功图片已保留') from error
        task_queue.atomic_json(journal, {**read_record(journal), 'status': 'completed'})
        return {**result, 'auto_retries': 1}


def can_retry_download(folder, index):
    """A paid result can be downloaded again without another generation call."""
    return bool(read_record(Path(folder) / 'image-jobs' / f'{index}.json').get('result'))


def progress(folder):
    """Expose only index and status; supplier IDs and prompts stay private."""
    values = []
    for path in (Path(folder) / 'image-jobs/.auto-retry').glob('*.json'):
        if not path.stem.isdigit():
            continue
        try:
            claim = read_record(path)
            if claim:
                job = read_record(path.parent.parent / path.name)
                values.append({'index': int(path.stem), 'attempts': 1,
                               'status': job.get('status') or claim.get('status')})
        except RuntimeError:
            values.append({'index': int(path.stem), 'attempts': 1, 'status': 'unknown'})
    return sorted(values, key=lambda x: x['index'])
