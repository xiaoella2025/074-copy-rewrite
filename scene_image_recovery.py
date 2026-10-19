"""Explicit retry of one missing, terminally failed scene; never restart the batch."""
from functools import wraps
import json
from pathlib import Path
import re
import time
from urllib.parse import urlsplit
import task_cover
import task_queue
from image_motion import read,write

ROUTE=re.compile(r'/api/task/([A-Za-z0-9_-]{1,100})/retry-image')

class RecoveryFailure(RuntimeError):
    def __init__(self,message,retryable=False):
        super().__init__(message);self.retryable=retryable

def retry(backend,tid,data):
    if not isinstance(data,dict) or set(data)-{'index','operation_id'}:raise ValueError('补图参数无效')
    index=data.get('index');operation=data.get('operation_id')
    if type(index)!=int or index<1 or not isinstance(operation,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',operation):raise ValueError('补图镜头或操作编号无效')
    folder=task_cover.folder_for(backend,tid)
    with backend.task_operation(tid):
        prompts=read(folder/'04-prompts.json',[])
        prompt=next((p for p in prompts if p.get('idx')==index and isinstance(p.get('desc_prompt'),str) and p['desc_prompt'].strip()),None)
        if not prompt:raise ValueError('未找到本镜绘图提示词')
        # Successful local outputs always win, including a lost success response.
        local=next((p for p in (folder/'covers').glob('*') if p.stem.isdigit() and int(p.stem)==index and p.suffix.lower() in ('.png','.jpg','.jpeg','.webp') and p.stat().st_size),None)
        if local:return {'ok':True,'index':index,'cached':True,'url':f'/api/task_image/{tid}/{local.name}'}
        journal=folder/'.image-retries'/f'{index}-{operation}.json'
        receipt=folder/'image-jobs'/f'{index}.json';job=read(receipt,{})
        if journal.exists():raise RecoveryFailure('本次补图已提交；同一次操作不会再次购买。确认失败后可重新点击，仅重画本镜',job.get('status') in ('failed','rejected'))
        if job.get('status') not in ('failed','rejected'):raise ValueError('本镜仍在途、状态不明或没有明确失败记录，请先查图；不会再次购买')
        client=read(folder/'client_config.json',{}).get('image',{})
        provider=client.get('provider') or job.get('primary_provider') or job.get('provider')
        cfg=backend.resolve_image_config(backend.load_settings(),provider)
        if not cfg.get('api_key') and not (cfg.get('ak') and cfg.get('sk')):raise ValueError('请先配置本任务绘图引擎的凭据')
        archive=journal.with_suffix('.receipt.json')
        # Claim durably before removing the old terminal receipt or contacting
        # the supplier. A crash with an uncertain claim never triggers a resend.
        write(archive,job);write(journal,{'operationId':operation,'index':index,'status':'claimed','createdAt':time.time()})
        # A placeholder forces the shared batch path to create a durable job
        # even for synchronous providers, before its first network submission.
        marker={'manualOperation':operation}
        task_queue.atomic_json(receipt,marker)
        body={'task_id':tid,'prompts':[prompt],'provider':provider,'retry':False,
              'ratio':client.get('ratio') or job.get('ratio') or '9:16',
              'resolution':client.get('resolution') or job.get('resolution') or '1k','concurrency':1}
        try:
            value=task_queue.dispatch(backend,'/api/step4_generate_images',body,tid)
            result=next((r for r in value.get('results',[]) if r.get('idx')==index and r.get('ok')),None)
            if not result:raise RuntimeError('补图未完成')
            write(journal,{'operationId':operation,'index':index,'status':'completed'})
            return {'ok':True,'index':index,'url':result.get('task_local') or result.get('url'),'cached':False}
        except Exception:
            # Only a pre-submission failure can restore the old terminal record.
            # A new unknown/pending receipt is retained, never replaced.
            current=read(receipt,{})
            if not current or current==marker:task_queue.atomic_json(receipt,job);current=job
            raise RecoveryFailure(f'第 {index} 镜补图未完成；其他图片已保留。请核对本次任务状态，不会自动再次购买',current.get('status') in ('failed','rejected')) from None

def install(backend):
    if getattr(backend.Handler,'_scene_recovery_installed',False):return
    original=backend.Handler.do_POST
    @wraps(original)
    def do_post(handler):
        match=ROUTE.fullmatch(urlsplit(handler.path).path)
        if not match:return original(handler)
        if not handler._desktop_authorized():return
        try:
            size=int(handler.headers.get('content-length','0'))
            if not 0<=size<=4096:
                handler.close_connection=True;handler._json(413,{'error':'补图请求过大'});return
            data=json.loads(handler.rfile.read(size)) if size else {}
            handler._json(200,retry(backend,match[1],data))
        except (ValueError,RuntimeError,OSError) as error:
            handler._json(409,{'error':str(error) if not isinstance(error,(json.JSONDecodeError,UnicodeError,OSError)) else '补图记录无法读取或保存，请检查记录和磁盘','retryable':bool(getattr(error,'retryable',False))})
    backend.Handler.do_POST=do_post;backend.Handler._scene_recovery_installed=True
