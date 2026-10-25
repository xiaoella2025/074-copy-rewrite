"""Read-only cloning of completed image tasks before any new mutation."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import time
import uuid
from contextlib import nullcontext

def completed(folder):
    try:
        value=json.loads((Path(folder)/'06-draft-meta.json').read_text('utf8'))
        return isinstance(value,dict) and value.get('ok') is not False and bool(value.get('draft_dir'))
    except (OSError,ValueError):return False

def rebase(value,source,target,old_id,new_id):
    if isinstance(value,dict):return {k:(new_id if k in ('task_id','taskId') and v==old_id else rebase(v,source,target,old_id,new_id)) for k,v in value.items()}
    if isinstance(value,list):return [rebase(v,source,target,old_id,new_id) for v in value]
    if not isinstance(value,str):return value
    if re.match(r'^(?:[A-Za-z]:[\\/]|\\\\)',value):
        try:relative=Path(value).relative_to(source)
        except ValueError:pass
        else:
            if '..' not in relative.parts:return str(target/relative)
    for prefix in (str(source),source.as_posix()):
        if value==prefix:return str(target)
        if value.startswith(prefix+'\\') or value.startswith(prefix+'/'):return str(target)+value[len(prefix):]
    for kind in ('task_cover','task_video','task_image','audio','task_animation','cover-image'):
        prefix='/api/'+kind+'/'+old_id+'/'
        if value.startswith(prefix):return '/api/'+kind+'/'+new_id+'/'+value[len(prefix):]
    return value

def fork(backend,task_id,reason='pipeline',operation_key=None):
    with backend.TASK_OPERATION_LOCK:
        return _fork(backend,task_id,reason,operation_key)

def _fork(backend,task_id,reason,operation_key):
    if not isinstance(task_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',task_id):raise ValueError('无效原任务编号')
    root=backend.DATA_DIR/'tasks';source=root/task_id
    if not source.is_dir() or source.resolve().parent!=root.resolve() or source.is_symlink() or getattr(source,'is_junction',lambda:False)():raise ValueError('原任务不存在或路径无效')
    import task_cover,scene_reference,task_queue
    ledger_path=backend.DATA_DIR/'task-revisions.json'
    ledger={'version':1,'operations':{}}
    registry_key=task_id+':'+operation_key if operation_key else None
    if registry_key:
        if ledger_path.exists():ledger=json.loads(ledger_path.read_text('utf8'))
        if ledger.get('version')!=1 or not isinstance(ledger.get('operations'),dict):raise ValueError('任务版本记录损坏，请保留原记录核查')
        saved=ledger['operations'].get(registry_key)
        if saved:
            child=root/saved
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',saved) or not child.is_dir() or task_cover.read(child/'fork.json',{}).get('source_task_id')!=task_id:raise ValueError('原修改版本缺失，请先核对记录，不能重复提交')
            return saved
    task_cover.require_idle(source);scene_reference.require_idle(source)
    require=getattr(backend,'require_batch_image_idle',None)
    if require:require(source)
    if task_queue.get_queue(backend).owns(task_id):raise ValueError('原任务正在执行或排队，请先暂停')
    video=task_cover.read(source/'04-video-meta.json',{})
    if any(x.get('status') in ('pending','submitting','unknown') for x in video.get('items',{}).values()):raise ValueError('原任务有在途视频，请先核对原记录')
    new_id=f'task_{int(time.time()*1000)}_{uuid.uuid4().hex[:12]}'
    target=root/new_id
    excluded={'.reruns','rerun-archive','draft','06-draft-meta.json','progress.json','run-meta.json','cancel','pause','pause-request','fork.json'}
    try:
        # Never capture/update image history in the source as part of cloning.
        for path in source.rglob('*'):
            if path.is_symlink() or getattr(path,'is_junction',lambda:False)():raise ValueError('任务包含链接目录，不能直接复制')
        shutil.copytree(source,target,ignore=lambda path,names:[name for name in names if Path(path)==source and name in excluded])
        for path in target.rglob('*.json'):
            value=json.loads(path.read_text('utf8'));changed=rebase(value,source,target,task_id,new_id)
            if changed!=value:task_cover.write(path,changed)
        task_cover.write(target/'fork.json',{'source_task_id':task_id,'field':reason,'created_at':time.strftime('%Y-%m-%d %H:%M:%S')})
        if registry_key:
            ledger['operations'][registry_key]=new_id
            task_queue.atomic_json(ledger_path,ledger)
        return new_id
    except BaseException:
        if target.is_dir() and target.parent.resolve()==root.resolve():shutil.rmtree(target)
        raise

def route_completed(backend,handler,data):
    """Redirect direct editor writes before their first mutation, not after repack."""
    if getattr(handler,'_revision_routed',False):return False
    path=handler.path;match=re.fullmatch(r'/api/task/([A-Za-z0-9_-]{1,100})/(repack|captions|motion-prompt|motion-video|animation-video|retry-image|repair-prompts)',path)
    scene=re.fullmatch(r'/api/scene-image/([A-Za-z0-9_-]{1,100})/(?:\d+/(?:crop|replace|restore|reference)|gallery/(?:copy|swap|import))',path)
    if match or scene:
        task_id=(match or scene)[1]
        if (path.endswith('/reference') and data.get('action')=='query') or data.get('query_only'):return False
    elif path in getattr(backend,'TASK_STAGE_ROUTES',set()):task_id=data.get('task_id')
    else:return False
    if not isinstance(task_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',task_id):return False
    source=backend.DATA_DIR/'tasks'/task_id
    if not completed(source):return False
    operation=data.get('operation_id')
    identity=operation if isinstance(operation,str) and re.fullmatch(r'[A-Za-z0-9_-]{1,100}',operation) else hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    try:
        with backend.TASK_OPERATION_LOCK:
            new_id=fork(backend,task_id,'direct-editor',operation_key=path+':'+identity)
    except (ValueError,OSError) as error:
        handler._json(409,{'error':str(error)});return True
    target=backend.DATA_DIR/'tasks'/new_id
    if completed(target):
        saved=json.loads((target/'06-draft-meta.json').read_text('utf8'))
        handler._json(200,{**saved,'task_id':new_id,'source_task_id':task_id});return True
    old_json=handler._json;old_path=handler.path
    def response(status,value):
        if isinstance(value,dict):value={**value,'task_id':new_id,'source_task_id':task_id}
        old_json(status,value)
    handler.path=path.replace('/'+task_id+'/', '/'+new_id+'/',1)
    handler._json=response;handler._revision_routed=True
    try:
        # Scene editors already acquire the child's operation lease internally.
        with (nullcontext() if scene or path.endswith('/repair-prompts') else backend.task_operation(new_id)):
            handler._handle_json_post(rebase(data,source,target,task_id,new_id))
    finally:
        handler.path=old_path;handler._json=old_json;handler._revision_routed=False
    return True
