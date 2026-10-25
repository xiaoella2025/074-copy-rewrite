"""Formal RH consumer workflow provider, separate from the wallet model API."""
import json
from pathlib import Path
import re
import secrets
import threading
import time
import uuid

from image_motion import read,write
import rh_coins_experiment as experiment
import rh_coins_workflow as workflow

PROVIDER='runninghub_workflow'
LOCK=threading.RLock()


def resolve(backend):
    config=experiment.config(backend);saved=read(experiment.directory(backend)/'checked.json',{})
    candidate=experiment.CANDIDATES[config['preset']]
    return {'provider':PROVIDER,'api_key':config.get('api_key',''),'base_url':experiment.API,
        'model':'qwen-workflow-'+candidate['id'],'workflow_id':candidate['id'],'preset':config['preset'],
        'enabled':config.get('enabled') is True,'member_key_confirmed':config.get('member_key_confirmed') is True,
        'web_tested':config.get('web_tested') is True,'checked':experiment.checked(config,saved),
        'workflow':saved.get('graph'),'workflow_sha256':saved.get('workflowSha256'),
        'ratio':'9:16','resolution':'1k','concurrency':1,'auto_fallback_gpt':False}


def public_config(backend):
    try:cfg=resolve(backend)
    except (OSError,ValueError,KeyError):return {'configured':False,'has_key':False,'error':'RH币工作流配置需要重新核对'}
    return {'configured':bool(cfg['api_key'] and cfg['enabled'] and cfg['member_key_confirmed'] and cfg['web_tested'] and cfg['checked']),
        'has_key':bool(cfg['api_key']),**{key:cfg[key] for key in ('enabled','checked','model','workflow_id','base_url','concurrency','resolution','ratio')}}


def query(backend,cfg,task_id):
    if cfg.get('base_url')!=experiment.API or not isinstance(task_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}',task_id):raise ValueError('RH币原任务或站点无效')
    result=experiment.post(backend,cfg,'/task/openapi/outputs',{'apiKey':cfg.get('api_key'),'taskId':task_id})
    code=result.get('code')
    if code in (804,813):return {'status':'RUNNING' if code==804 else 'QUEUED','results':[]}
    if code==805:
        terminal=experiment.post(backend,cfg,'/task/openapi/status',{'apiKey':cfg.get('api_key'),'taskId':task_id})
        if terminal.get('code')==0 and terminal.get('data') in ('FAILED','CANCELED','CANCELLED'):
            return {'status':'FAILED','failReason':'RH状态接口确认工作流失败或已取消，请查看原任务节点原因','results':[]}
        return {'status':'PENDING','results':[]}
    outputs=result.get('data')
    if code!=0 or not isinstance(outputs,list):raise RuntimeError('RH币原任务查询暂未成功，请保留原任务编号，不要重新生成')
    images=[item for item in outputs if isinstance(item,dict) and str(item.get('fileType','')).lower() in ('png','jpg','jpeg','webp')]
    if len(images)!=1 or not isinstance(images[0].get('fileUrl'),str) or not images[0]['fileUrl'].startswith('https://'):
        raise RuntimeError('RH币原任务没有返回预期的单张图片，请核对原任务')
    return {'status':'SUCCESS','results':[{'url':images[0]['fileUrl']}]}


def generate(backend,cfg,prompt,ratio='9:16',resolution='1k',on_task_id=None):
    try:
        if not (cfg.get('enabled') and cfg.get('api_key') and cfg.get('member_key_confirmed') and cfg.get('web_tested') and cfg.get('checked')):
            raise ValueError('请先在系统设置启用并核对RH币工作流及会员Key')
        if cfg.get('base_url')!=experiment.API:raise ValueError('RH币工作流仅使用已核对的国内站')
        if str(resolution).lower()!='1k':raise ValueError('RH币工作流当前支持1K，请在任务参数选择1K')
        graph=cfg.get('workflow')
        if workflow.digest(graph)!=cfg.get('workflow_sha256'):raise ValueError('RH币完整工作流快照已变化，请重新核对')
        graph=workflow.build_graph(graph,prompt,ratio,secrets.randbits(32))
    except ValueError as error:
        raise getattr(backend,'ImageSubmissionRejected',RuntimeError)(str(error)) from None
    import image_generation_progress
    def check():
        image_generation_progress.checkpoint()
        callback=cfg.get('_checkpoint')
        if callback:callback()
    # Member concurrency is conservative. Pause checkpoints run before a queued
    # local worker can create a new paid supplier task.
    with LOCK:
        try:check()
        except InterruptedError as error:
            error.image_not_submitted=True
            raise
        root=experiment.directory(backend)/'provider-jobs'/uuid.uuid4().hex
        if not root.resolve().is_relative_to(experiment.directory(backend).resolve()):raise ValueError('RH币回执目录无效')
        path=root/'job.json';job={'status':'submitting','provider':PROVIDER,'workflowId':cfg['workflow_id'],
            'workflowSha256':workflow.digest(graph),'credential':experiment.credential(cfg),'prompt':prompt,
            'ratio':ratio,'resolution':'1k','createdAt':time.time()}
        write(root/'workflow.json',graph);write(path,job)
        try:
            response=experiment.post(backend,cfg,'/task/openapi/create',{'apiKey':cfg['api_key'],
                'workflowId':cfg['workflow_id'],'workflow':json.dumps(graph,ensure_ascii=False),'nodeInfoList':[],'instanceType':'default'})
            data=response.get('data');task_id=data.get('taskId') if isinstance(data,dict) else None
            if type(task_id) is int:task_id=str(task_id)
            if not isinstance(task_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}',task_id):
                code=response.get('code')
                if type(code) is int and code in experiment.REJECTIONS:
                    job.update(status='rejected');write(path,job)
                    raise getattr(backend,'ImageSubmissionRejected',RuntimeError)('RH币工作流拒绝提交：'+experiment.REJECTIONS[code])
                raise RuntimeError('RH币提交未取得有效任务编号，请核对原任务；不会自动重发')
            job.update(taskId=task_id,status='pending');write(path,job)
            if on_task_id:on_task_id(task_id,cfg)
            deadline=time.monotonic()+900
            while True:
                check();result=query(backend,cfg,task_id)
                if result['status']=='SUCCESS':
                    output={**result['results'][0],'provider':PROVIDER}
                    job.update(status='ok',result=output,updatedAt=time.time());write(path,job);return output
                if result['status']=='FAILED':
                    job.update(status='failed');write(path,job);raise RuntimeError(result['failReason'])
                if time.monotonic()>=deadline:raise RuntimeError('RH币原任务仍在途，任务编号已保存；稍后续跑会查询原任务')
                time.sleep(3)
        except BaseException as error:
            if job['status'] not in ('ok','failed','rejected'):job['status']='pending' if job.get('taskId') else 'unknown'
            job['updatedAt']=time.time();write(path,job)
            if isinstance(error,(InterruptedError,KeyboardInterrupt,SystemExit)) or job['status'] in ('rejected','failed'):raise
            raise RuntimeError('RH币工作流未完成；原提交记录已保留，请查询原任务，不会自动重发') from None
