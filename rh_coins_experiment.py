"""Opt-in RH consumer workflow experiment, isolated from all production providers."""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import shutil
import threading
import time
import urllib.error
import urllib.request

from image_motion import read,write
import task_cover
import rh_coins_workflow as workflow

API='https://www.runninghub.cn'
CANDIDATES={
 'qwen-simple':{'id':'1955160402595233794','name':'Qwen 文生图 · 原生候选'},
 'qwen-native':{'id':'2027264283821744129','name':'Qwen-Image ComfyUI 原生 · 备选'},
 'flux-native':{'id':'1819583592967110658','name':'FLUX 文生图 · 热门','family':'flux','note':'约1.09万浏览、200+收藏；2026-10-25核对，适合通用背景与分镜'},
 'qwen-chinese':{'id':'1954942638128599042','name':'Qwen 中文海报 · 优选','family':'qwen','note':'597浏览、52收藏；2026-10-25核对，偏中文海报'},
 'sdxl-native':{'id':'1912776705101234178','name':'SDXL 文生图 · 基础备选','family':'sdxl','note':'约394浏览、54收藏；2026-10-25核对，基础单图流程'},
}
LOCK=threading.RLock()
ACTIVE={'submitting','pending','queued','running','unknown','download_pending'}
BASE='/api/rh-coins-experiment'
REJECTIONS={301:'参数错误',380:'候选工作流不存在',416:'钱包不足，请核对是否误用了企业 Key',
    421:'平台并发额度已满',433:'工作流节点校验未通过，请在网页核对原工作流',
    801:'消费级会员等级尚不支持 API',802:'会员 Key 未授权或已失效',803:'工作流输入字段不匹配',
    810:'请先在网页保存并运行所选工作流一次',811:'Key 类型或权限不符',812:'企业钱包额度不足，请改用消费级会员 Key'}


def directory(backend):
    root=backend.DATA_DIR.resolve();folder=root/'rh-coins-experiment'
    if folder.is_symlink() or getattr(folder,'is_junction',lambda:False)() or not folder.resolve().is_relative_to(root):raise ValueError('独立实验目录无效')
    return folder


def job_directory(backend,operation):
    if not isinstance(operation,str) or not re.fullmatch(r'[a-f0-9]{32}',operation):raise ValueError('操作编号无效')
    root=directory(backend).resolve();folder=root/'jobs'/operation
    if not folder.resolve().is_relative_to(root):raise ValueError('任务目录无效')
    return folder


def credential(config):return hashlib.sha256((API+'\0'+config.get('api_key','')).encode()).hexdigest()


def config(backend):
    return {'enabled':False,'preset':'qwen-simple','member_key_confirmed':False,'web_tested':False,**read(directory(backend)/'config.json',{})}


def public(job):
    result={key:job[key] for key in ('operationId','status','taskId','prompt','ratio','createdAt','updatedAt','error','workflowId','workflowSha256','seed') if key in job}
    if job.get('status')=='ok':result['url']=BASE+'/image/'+job['operationId']
    return result


def checked(cfg,audit):
    return bool(audit.get('valid') is True and audit.get('credential')==credential(cfg) and audit.get('preset')==cfg['preset'])


def state(backend):
    import rh_workflow_catalog as catalog
    cfg=config(backend);root=directory(backend);audit=catalog.cached(backend,cfg['preset'],cfg)
    jobs=[read(path,{}) for path in (root/'jobs').glob('*/job.json')]
    return {'enabled':cfg['enabled'],'configured':bool(cfg.get('api_key')),'preset':cfg['preset'],
        'member_key_confirmed':cfg['member_key_confirmed'],'web_tested':cfg['web_tested'],
        'checked':checked(cfg,audit),'account':audit.get('account',{}) if checked(cfg,audit) else {},
        'workflow':audit.get('summary',{}) if checked(cfg,audit) else {},
        'candidates':catalog.public_entries(backend),
        'jobs':[public(job) for job in sorted(jobs,key=lambda j:j.get('createdAt',0),reverse=True)[:30]],
        'exportDirectory':str(Path.home()/'Downloads' if (Path.home()/'Downloads').is_dir() else Path.home())}


