"""Opt-in, single-image ModelScope editing; independent from production pipelines."""
import base64
import hashlib
import json
from pathlib import Path
import re
import threading
import time
import urllib.parse

from image_motion import read, write
import task_cover

MODEL='Qwen/Qwen-Image-Edit-2511'
API='https://api-inference.modelscope.cn/v1'
LOCK=threading.RLock()
ACTIVE={'submitting','pending','unknown','download_pending'}


def directory(backend):
    root=backend.DATA_DIR.resolve();folder=root/'modelscope-reference-experiment'
    if folder.is_symlink() or getattr(folder,'is_junction',lambda:False)() or not folder.resolve().is_relative_to(root):
        raise ValueError('实验目录无效')
    return folder


def job_directory(backend,operation):
    if not isinstance(operation,str) or not re.fullmatch(r'[a-f0-9]{32}',operation):raise ValueError('测试操作编号无效')
    root=directory(backend);folder=root/'jobs'/operation
    if not folder.resolve().is_relative_to(root.resolve()):raise ValueError('测试目录无效')
    return folder


def public(job):
    value={key:job[key] for key in ('operationId','status','taskId','prompt','model','createdAt','updatedAt','error') if key in job}
    if job.get('status')=='ok':value['url']='/api/ms-reference-experiment/image/'+job['operationId']
    return value


def state(backend):
    root=directory(backend);settings=backend.load_settings().get('modelscope') or {}
    jobs=[read(path,{}) for path in (root/'jobs').glob('*/job.json')]
    return {'enabled':read(root/'config.json',{}).get('enabled') is True,'model':MODEL,
            'configured':bool(settings.get('tokens')),'jobs':[public(job) for job in sorted(jobs,key=lambda j:j.get('createdAt',0),reverse=True)[:30]]}


def configure(backend,data):
    if set(data)!={'enabled'} or type(data['enabled']) is not bool:raise ValueError('启用选项必须为布尔值')
    with LOCK:write(directory(backend)/'config.json',{'enabled':data['enabled']})
    return state(backend)


def submit(backend,data):
    operation=data.get('operation_id');folder=job_directory(backend,operation)
    prompt=data.get('prompt');reference=data.get('reference')
    if not isinstance(prompt,str) or not prompt.strip() or len(prompt)>20000:raise ValueError('请填写1至20000字的编辑要求')
    if not isinstance(reference,str) or len(reference)>14_000_000:raise ValueError('请选择10MB以内的产品参考图')
    match=re.fullmatch(r'data:image/(?:png|jpeg|webp);base64,([A-Za-z0-9+/=]+)',reference)
    if not match:raise ValueError('参考图只支持PNG/JPG/WEBP')
    raw=task_cover.image_bytes({'b64':match[1]})
    encoded='data:image/png;base64,'+base64.b64encode(raw).decode()
    fingerprint=hashlib.sha256(json.dumps([MODEL,prompt.strip(),hashlib.sha256(raw).hexdigest()],ensure_ascii=False).encode()).hexdigest()
    path=folder/'job.json'
    with LOCK:
        existing=read(path,{})
        if existing:
            if existing.get('fingerprint')!=fingerprint:raise ValueError('本次测试参数已改变，请先核对原任务')
            return public(existing)
        if not state(backend)['enabled']:raise ValueError('请先启用独立参考图实验')
        for previous in (directory(backend)/'jobs').glob('*/job.json'):
            if read(previous,{}).get('status') in ACTIVE:raise ValueError('已有测试在途或提交状态不明，请先查询原任务；不会重复提交')
        cfg=backend.resolve_image_config(backend.load_settings(),'modelscope')
        if not cfg.get('api_key'):raise ValueError('请先在系统设置配置魔搭Token')
        cfg={**cfg,'base_url':API,'model':MODEL}
        folder.mkdir(parents=True,exist_ok=True)
        (folder/'reference.png').write_bytes(raw)
        job={'operationId':operation,'status':'submitting','prompt':prompt.strip(),'model':MODEL,
             'fingerprint':fingerprint,'credential':task_cover.credential(cfg),'createdAt':time.time(),'updatedAt':time.time()}
        write(path,job)
    try:
        _,body=backend._http_post_json(API+'/images/generations',
            {'Authorization':'Bearer '+cfg['api_key'],'Content-Type':'application/json','X-ModelScope-Async-Mode':'true'},
            json.dumps({'model':MODEL,'prompt':prompt.strip(),'image_url':[encoded]},ensure_ascii=False).encode('utf8'))
        task_id=json.loads(body).get('task_id')
        if not isinstance(task_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}',task_id):raise RuntimeError('未返回有效任务编号')
        job.update(taskId=task_id,status='pending')
    except (OSError,RuntimeError,ValueError) as error:
        status=re.search(r'HTTP\s+(\d{3})',str(error),re.I)
        rejected=status and int(status[1]) in (400,401,402,403,404,413,415,422,429)
        job.update(status='rejected' if rejected else 'unknown',error=(f'平台拒绝提交（HTTP {status[1]}），请检查魔搭账号、额度或图片。' if rejected else '提交结果尚未确认，请核对魔搭任务记录；不会自动重发。'))
    job['updatedAt']=time.time();write(path,job)
    return public(job)


