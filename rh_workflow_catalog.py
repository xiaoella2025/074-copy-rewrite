"""Local workflow entries and independently checked full graphs; never submits."""
import json
import re
import time
from urllib.parse import urlsplit
from image_motion import read,write
import rh_workflow_graphs as graphs
import rh_coins_workflow as workflow


def key_value(key):
    if not isinstance(key,str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,80}',key):raise ValueError('工作流选择无效')
    return key


def entries(backend):
    import rh_coins_experiment as experiment
    path=experiment.directory(backend)/'workflow-catalog.json'
    custom=json.loads(path.read_text('utf8')) if path.exists() else {}
    if not isinstance(custom,dict):raise ValueError('工作流目录损坏，请保留文件并检查')
    for key,entry in custom.items():
        key_value(key)
        if not isinstance(entry,dict) or not re.fullmatch(r'\d{10,30}',str(entry.get('id',''))) or key!='custom-'+entry['id']:
            raise ValueError('自定义工作流目录无效')
    return {**experiment.CANDIDATES,**custom}


def cache_path(backend,key):
    import rh_coins_experiment as experiment
    return experiment.directory(backend)/'checked-workflows'/(key_value(key)+'.json')


def cached(backend,key,cfg=None):
    import rh_coins_experiment as experiment
    saved=read(cache_path(backend,key),{})
    if not saved:
        legacy=read(experiment.directory(backend)/'checked.json',{})
        if legacy.get('preset')==key:saved=legacy
    return saved


def api_tested(saved):
    proof=saved.get('api_test') if isinstance(saved,dict) else None
    return bool(isinstance(proof,dict) and saved.get('valid') is True
                and proof.get('status')=='ok' and proof.get('workflowId')==saved.get('workflowId')
                and proof.get('sourceSha256')==saved.get('sourceSha256')
                and proof.get('credential')==saved.get('credential')
                and isinstance(proof.get('taskId'),str) and re.fullmatch(r'[A-Za-z0-9_-]{1,200}',proof['taskId'])
                and isinstance(proof.get('imageSha256'),str) and re.fullmatch(r'[a-f0-9]{64}',proof['imageSha256']))


def api_cost_range(saved):
    proof=saved.get('api_test',{})
    values=[proof.get('spentCoins')]+[x.get('consumeCoins') for x in proof.get('costObservations',[]) if isinstance(x,dict)]
    costs=[value for value in values if type(value) is int and value>0]
    return [min(costs),max(costs)] if costs else None


def inspect_entry(backend,cfg,key,entry,account=None):
    import rh_coins_experiment as experiment
    if cfg.get('member_key_confirmed') is not True:raise ValueError('请先保存并确认国内站会员Key')
    value=experiment.post(backend,cfg,'/api/openapi/getJsonApiFormat',{'apiKey':cfg.get('api_key'),'workflowId':entry['id']})
    raw=value.get('data',{}).get('prompt') if isinstance(value.get('data'),dict) else None
    if value.get('code')!=0 or not isinstance(raw,str) or len(raw)>200000:raise ValueError('没有读到完整工作流，请核对链接和账户权限；未提交生成')
    try:source=json.loads(raw);prepared=graphs.prepare(source)
    except (KeyError,TypeError,IndexError):raise ValueError('工作流接线或字段不完整，暂不能自动接入') from None
    saved={'valid':True,'credential':experiment.credential(cfg),'preset':key,'workflowId':entry['id'],
           'account':account or {},'graph':prepared['graph'],'workflowSha256':workflow.digest(prepared['graph']),
           'sourceSha256':workflow.digest(source),'summary':prepared['summary'],'checkedAt':time.time(),
           'web_tested':cfg.get('web_tested') is True}
    previous=cached(backend,key,cfg)
    if (api_tested(previous) and previous.get('sourceSha256')==saved['sourceSha256']
            and previous.get('workflowSha256')==saved['workflowSha256']
            and previous.get('credential')==saved['credential']):
        saved['api_test']=previous['api_test']
    return saved


def public_entries(backend):
    import rh_coins_experiment as experiment
    cfg=experiment.config(backend);result=[]
    for key,entry in entries(backend).items():
        saved=cached(backend,key,cfg);valid=experiment.checked({**cfg,'preset':key},saved)
        result.append({'key':key,'id':entry['id'],'name':entry['name'],'url':experiment.API+'/post/'+entry['id'],
                       'note':entry.get('note','单张费用未实测'),'family':entry.get('family') or saved.get('summary',{}).get('kind',''),
                       'checked':valid,'web_tested':saved.get('web_tested',False) if valid else False,
                       'api_tested':api_tested(saved) if valid else False,
                       'api_test_cost':saved.get('api_test',{}).get('spentCoins') if valid and api_tested(saved) else None,
                       'api_test_cost_range':api_cost_range(saved) if valid and api_tested(saved) else None,
                       'summary':saved.get('summary',{}) if valid else {}})
    return result


def identifier(value):
    if not isinstance(value,str):raise ValueError('请填写工作流链接或ID')
    value=value.strip()
    if re.fullmatch(r'\d{10,30}',value):return value
    url=urlsplit(value)
    if (url.scheme!='https' or url.netloc not in ('www.runninghub.cn','runninghub.cn') or url.query or url.fragment
            or not re.fullmatch(r'/(?:post|workflow)/\d{10,30}/?',url.path)):
        raise ValueError('请粘贴国内站post/workflow链接或纯数字ID，链接不要带参数')
    return url.path.strip('/').split('/')[-1]


def add(backend,data):
    import rh_coins_experiment as experiment
    if not isinstance(data,dict) or set(data)!={'name','url'}:raise ValueError('请填写工作流名称和链接或ID')
    name=data['name']
    if not isinstance(name,str) or not name.strip() or len(name)>60:raise ValueError('工作流名称需要1至60字')
    wid=identifier(data['url']);key='custom-'+wid
    with experiment.LOCK:
        cfg=experiment.config(backend);entry={'id':wid,'name':name.strip()}
        saved=inspect_entry(backend,{**cfg,'web_tested':False},key,entry)
        entry['family']=saved['summary']['kind']
        path=experiment.directory(backend)/'workflow-catalog.json'
        custom=json.loads(path.read_text('utf8')) if path.exists() else {}
        if not isinstance(custom,dict):raise ValueError('原工作流目录损坏，未覆盖')
        write(cache_path(backend,key),saved);write(path,{**custom,key:entry})
    return {'ok':True,'added':key,'candidates':public_entries(backend),
            'message':'已核对并添加；默认工作流未改，未提交生成。选择后请确认同账户网页跑通。'}