def configure(backend,data):
    allowed={'enabled','api_key','preset','member_key_confirmed','web_tested'}
    if not isinstance(data,dict) or not data or set(data)-allowed:raise ValueError('配置字段无效')
    with LOCK:
        cfg=config(backend);before=credential(cfg),cfg['preset']
        for field in ('enabled','member_key_confirmed','web_tested'):
            if field in data:
                if type(data[field]) is not bool:raise ValueError('开关必须为布尔值')
                cfg[field]=data[field]
        if 'preset' in data:
            import rh_workflow_catalog as catalog
            if not isinstance(data['preset'],str) or data['preset'] not in catalog.entries(backend):raise ValueError('请选择已保存的工作流')
            cfg['preset']=data['preset']
        if 'api_key' in data:
            key=data['api_key']
            if not isinstance(key,str):raise ValueError('会员 Key 必须为文字')
            key=key.strip()
            if key:
                if not re.fullmatch(r'[A-Za-z0-9_\-]{8,256}',key):raise ValueError('Key 格式有误，请只粘贴消费级会员 Key')
                cfg['api_key']=key
        if before!=(credential(cfg),cfg['preset']):
            cfg['web_tested']=False
            if before[0]!=credential(cfg) and data.get('member_key_confirmed') is not True:cfg['member_key_confirmed']=False
            write(directory(backend)/'checked.json',{'valid':False})
        # A new key and explicit checkbox confirmation may be saved together.
        if data.get('web_tested') is True:cfg['web_tested']=True
        if 'web_tested' in data:
            import rh_workflow_catalog as catalog
            saved=catalog.cached(backend,cfg['preset'],cfg)
            if saved.get('credential')==credential(cfg) and saved.get('preset')==cfg['preset']:
                write(catalog.cache_path(backend,cfg['preset']),{**saved,'web_tested':cfg['web_tested']})
        write(directory(backend)/'config.json',cfg)
    return state(backend)


def http_post_json(url,headers,body,timeout=30):
    """Preserve even an HTTP error JSON body: it can contain an accepted task ID."""
    request=urllib.request.Request(url,data=body,headers=headers,method='POST')
    try:response=urllib.request.urlopen(request,timeout=timeout)
    except urllib.error.HTTPError as error:response=error
    except urllib.error.URLError:raise RuntimeError('独立实验平台连接未完成') from None
    with response:
        raw=response.read(1_000_001)
        if len(raw)>1_000_000:raise RuntimeError('独立实验平台响应超过限制')
        return response.code,raw.decode('utf8')


def post(backend,cfg,path,payload):
    key=cfg.get('api_key')
    if not key:raise ValueError('请单独配置国内站消费级会员 Key')
    transport=getattr(backend,'_rh_coins_post_json',http_post_json)
    _,body=transport(API+path,{'Authorization':'Bearer '+key,'Content-Type':'application/json'},json.dumps(payload,ensure_ascii=False).encode(),timeout=30)
    result=json.loads(body)
    if not isinstance(result,dict):raise RuntimeError('平台未返回有效 JSON 对象')
    return result


def account(backend,cfg):
    result=post(backend,cfg,'/uc/openapi/accountStatus',{'apikey':cfg.get('api_key')})
    if result.get('code')!=0 or not isinstance(result.get('data'),dict):raise RuntimeError('账户资料查询未成功，请检查消费级会员 Key 和站点')
    return {key:str(result['data'][key])[:80] for key in ('remainCoins','remainMoney','currency','apiType','currentTaskCounts') if key in result['data']}


def check(backend):
    import rh_workflow_catalog as catalog
    with LOCK:
        root=directory(backend);cfg=config(backend);entry=catalog.entries(backend).get(cfg['preset'])
        if not entry:raise ValueError('工作流选择不存在')
        write(catalog.cache_path(backend,cfg['preset']),{'valid':False});write(root/'checked.json',{'valid':False})
        if cfg.get('member_key_confirmed') is not True:raise ValueError('请确认 Key 来自国内站消费级会员页面')
        info=account(backend,cfg)
        saved=catalog.inspect_entry(backend,cfg,cfg['preset'],entry,info)
        write(catalog.cache_path(backend,cfg['preset']),saved);write(root/'checked.json',saved)
    return state(backend)


