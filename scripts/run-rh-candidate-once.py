"""Run one authorized RH candidate with a durable, non-secret receipt.

The receipt is written before submitting. Never rerun a candidate whose receipt
exists; inspect the platform task and billing instead.
"""
import json
from pathlib import Path
import re
import secrets
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from image_motion import read, write
import rh_coins_experiment as exp
import rh_coins_workflow as workflow
import rh_workflow_graphs as graphs
import task_cover

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / '.desktop-tools/rh-four-live-tests-20261027'
DATA = Path.home() / 'AppData/Local/com.app074.desktop/data'
BACKEND = SimpleNamespace(DATA_DIR=DATA)
KEYS = ('qwen-native', 'flux-native', 'qwen-chinese', 'sdxl-native')
PROMPT = '一幅9:16竖版中国山水画：清晨山间小路、远处青山、薄雾与暖色阳光，画面清晰，色彩协调，没有文字、标志或水印。'


def balance(cfg):
    info = exp.account(BACKEND, cfg)
    return int(info['remainCoins']), info.get('currentTaskCounts')


def receipt(key, value):
    write(AUDIT / (key + '.json'), value)
    print(json.dumps({k: value.get(k) for k in ('key', 'status', 'workflowId', 'taskId', 'responseCode', 'balanceBefore', 'balanceAfter', 'spentCoins', 'error', 'imagePath')}, ensure_ascii=False), flush=True)


def main(key):
    if key not in KEYS:
        raise ValueError('Only the four authorized candidates may be run')
    path = AUDIT / (key + '.json')
    if path.exists():
        raise RuntimeError('Receipt already exists; do not submit again: ' + str(path))
    cfg = exp.config(BACKEND)
    first = next((read(p, {}) for p in (exp.directory(BACKEND) / 'jobs').glob('*/job.json') if read(p, {}).get('status') == 'ok'), {})
    if not cfg.get('api_key') or exp.credential(cfg) != first.get('credential'):
        raise RuntimeError('Current Key differs from the first successful workflow')
    entry = exp.CANDIDATES[key]
    value = exp.post(BACKEND, cfg, '/api/openapi/getJsonApiFormat', {'apiKey': cfg['api_key'], 'workflowId': entry['id']})
    raw = value.get('data', {}).get('prompt') if isinstance(value.get('data'), dict) else None
    if value.get('code') != 0 or not isinstance(raw, str):
        raise RuntimeError('Could not read the complete workflow graph')
    prepared = graphs.prepare(json.loads(raw))
    graph = workflow.build_graph(prepared['graph'], PROMPT, '9:16', secrets.randbits(32))
    before, in_flight = balance(cfg)
    if before <= 0 or in_flight not in ('0', 0, None):
        raise RuntimeError('Insufficient coins or existing platform task')
    record = {'key': key, 'status': 'submitting', 'workflowId': entry['id'], 'workflowSha256': workflow.digest(graph),
              'summary': prepared['summary'], 'prompt': PROMPT, 'ratio': '9:16', 'balanceBefore': before, 'createdAt': time.time()}
    receipt(key, record)
    try:
        response = exp.post(BACKEND, cfg, '/task/openapi/create', {'apiKey': cfg['api_key'], 'workflowId': entry['id'],
            'workflow': json.dumps(graph, ensure_ascii=False), 'nodeInfoList': [], 'instanceType': 'default'})
    except BaseException:
        record.update(status='unknown', error='Submission response not received; inspect account tasks before any retry')
        receipt(key, record)
        return
    data = response.get('data')
    task_id = data.get('taskId') if isinstance(data, dict) else None
    if type(task_id) is int:
        task_id = str(task_id)
    record['responseCode'] = response.get('code')
    if not isinstance(task_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', task_id):
        record.update(status='rejected' if type(record['responseCode']) is int and record['responseCode'] != 0 else 'unknown',
                      error=exp.REJECTIONS.get(record['responseCode'], 'No valid task ID; inspect account tasks'))
        record['balanceAfter'], _ = balance(cfg)
        record['spentCoins'] = record['balanceBefore'] - record['balanceAfter']
        receipt(key, record)
        return
    record.update(status='pending', taskId=task_id)
    receipt(key, record)
    deadline = time.monotonic() + 900
    while time.monotonic() < deadline:
        response = exp.post(BACKEND, cfg, '/task/openapi/outputs', {'apiKey': cfg['api_key'], 'taskId': task_id})
        code = response.get('code')
        if code in (804, 813):
            time.sleep(5)
            continue
        if code == 805:
            terminal = exp.post(BACKEND, cfg, '/task/openapi/status', {'apiKey': cfg['api_key'], 'taskId': task_id})
            if terminal.get('code') == 0 and terminal.get('data') in ('FAILED', 'CANCELED', 'CANCELLED'):
                record.update(status='failed', error='Platform task failed or was cancelled')
            else:
                record.update(status='unknown', error='Platform returned 805 with no confirmed terminal state')
            break
        outputs = response.get('data')
        if code != 0 or not isinstance(outputs, list):
            record.update(status='unknown', error='Unexpected outputs response code ' + str(code))
            break
        images = [x for x in outputs if isinstance(x, dict) and str(x.get('fileType', '')).lower() in ('png', 'jpg', 'jpeg', 'webp')]
        if len(images) != 1 or not isinstance(images[0].get('fileUrl'), str):
            record.update(status='unknown', error='Expected exactly one image output')
            break
        record.update(status='output_ready', imageUrl=images[0]['fileUrl'])
        receipt(key, record)
        try:
            image = task_cover.image_bytes({'url': images[0]['fileUrl']})
            image_path = AUDIT / (key + '.png')
            image_path.write_bytes(image)
            record.update(status='ok', imagePath=str(image_path), imageBytes=len(image))
        except BaseException:
            record.update(status='output_ready', error='Image download pending; task output URL retained')
        break
    else:
        record.update(status='pending', error='Task still running after 15 minutes; query original task')
    record['balanceAfter'], _ = balance(cfg)
    record['spentCoins'] = record['balanceBefore'] - record['balanceAfter']
    receipt(key, record)


if __name__ == '__main__':
    main(sys.argv[1])