def query(backend,operation):
    folder=job_directory(backend,operation);path=folder/'job.json'
    with LOCK:
        job=read(path,{})
        if not job:raise ValueError('测试记录不存在')
        if job.get('status')=='ok' and (folder/'result.png').is_file():return public(job)
        if job.get('status') in ('rejected','failed'):return public(job)
        if not job.get('result'):
            if not job.get('taskId'):raise ValueError('没有平台任务编号，请核对魔搭记录；不会重复提交')
            cfg=backend.resolve_image_config(backend.load_settings(),'modelscope')
            candidates=[{**cfg,'api_key':token,'base_url':API,'model':MODEL} for token in cfg.get('tokens') or []]
            cfg=next((item for item in candidates if task_cover.credential(item)==job.get('credential')),None)
            if not cfg:raise ValueError('原魔搭Token凭据已变化，请恢复原账号再查询')
            try:
                _,body=backend._http_get_json(API+'/tasks/'+urllib.parse.quote(job['taskId'],safe=''),
                    {'Authorization':'Bearer '+cfg['api_key'],'X-ModelScope-Task-Type':'image_generation'})
                result=json.loads(body)
            except (OSError,RuntimeError,ValueError):raise RuntimeError('查询暂未成功，请稍后查询原任务；不会重新提交') from None
            if result.get('task_status')=='FAILED':
                job.update(status='failed',error='魔搭确认本次参考图测试失败，可修改要求后另开一次测试。',updatedAt=time.time());write(path,job);return public(job)
            if result.get('task_status')!='SUCCEED':return public(job)
            url=next((value for value in result.get('output_images') or [] if isinstance(value,str) and value.startswith('https://')),None)
            if not url:raise RuntimeError('平台成功但未返回有效图片地址，请核对原任务；不会重新提交')
            job.update(status='download_pending',result={'url':url},updatedAt=time.time());write(path,job)
        try:raw=task_cover.image_bytes(job['result'])
        except (OSError,RuntimeError,ValueError):raise RuntimeError('图片取回未完成，原结果已保留；稍后查询即可，不用重新生成') from None
        target=folder/'result.png';temporary=target.with_suffix('.tmp');temporary.write_bytes(raw);temporary.replace(target)
        job.update(status='ok',updatedAt=time.time());job.pop('error',None);write(path,job)
        return public(job)


def media(backend,operation):
    folder=job_directory(backend,operation);target=folder/'result.png'
    if read(folder/'job.json',{}).get('status')!='ok' or not target.is_file():raise ValueError('测试图片尚未取回')
    return target