def submit(backend,data):
    operation=data.get('operation_id');folder=job_directory(backend,operation);path=folder/'job.json'
    prompt=data.get('prompt');ratio=data.get('ratio')
    if not isinstance(prompt,str) or not prompt.strip() or len(prompt)>8000:raise ValueError('请填写1至8000字画面描述')
    if not isinstance(ratio,str) or ratio not in workflow.RATIOS:raise ValueError('画面比例无效')
    fingerprint=hashlib.sha256(json.dumps([prompt.strip(),ratio],ensure_ascii=False).encode()).hexdigest()
    with LOCK:
        previous=read(path,{})
        if previous:
            if previous.get('fingerprint')!=fingerprint:raise ValueError('本次操作参数已改变，请先查询原任务')
            return public(previous)
        import rh_workflow_catalog as catalog
        cfg=config(backend);root=directory(backend);audit=catalog.cached(backend,cfg['preset'],cfg)
        if cfg.get('enabled') is not True:raise ValueError('请先启用 RH 币独立实验')
        if not checked(cfg,audit) or not cfg.get('member_key_confirmed'):raise ValueError('请先核对会员 Key 和完整工作流')
        if cfg.get('web_tested') is not True:raise ValueError('请先按手册在网页运行所选工作流并确认正常出图')
        if any(read(item,{}).get('status') in ACTIVE for item in (root/'jobs').glob('*/job.json')):raise ValueError('已有在途或状态不明的任务，请先查询原任务，不会重复购买')
        graph=audit.get('graph')
        if workflow.digest(graph)!=audit.get('workflowSha256'):raise ValueError('工作流快照校验失败，请重新核对')
        try:info=account(backend,cfg)
        except (OSError,RuntimeError,ValueError):raise ValueError('账户预检暂未完成，本次未提交生成；请稍后核对配置再试') from None
        try:coins=float(info.get('remainCoins','nan'))
        except ValueError:coins=float('nan')
        if not math.isfinite(coins) or coins<=0:raise ValueError('未查询到可用 RH 币，请核对消费级会员账户')
        seed=secrets.randbits(32);graph=workflow.build_graph(graph,prompt,ratio,seed)
        job={'operationId':operation,'status':'submitting','prompt':prompt.strip(),'ratio':ratio,'seed':seed,
            'fingerprint':fingerprint,'credential':credential(cfg),'workflowId':catalog.entries(backend)[cfg['preset']]['id'],
            'workflowSha256':workflow.digest(graph),'createdAt':time.time(),'updatedAt':time.time()}
        write(folder/'workflow.json',graph);write(path,job)
    try:
        response=post(backend,cfg,'/task/openapi/create',{'apiKey':cfg['api_key'],'workflowId':job['workflowId'],
            'workflow':json.dumps(graph,ensure_ascii=False),'nodeInfoList':[],'instanceType':'default'})
        value=response.get('data');task_id=value.get('taskId') if isinstance(value,dict) else None
        if isinstance(task_id,int) and not isinstance(task_id,bool):task_id=str(task_id)
        if isinstance(task_id,str) and re.fullmatch(r'[A-Za-z0-9_-]{1,200}',task_id):
            job.update(taskId=task_id,status='pending')
        elif type(response.get('code')) is int and response['code'] in REJECTIONS:
            job.update(status='rejected',error='平台拒绝（代码 '+str(response['code'])+'）：'+REJECTIONS[response['code']]+'；未自动切换计费。')
        else:job.update(status='unknown',error='提交未返回有效任务编号，请核对 RH 任务与账单；不会自动重发。')
    except (OSError,RuntimeError,ValueError):
        job.update(status='unknown',error='未取得完整提交响应，请核对 RH 任务与账单；不会自动重发。')
    with LOCK:job['updatedAt']=time.time();write(path,job)
    return public(job)


def query(backend,operation):
    folder=job_directory(backend,operation);path=folder/'job.json'
    with LOCK:
        job=read(path,{})
        if not job:raise ValueError('测试记录不存在')
        if job.get('status')=='ok' and (folder/'result.png').is_file():return public(job)
        if job.get('status') in ('failed','rejected'):return public(job)
        if not job.get('result'):
            if not job.get('taskId'):raise ValueError('没有平台任务编号，请先核对 RH 账单；不会重新提交')
            cfg=config(backend)
            if credential(cfg)!=job.get('credential'):raise ValueError('会员 Key 已改变，请恢复原 Key 查询该任务')
            try:result=post(backend,cfg,'/task/openapi/outputs',{'apiKey':cfg['api_key'],'taskId':job['taskId']})
            except (OSError,RuntimeError,ValueError):raise RuntimeError('查询暂未成功，请稍后查询原任务，不用重新生成') from None
            code=result.get('code')
            if code in (804,813):job.update(status='running' if code==804 else 'queued',updatedAt=time.time());write(path,job);return public(job)
            if code==805:
                try:terminal=post(backend,cfg,'/task/openapi/status',{'apiKey':cfg['api_key'],'taskId':job['taskId']})
                except (OSError,RuntimeError,ValueError):terminal={}
                if terminal.get('code')==0 and terminal.get('data') in ('FAILED','CANCELED','CANCELLED'):
                    job.update(status='failed',error='平台状态接口确认任务失败或已取消，请在 RH 原任务查看节点原因；需要重试时请另开一次生成。',updatedAt=time.time());write(path,job);return public(job)
                job.update(status='unknown',error='平台返回任务状态异常（805），尚不能确认终态；请核对 RH 原任务并继续查询，不会重新生成。',updatedAt=time.time());write(path,job);return public(job)
            outputs=result.get('data')
            if code!=0 or not isinstance(outputs,list):raise RuntimeError('平台暂未返回可用结果，请继续查询原任务')
            images=[item for item in outputs if isinstance(item,dict) and str(item.get('fileType','')).lower() in ('png','jpg','jpeg','webp')]
            if len(images)!=1:raise RuntimeError('平台未返回预期的一张图片，请核对原任务；不会重复生成')
            url=images[0].get('fileUrl')
            if not isinstance(url,str) or not url.startswith('https://'):raise RuntimeError('平台图片地址无效，请核对原任务')
            job.update(status='download_pending',result={'url':url},updatedAt=time.time());write(path,job)
        try:raw=task_cover.image_bytes(job['result'])
        except (OSError,RuntimeError,ValueError):raise RuntimeError('图片取回未完成，原结果已保留；再次查询即可继续下载') from None
        target=folder/'result.png';temp=folder/'result.tmp';temp.write_bytes(raw);temp.replace(target)
        job.update(status='ok',updatedAt=time.time());job.pop('error',None);write(path,job)
        return public(job)


def media(backend,operation):
    folder=job_directory(backend,operation);target=folder/'result.png'
    if read(folder/'job.json',{}).get('status')!='ok' or not target.is_file():raise ValueError('图片尚未取回')
    return target


def export_image(backend,data):
    operation=data.get('operation_id');source=media(backend,operation);chosen=data.get('directory')
    if not isinstance(chosen,str) or not chosen.strip() or not Path(chosen).is_absolute():raise ValueError('请输入完整的保存目录')
    destination=Path(chosen).resolve()
    if not destination.is_dir():raise ValueError('保存目录不存在')
    for number in range(1,1001):
        target=destination/('RH币生图-'+operation[:8]+('' if number==1 else f' ({number})')+'.png')
        try:output=target.open('xb')
        except FileExistsError:continue
        try:
            with output,source.open('rb') as handle:shutil.copyfileobj(handle,output);output.flush();os.fsync(output.fileno())
        except BaseException:target.unlink(missing_ok=True);raise
        return {'path':str(target),'size':target.stat().st_size}
    raise ValueError('同名文件过多，请更换保存目录')
