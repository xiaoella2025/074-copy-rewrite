"""Shared Story cover result actions. Paid submissions and failure notices are durable."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import time
import urllib.request
import uuid
from PIL import Image
from image_motion import read, write
from template_store import TemplateStore

RATIOS=('3:4','9:16','1:1','4:3','16:9')

def cover_error(error):
    """Classify provider failures without returning their payloads or credentials."""
    text=str(error)
    if text.startswith('RH币工作流完整图未核对：'):
        return {'kind':'workflow_preflight','title':'所选 RH 币工作流尚未核对完整图',
                'body':'到系统设置核对这条候选工作流后再试；本次未提交生成，也没有产生 RH 任务编号。'}
    if text.startswith(('RH币工作流尚未网页实测：','RH币工作流尚未真实出图验证：')):
        return {'kind':'workflow_preflight','title':'所选 RH 币工作流尚未真实出图验证',
                'body':'请在同一账户网页运行，或完成可核对任务号的 API 单张测试；本次未提交生成，也没有产生 RH 任务编号。'}
    if text.startswith('RH币工作流配置未完成：'):
        return {'kind':'workflow_preflight','title':'RH 币工作流配置未完成',
                'body':'请到系统设置检查会员 Key 与工作流开关；本次未提交生成，也没有产生 RH 任务编号。'}
    http=re.search(r'\bHTTP\s+(\d{3})\b',text,re.I)
    if http:
        status=int(http[1])
        if status in (401,403):return {'kind':'authentication','title':f'封面提交被拒绝（HTTP {status}）','body':'绘图平台拒绝访问，请检查所选平台的凭据与权限；本次是否受理以平台记录为准。'}
        if status==429:return {'kind':'rate_limit','title':'封面提交受限（HTTP 429）','body':'绘图平台限流或额度受限；请先核对平台任务记录和账户状态。'}
        if status>=500:return {'kind':'upstream','title':f'封面请求异常（HTTP {status}）','body':'平台或网关未正常返回结果，不能据此确认是否已受理；请先核对平台任务记录。'}
    if re.search(r'content[_ ]policy|moderation|safety|sensitive|image_generation_user_error|did not (?:follow|pass)|inappropriate|nsfw|unsafe|copyright|trademark|\b(?:4001|2038)\b|违规|敏感|不允许|不通过|政策|审核|违法|侵权|色情|暴力|涉嫌|公众人物|版权|安全策略|安全检测',text,re.I):
        return {'kind':'moderation','title':'封面没出来：触发了绘图平台的内容审核（违规/审核未通过）',
                'body':'可以换一个构图方向，或点「编辑提示词」删掉敏感描述后再出图，也可以换个模板。'}
    if isinstance(error,TimeoutError) or re.search(r'超时|timeout|timed out',text,re.I):
        return {'kind':'timeout','title':'封面出图超时',
                'body':'平台排队较久，图可能已经在生成。稍后点「查图」免费取回，不要重新提交或急着重画，重画会再次计费。没有任务编号时请先核对供应商记录。'}
    if re.search(r'连接失败|connection|network|连接重置|远程主机|SSL|TLS',text,re.I):
        return {'kind':'network','title':'封面请求连接异常','body':'未取得完整平台响应，无法确认是否已受理；请先核对平台任务记录。'}
    return {'kind':'failed','title':'封面出图失败',
            'body':'请检查绘图设置。有任务编号或已返回结果时，可稍后点「查图」取回；确认上游失败后，再修改提示词或上传本地图。'}

def record_error(job_path,job,error):
    details=cover_error(error)
    diagnostic={'kind':details['kind'],'exception':type(error).__name__,'message':details['title']+'：'+details['body'],'at':time.time(),'taskIdSaved':bool(job.get('taskId'))}
    status=re.search(r'\bHTTP\s+(\d{3})\b',str(error),re.I)
    if status:diagnostic['httpStatus']=int(status[1])
    job.setdefault('firstDiagnostic',diagnostic);job['lastDiagnostic']=diagnostic
    job['error']=details['title']+'：'+details['body'];write(job_path,job)
    # Keep exception types used by callers, but never expose the upstream body.
    message=job['error']
    if isinstance(error,TimeoutError):raise TimeoutError(message) from None
    if isinstance(error,InterruptedError):raise InterruptedError(message) from None
    if isinstance(error,OSError):raise OSError(message) from None
    if isinstance(error,ValueError):raise ValueError(message) from None
    if isinstance(error,RuntimeError):raise type(error)(message) from None
    raise RuntimeError(message) from None

def prompt_key(info):
    return hashlib.sha256(json.dumps([info.get(k) for k in ('title','subtitle','template','directions','direction','ratio','withTitle','style')],ensure_ascii=False,sort_keys=True).encode()).hexdigest()

def folder_for(backend,tid):
    if not isinstance(tid,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',tid):raise ValueError('无效任务 ID')
    root=(backend.DATA_DIR/'tasks').resolve();folder=root/tid
    if not folder.is_dir() or folder.resolve().parent!=root:raise ValueError('任务不存在')
    return folder

def slot_for(data):
    slot=data.get('slot',1)
    if type(slot)!=int or slot not in (1,2):raise ValueError('无效封面编号')
    return slot

def paths(folder,slot):
    return folder/('cover-meta.json' if slot==1 else 'cover2-meta.json'),folder/f'cover-poster-{slot}.png'

def cover_template(backend,identifier,snapshot=None):
    store=TemplateStore(backend.DATA_DIR,backend.ROOT)
    if snapshot is not None:
        canonical=identifier if identifier.startswith('custom-') else backend.story_cover_template(identifier)['id']
        return store.resolve('covers',canonical,snapshot)
    if isinstance(identifier,str) and identifier.startswith('custom-'):return store.resolve('covers',identifier)
    selected=backend.story_cover_template(identifier)
    return store.resolve('covers',selected['id']) if not identifier.startswith('custom:') else selected

def view(backend,tid,slot=1):
    slot_for({'slot':slot});folder=folder_for(backend,tid)
    state=read(folder/'creative.json',{});meta=read(folder/'02-meta.json',{})
    client=read(folder/'client_config.json',{});cfg=state.get('config',{});base=client.get('cover',{})
    request=read(folder/'request.json',{});editor=read(folder/'cover-editor.json',{}).get(str(slot),{})
    template=editor.get('template') or cfg.get('coverTemplate2' if slot==2 else 'coverTemplate') or base.get('template') or request.get('cover_template') or 'cinematic-poster'
    selected=cover_template(backend,template,editor.get('template_snapshot'))
    directions=editor.get('directions',meta.get('cover_image_prompts') or meta.get('coverImagePrompts') or [])
    if not isinstance(directions,list):directions=[]
    directions=[x for x in directions if isinstance(x,str) and x.strip()]
    direction=editor.get('direction',cfg.get('coverDirection',base.get('direction',0)))
    direction_count=len(directions) if directions else len(selected.get('directions') or [])
    if type(direction)!=int or not 0<=direction<direction_count:direction=0
    style=cfg.get('style') or client.get('image',{}).get('style') or request.get('style') or ''
    style=next((s for s in backend.story_workflow_reference()['styles'] if s['id']==style or s['name']==style),None)
    title=(cfg.get('coverTitle') or base.get('title')
           or (meta['title'] if 'title' in meta else state.get('title') or request.get('title') or ''))
    subs=cfg.get('coverSubtitle') or base.get('subtitle') or (meta['subtitle'] if 'subtitle' in meta else [])
    if isinstance(subs,str):subs=subs.splitlines()
    subs=[x for x in subs if isinstance(x,str)] if isinstance(subs,list) else []
    if 'title' in editor and not editor.get('workflow_choices'):title=editor['title']
    if 'subtitle' in editor and not editor.get('workflow_choices'):subs=editor['subtitle']
    mode=editor.get('mode') or cfg.get('cover_mode') or base.get('mode') or request.get('cover_mode') or 'off'
    with_title=editor.get('withTitle',mode not in ('plain','blank'))
    ratio=editor.get('ratio') or cfg.get('coverRatio') or base.get('ratio') or request.get('cover_ratio') or '3:4'
    if ratio not in RATIOS:ratio='3:4'
    cover=read(paths(folder,slot)[0],{})
    if not cover and state.get('cover2' if slot==2 else 'cover'):cover={'url':state['cover2' if slot==2 else 'cover']}
    job=read(folder/f'cover-job-{slot}.json',{})
    error_info=cover_error(job['error']) if job.get('error') else cover_error('') if job.get('status') in ('failed','unknown') else None
    if job.get('error'):job={**job,'error':error_info['title']+'：'+error_info['body']}
    prompt=backend.compose_story_cover_prompt(directions[direction],title,subs,with_title,style,selected) if directions else ''
    if not directions and editor.get('template') and job.get('template')!=selected['id']:prompt=''
    templates=TemplateStore(backend.DATA_DIR,backend.ROOT).list('covers')
    templates=[selected if item['id']==selected['id'] else item for item in templates]
    if not any(item['id']==selected['id'] for item in templates):templates.append(selected)
    profiles=[{**{k:p.get(k,'') for k in ('id','name','model')},'enabled':bool(p.get('enabled'))} for p in backend.load_profiles() if isinstance(p,dict)]
    current_profile=next((p['id'] for p in profiles if p['enabled']),profiles[0]['id'] if profiles else '')
    task_profile=cfg.get('profile_id') or client.get('generate',{}).get('profile_id')
    result={'slot':slot,'title':title,'subtitle':subs,'template':selected['id'],'template_snapshot':selected,'templates':templates,
            'directions':directions,'direction':direction,'ratio':ratio,'withTitle':with_title,'mode':mode,'cover':cover,
            'prompt':prompt,'style':style,'provider':editor['provider'] if 'provider' in editor else cfg['coverProvider'] if 'coverProvider' in cfg else base.get('provider') or cfg.get('imageProvider') or client.get('image',{}).get('provider') or '',
            'job':job,'errorInfo':error_info,'workflow':editor.get('workflow',cfg.get('coverWorkflow',base.get('workflow',''))),'profile_id':current_profile,
            'profile_override':'','task_profile_id':task_profile,'profiles':profiles}
    if result['provider']=='runninghub_workflow':
        import rh_workflow_catalog
        result['workflows']=rh_workflow_catalog.public_entries(backend)
    result['localCoverAvailable']=bool(local_cover(backend,folder,slot,cover))
    cached=read(folder/f'cover-prompt-{slot}.json',{})
    # History stays inspectable when edited options invalidate the current prompt.
    # Never promote that history to a new paid submission automatically.
    result['lastPrompt']=next((value for value in (job.get('prompt'),cover.get('prompt'),cached.get('prompt')) if isinstance(value,str) and value.strip()),'')
    result['available']=slot==1 or bool(cover or job or editor or cfg.get('extraCover') or base.get('extra') or base.get('extraCover') or request.get('extra_cover'))
    result['imageInfo']=__import__('cover_images').view(backend,tid,slot,selection=result)
    if result['imageInfo'].get('recoveryNeeded'):result['cover']={}
    result['completed']=__import__('task_versions').completed(folder)
    if not directions and cached.get('key')==prompt_key(result):result['prompt']=cached.get('prompt','')
    return result

def sync_provider_config(folder,previous,current):
    old=(previous.get('cover') or {}).get('provider')
    new=(current.get('cover') or {}).get('provider')
    if old==new and (previous.get('cover') or {}).get('workflow')==(current.get('cover') or {}).get('workflow'):return
    provider=new or ''
    if provider=='custom':provider='custom_image'
    if provider not in ('','gpt_image','custom_image','runninghub','runninghub_workflow','modelscope','jimeng'):raise ValueError('绘图提供商无效')
    editors=read(folder/'cover-editor.json',{})
    editors['1']={**editors.get('1',{}),'provider':provider,'workflow':(current.get('cover') or {}).get('workflow','')}
    write(folder/'cover-editor.json',editors)

def validate_options(backend,data,snapshot=None):
    allowed={'slot','title','subtitle','template','direction','ratio','withTitle','provider','mode','profile_id','workflow'}
    if set(data)-allowed:raise ValueError('未知封面设置')
    if 'title' in data and (not isinstance(data['title'],str) or len(data['title'])>200):raise ValueError('封面标题最多200字')
    if 'subtitle' in data and not isinstance(data['subtitle'],list):raise ValueError('副标题须按行保存为文字列表')
    if 'subtitle' in data and any(not isinstance(x,str) or len(x)>300 for x in data['subtitle']):raise ValueError('副标题每行须为文字，最多300字；可回车换行')
    if 'template' in data:
        if not isinstance(data['template'],str):raise ValueError('封面模板不存在')
        known={x['id'] for x in TemplateStore(backend.DATA_DIR,backend.ROOT).list('covers')}
        if data['template'] not in known and not (snapshot and snapshot.get('id')==data['template']):raise ValueError('封面模板不存在')
    if 'workflow' in data and not isinstance(data['workflow'],str):raise ValueError('工作流选择必须为文字')
    if data.get('workflow'):
        import rh_workflow_catalog
        if data['workflow'] not in rh_workflow_catalog.entries(backend):raise ValueError('所选RH工作流不存在')
    if 'profile_id' in data and (not isinstance(data['profile_id'],str) or data['profile_id'] and not any(p.get('id')==data['profile_id'] for p in backend.load_profiles())):raise ValueError('所选文字模型已不存在，请重新选择')
    if 'ratio' in data and data['ratio'] not in RATIOS:raise ValueError('封面比例无效')
    if 'direction' in data and (type(data['direction'])!=int or data['direction']<0):raise ValueError('构图方向无效')
    if 'withTitle' in data and type(data['withTitle'])!=bool:raise ValueError('标题文字选项无效')
    if 'provider' in data and data['provider'] not in ('','gpt_image','custom_image','runninghub','runninghub_workflow','modelscope','jimeng'):raise ValueError('绘图提供商无效')
    if 'mode' in data and data['mode'] not in ('local','titled','plain'):raise ValueError('封面模式无效')

def image_bytes(result):
    value=result.get('b64') or result.get('url')
    if not isinstance(value,str):raise ValueError('未返回封面图片')
    if value.startswith(('https://','http://')):
        with urllib.request.urlopen(value,timeout=120) as response:raw=response.read(10_000_001)
    else:
        if len(value)>14_000_000:raise ValueError('封面图片超过10MB')
        try:raw=base64.b64decode(value,validate=True)
        except ValueError as error:raise ValueError('封面编码无效') from error
    if not raw or len(raw)>10_000_000:raise ValueError('封面图片为空或超过10MB')
    try:
        with Image.open(io.BytesIO(raw)) as im:
            if im.width*im.height>40_000_000:raise ValueError('封面像素过大')
            im.load()
            if im.format=='PNG':return raw
            out=io.BytesIO();im.convert('RGBA').save(out,'PNG');return out.getvalue()
    except (OSError,Image.DecompressionBombError) as error:raise ValueError('无法读取封面图片') from error

def commit(backend,tid,slot,raw,extra):
    return __import__('cover_images').commit(backend,tid,slot,raw,extra)


def credential(cfg):
    return hashlib.sha256(json.dumps([cfg.get('provider'),cfg.get('base_url'),cfg.get('api_key'),cfg.get('ak'),cfg.get('sk')]).encode()).hexdigest()

def is_manual_input(folder,slot):
    editor=read(folder/'cover-editor.json',{}).get(str(slot),{})
    if editor.get('mode'):return editor['mode'] in ('local','upload')
    meta=read(paths(folder,slot)[0],{})
    if meta.get('provider'):return meta['provider']=='upload'
    client=read(folder/'client_config.json',{});state=read(folder/'creative.json',{});request=read(folder/'request.json',{})
    mode=state.get('config',{}).get('cover_mode') or client.get('cover',{}).get('mode') or request.get('cover_mode')
    return mode in ('local','upload')

def copy_to_revision(backend,source,target,new_id,manual_only=False):
    """A branch owns its cover bytes; later source edits/deletion cannot affect it."""
    editors=read(source/'cover-editor.json',{});retained_editors={}
    for slot in (1,2):
        meta=read(paths(source,slot)[0],{})
        if manual_only and not is_manual_input(source,slot):
            continue
        if str(slot) in editors:retained_editors[str(slot)]=editors[str(slot)]
        candidate=Path(meta.get('path') or meta.get('local_path') or paths(source,slot)[1])
        if not candidate.is_file() and str(meta.get('url','')).startswith('/covers/'):
            candidate=backend.DATA_DIR/'covers'/Path(meta['url']).name
        if not candidate.is_file() and slot==1 and is_manual_input(source,slot):
            candidate=next((source/f'cover-upload.{ext}' for ext in ('png','jpg','webp','jpeg') if (source/f'cover-upload.{ext}').is_file()),candidate)
        if candidate.is_file() and candidate.resolve().is_relative_to(backend.DATA_DIR.resolve()):
            dest=paths(target,slot)[1];dest.write_bytes(candidate.read_bytes())
            write(paths(target,slot)[0],{**meta,**({'provider':'upload'} if manual_only else {}),'path':str(dest),'url':f'/api/task_cover/{new_id}/{slot}.png'})
        job=source/f'cover-job-{slot}.json'
        if job.is_file() and not manual_only:write(target/job.name,read(job,{}))
    if (source/'cover-editor.json').is_file():write(target/'cover-editor.json',retained_editors if manual_only else editors)

def query_provider(backend,cfg,tid):
    if cfg['provider']=='runninghub_workflow':
        import rh_workflow_provider
        return rh_workflow_provider.query(backend,cfg,tid)
    if cfg['provider']=='modelscope':
        import urllib.parse
        _,text=backend._http_get_json('https://api-inference.modelscope.cn/v1/tasks/'+urllib.parse.quote(tid,safe=''),
            {'Authorization':'Bearer '+cfg['api_key'],'X-ModelScope-Task-Type':'image_generation'})
        value=json.loads(text)
        return {'status':{'SUCCEED':'SUCCESS','FAILED':'FAILED'}.get(value.get('task_status'),'PENDING'),
                'failReason':value.get('message') or value.get('error'),
                'results':[{'url':x} for x in value.get('output_images',[]) if isinstance(x,str)]}
    _,text=backend._http_post_json(cfg.get('base_url','https://www.runninghub.ai').rstrip('/')+'/openapi/v2/query',
        {'Authorization':'Bearer '+cfg['api_key'],'Content-Type':'application/json'},json.dumps({'taskId':tid}).encode(),timeout=180)
    return backend._runninghub_result(json.loads(text))

def action(backend,tid,name,data):
    folder=folder_for(backend,tid);slot=slot_for(data)
    with backend.task_operation(tid):
        with __import__('scene_images').LOCK:__import__('cover_images').recover(folder)
        if name=='recover':return view(backend,tid,slot)
        if name!='query':__import__('cover_images').require_idle(folder)
        import task_versions
        if name in ('save','save-template','directions','generate','upload','replace-unknown') and task_versions.completed(folder):
            if name=='save':validate_options(backend,data)
            if name=='generate' and (not isinstance(data.get('operation_id'),str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',data['operation_id'])):raise ValueError('缺少有效封面操作编号')
            key='cover:'+str(slot)+':'+name+':'+(data.get('operation_id') or hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False).encode()).hexdigest())
            new_id=task_versions.fork(backend,tid,'cover',operation_key=key)
            try:
                with backend.task_operation(new_id):
                    result=_action(backend,folder_for(backend,new_id),new_id,slot,name,data)
            except Exception as error:
                error.task_id=new_id
                raise
            return {**result,'task_id':new_id,'source_task_id':tid}
        return _action(backend,folder,tid,slot,name,data)

def require_idle(folder):
    __import__('cover_images').require_idle(folder)
    for slot in (1,2):
        if read(folder/f'cover-job-{slot}.json',{}).get('status') in ('submitting','unknown','pending','download_pending'):
            raise ValueError('封面在途或提交状态不明，请先查图或核对供应商记录，不能破坏性重跑')

def rerun_files(folder):
    """Explicit AI cover rerun clears terminal jobs; manual images remain owned."""
    editors=read(folder/'cover-editor.json',{});files=[]
    for slot in (1,2):
        if editors.get(str(slot),{}).get('mode')=='local':continue
        files += [f'cover-poster-{slot}.png',paths(folder,slot)[0].name,f'cover-job-{slot}.json']
    return files

def build_selected_prompt(backend,folder,info,checkpoint=None):
    """Only missing work uses the current system model and saved cover composition."""
    state=read(folder/'creative.json',{})
    content=(folder/'02-rewrite.txt').read_text('utf8') if (folder/'02-rewrite.txt').exists() else state.get('lyrics') or state.get('config',{}).get('copy','')
    if not content.strip():raise ValueError('未找到改写文案，无法生成封面构图')
    selected=info['template_snapshot'];presets=selected.get('directions') or [{'hint':''}]
    direction=presets[min(info['direction'],len(presets)-1)]
    system=('你是短视频封面视觉策划。根据文案生成一条竖屏封面海报的画面描述，50-100字，'
            '只描述画面内容（主体、构图、光线、氛围），不写画风词、不写任何文字内容。'+selected['compositionRule'])
    if checkpoint:checkpoint()
    llm=backend.resolve_active_llm_settings()
    import visual_requirements
    system+='\n'+visual_requirements.block(visual_requirements.load(folder))
    visual=backend.call_llm(llm,system,'原文全文：\n'+content+'\n封面主标题：'+info['title']+'\n方向：'+direction['hint']).strip()
    if not visual:raise ValueError('未生成封面构图，请重试')
    return visual_requirements.apply(backend.compose_story_cover_prompt(visual,info['title'],info['subtitle'],info['withTitle'],info['style'],selected),visual_requirements.load(folder))

def replacement_intent(job):
    return job.get('status') in ('replacement_ready','unsubmitted') and bool(job.get('replacement'))

def local_cover(backend,folder,slot,cover):
    """Find validated owned bytes before considering another paid operation."""
    candidates=[Path(cover.get('path') or cover.get('local_path') or paths(folder,slot)[1]),paths(folder,slot)[1]]
    if str(cover.get('url','')).startswith('/covers/'):candidates.append(backend.DATA_DIR/'covers'/Path(cover['url']).name)
    if slot==1:candidates.extend(folder/f'cover-upload.{ext}' for ext in ('png','jpg','webp','jpeg'))
    candidates.append(folder/'covers'/('poster.png' if slot==1 else 'poster2.png'))
    for candidate in candidates:
        if not candidate.is_file() or not candidate.resolve().is_relative_to(backend.DATA_DIR.resolve()):continue
        try:raw=image_bytes({'b64':base64.b64encode(candidate.read_bytes()).decode()})
        except (ValueError,OSError):continue
        return candidate,raw
    return None

def _prepare_failed_rerun(backend,folder,tid,slot,info):
    """A claimed, explicit step-six rerun may buy one replacement for a failed cover."""
    queue=getattr(backend,'TASK_QUEUE',None)
    rerun=queue.get(tid) if queue else None
    job=info['job']
    if (job.get('status')!='failed' or job.get('result') or not isinstance(rerun,dict)
            or rerun.get('status')!='running' or str(rerun.get('from_step'))!='6' or not rerun.get('rerun_prepared')):
        return info
    queue_id=rerun.get('id')
    if (not isinstance(queue_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,70}',queue_id)
            or (job.get('replacement') or {}).get('retryQueueId')==queue_id):return info
    provider=info['provider'] or backend.resolve_image_config(backend.load_settings()).get('provider')
    if not provider:raise ValueError('请先选择封面绘图引擎')
    op='rerun-cover-'+queue_id
    job_path=folder/f'cover-job-{slot}.json'
    archive=folder/'.cover-replacements'/f'{slot}-{op}.json'
    archive.parent.mkdir(exist_ok=True)
    old_bytes=job_path.read_bytes()
    if archive.exists():
        if archive.read_bytes()!=old_bytes:raise ValueError('封面重跑编号已有其他归档，请核对原记录')
    else:
        temporary=archive.with_suffix('.'+uuid.uuid4().hex+'.tmp')
        try:
            with temporary.open('wb') as handle:
                handle.write(old_bytes);handle.flush();os.fsync(handle.fileno())
            os.replace(temporary,archive)
        finally:temporary.unlink(missing_ok=True)
    write(job_path,{'status':'replacement_ready','operationId':op,'provider':provider,'targetProvider':provider,
                    'replacement':{'archive':str(archive.relative_to(folder)),'previousProvider':job.get('provider'),
                                   'previousStatus':'failed','retryQueueId':queue_id,'confirmedAt':time.time()}})
    return view(backend,tid,slot)

def initial(backend,tid,slot=1,prompt_factory=None,data_url=None,options=None,explicit_prompt=None,local_only=False,checkpoint=None):
    """Caller already owns the workflow lease; never reacquire it here."""
    folder=folder_for(backend,tid)
    with __import__('scene_images').LOCK:__import__('cover_images').recover(folder)
    __import__('cover_images').require_idle(folder)
    info=view(backend,tid,slot);job=info['job'];cover=info['cover']
    cached=local_cover(backend,folder,slot,cover)
    if cached:
        candidate,raw=cached
        if candidate==paths(folder,slot)[1] and cover.get('url'):return cover
        return commit(backend,tid,slot,raw,cover)
    info=_prepare_failed_rerun(backend,folder,tid,slot,info);job=info['job'];cover=info['cover']
    if job.get('status') in ('submitting','unknown','pending','download_pending'):
        if not (job.get('taskId') or job.get('result')):
            cause=(job.get('firstDiagnostic') or {}).get('message') or '旧记录未保存首次异常的具体原因'
            raise ValueError('初次封面提交状态不明；首次原因：'+cause+'；请核对供应商记录，不会重复购买')
        result=_action(backend,folder,tid,slot,'query',{'slot':slot},checkpoint=checkpoint)
        if result['job'].get('status')!='ok':raise RuntimeError('原封面任务尚未完成，请稍后续跑/查图')
        return result['cover']
    replacement=replacement_intent(job)
    if replacement:
        selected=info['provider'] or backend.resolve_image_config(backend.load_settings()).get('provider')
        if selected!=job.get('targetProvider'):raise ValueError('已确认的新封面引擎与当前保存设置不一致，请恢复已确认的引擎')
    if job.get('status')=='ok' and (job.get('result') or job.get('taskId')):
        return _action(backend,folder,tid,slot,'query',{'slot':slot},checkpoint=checkpoint)['cover']
    if job.get('status')=='failed':raise ValueError('原封面生成已失败；请在“生成剪映草稿”修改封面引擎后保存并重跑，或上传本地图')
    if data_url:return _action(backend,folder,tid,slot,'upload',{'slot':slot,'data_url':data_url})['cover']
    if local_only or info['mode'] in ('local','upload') or cover.get('provider')=='upload':raise ValueError('本地封面缺失，请重新上传；不会改用收费绘图')
    if cover and not replacement:raise ValueError('旧封面缓存丢失且没有可查询的供应商编号，请查供应商记录或上传本地图；不会自动再次购买')
    editor=read(folder/'cover-editor.json',{}).get(str(slot),{})
    own_text_choices=not editor.get('workflow_choices') and any(key in editor for key in ('profile_id','template','title','subtitle','withTitle','direction'))
    preset_hint=''
    if options:
        options=dict(options)
        if replacement:options.pop('provider',None)
        # A later card edit owns its slot; a queued request is an older snapshot.
        for key in ('provider','workflow','template','direction','ratio','withTitle','profile_id','title','subtitle'):
            if key in editor and not editor.get('workflow_choices'):options.pop(key,None)
        # Creation uses a template preset index; metadata may return fewer
        # visual alternatives. Keep that preset hint, use an existing visual,
        # and leave the direct editor's strict generated-index validation intact.
        identifier=options.get('template',info['template'])
        selected=cover_template(backend,identifier,info['template_snapshot'] if identifier==info['template'] else None)
        requested=options.get('direction',0)
        presets=selected.get('directions') or []
        if info['directions'] and type(requested)==int and len(info['directions'])<=requested<len(presets):
            preset_hint=presets[requested].get('hint','')
            options['direction']=0
        # The queued request is a snapshot; a later explicit engine edit owns the choice.
        if 'provider' in read(folder/'cover-editor.json',{}).get(str(slot),{}):options.pop('provider',None)
        validate_options(backend,options);_action(backend,folder,tid,slot,'save',{'slot':slot,**options},workflow=True);info=view(backend,tid,slot)
    prompt=explicit_prompt or info['prompt'] or (build_selected_prompt(backend,folder,info,checkpoint) if own_text_choices else prompt_factory() if prompt_factory else '')
    if preset_hint and not explicit_prompt:prompt+='\n构图要求：'+preset_hint
    if isinstance(prompt,str) and prompt.strip():write(folder/f'cover-prompt-{slot}.json',{'key':prompt_key(info),'prompt':prompt})
    if checkpoint:checkpoint()
    return _action(backend,folder,tid,slot,'generate',{'slot':slot,'operation_id':job['operationId'] if replacement else f'workflow-cover-{slot}','prompt':prompt},checkpoint=checkpoint)['cover']

def _action(backend,folder,tid,slot,name,data,checkpoint=None,workflow=False):
    info=view(backend,tid,slot);job_path=folder/f'cover-job-{slot}.json';job=read(job_path,{})
    pending=job.get('status') in ('submitting','unknown','pending','download_pending')
    if name=='replace-unknown':
        if set(data)-{'slot','provider','operation_id','acknowledge_unknown'}:raise ValueError('未知封面替换设置')
        op=data.get('operation_id');provider=data.get('provider')
        if not isinstance(op,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',op):raise ValueError('缺少有效封面操作编号')
        if data.get('acknowledge_unknown') is not True:raise ValueError('请明确确认旧封面提交结果仍待核对及新引擎费用')
        validate_options(backend,{'provider':provider})
        if not provider:raise ValueError('请明确选择新的封面引擎')
        # A retry may arrive after the new operation has started or completed.
        if job.get('operationId')==op and job.get('replacement'):
            if job.get('targetProvider')!=provider:raise ValueError('本次封面操作的目标引擎已经固定')
            return info
        if slot!=1 or job.get('status') not in ('unknown','submitting') or job.get('taskId') or job.get('result') or job.get('operationId')==op:
            raise ValueError('仅可替换无任务编号、无结果的未知主封面提交')
        if not job.get('provider') or provider==job.get('provider') or provider!=info['provider']:raise ValueError('新引擎必须与旧单不同，并与已保存的封面设置一致')
        if local_cover(backend,folder,slot,info['cover']):raise ValueError('已有合法本地封面，请直接继续打包，无需再次生成')
        archive=folder/'.cover-replacements'/f'{slot}-{op}.json';archive.parent.mkdir(exist_ok=True)
        old_bytes=job_path.read_bytes()
        if archive.exists():
            if archive.read_bytes()!=old_bytes:raise ValueError('封面操作编号已有其他归档，请核对原记录')
        else:
            # Complete archive before changing the original receipt. Failed writes
            # leave the original authoritative record intact.
            temporary=archive.with_suffix('.'+uuid.uuid4().hex+'.tmp')
            try:
                with temporary.open('wb') as handle:
                    handle.write(old_bytes);handle.flush();os.fsync(handle.fileno())
                os.replace(temporary,archive)
            finally:temporary.unlink(missing_ok=True)
        write(job_path,{'status':'replacement_ready','operationId':op,'provider':provider,'targetProvider':provider,
                        'replacement':{'archive':str(archive.relative_to(folder)),'previousProvider':job['provider'],'confirmedAt':time.time()}})
        return view(backend,tid,slot)
    if name in ('upload','generate') and pending:raise ValueError('封面在途或提交状态不明，请先查图或核对供应商记录；不会重复购买')
    if name=='save-template':
        if pending:raise ValueError('封面正在生成，请先查询原任务')
        if set(data)-{'slot','template'}:raise ValueError('未知模板设置')
        # Save a reusable copy, then pin it to this slot. Library edits never
        # silently change an existing task's prompt or the other cover.
        saved=TemplateStore(backend.DATA_DIR,backend.ROOT).save('covers',data.get('template'))
        editors=read(folder/'cover-editor.json',{})
        editors[str(slot)]={**editors.get(str(slot),{}),'title':info['title'],'subtitle':info['subtitle'],'template':saved['id'],'template_snapshot':saved,'direction':0,'workflow_choices':False}
        write(folder/'cover-editor.json',editors)
        return view(backend,tid,slot)
    if name=='save':
        snapshot=info['template_snapshot'] if data.get('template',info['template'])==info['template'] else None
        validate_options(backend,data,snapshot)
        selected=cover_template(backend,data.get('template',info['template']),snapshot)
        direction_count=len(info['directions']) if info['directions'] else len(selected.get('directions') or [])
        if 'direction' in data and data['direction']>=direction_count:raise ValueError('构图方向不存在')
        editors=read(folder/'cover-editor.json',{});previous=editors.get(str(slot),{})
        editors[str(slot)]={**previous,'title':info['title'],'subtitle':info['subtitle'],**{k:v for k,v in data.items() if k!='slot'},'template':selected['id'],'template_snapshot':selected,
                           'workflow_choices':bool(workflow and (previous.get('workflow_choices') or not previous))}
        if 'template' in data and data['template']!=info['template'] and 'direction' not in data:editors[str(slot)]['direction']=0
        if 'title' in data and slot==1:editors['titleEdited']=True
        if 'subtitle' in data and slot==1:editors['subtitleEdited']=True
        write(folder/'cover-editor.json',editors)
        if any(key in data for key in ('provider','workflow')) and slot==1 and (folder/'client_config.json').is_file():
            client=read(folder/'client_config.json',{})
            client['cover']={**(client.get('cover') or {}),**{key:data[key] for key in ('provider','workflow') if key in data}}
            write(folder/'client_config.json',client)
        if slot==1 and ('title' in data or 'subtitle' in data):
            meta=read(folder/'02-meta.json',{});meta.update({k:v for k,v in data.items() if k in ('title','subtitle')});write(folder/'02-meta.json',meta)
        return view(backend,tid,slot)
    if name=='directions':
        if pending:raise ValueError('封面正在生成，请先查询原任务')
        template=data.get('template',info['template']);snapshot=info['template_snapshot'] if template==info['template'] else None
        validate_options(backend,{'template':template},snapshot)
        state=read(folder/'creative.json',{});content=(folder/'02-rewrite.txt').read_text('utf8') if (folder/'02-rewrite.txt').exists() else state.get('lyrics') or state.get('config',{}).get('copy','')
        if not content.strip():raise ValueError('未找到改写文案，无法生成构图方向')
        llm=backend.resolve_active_llm_settings()
        if not llm.get('api_key'):raise ValueError('请先配置 LLM 凭据')
        selected=cover_template(backend,template,snapshot)
        llm={**llm,'_prompt_template':{'step1MetadataSystemPrompt':backend.load_prompt_module('step1_meta.py')+'\n封面构图要求：'+selected['compositionRule']}}
        generated=backend.step1_meta(llm,info['title'],content,[],read(folder/'request.json',{}).get('track','character-story'))
        directions=generated.get('cover_image_prompts',[])
        if not isinstance(directions,list) or not directions or any(not isinstance(x,str) or not x.strip() for x in directions):raise ValueError('未生成构图方向，请重试')
        editors=read(folder/'cover-editor.json',{});editors[str(slot)]={**editors.get(str(slot),{}),'title':info['title'],'subtitle':info['subtitle'],'template':selected['id'],'template_snapshot':selected,'direction':0,'directions':directions,'workflow_choices':False};write(folder/'cover-editor.json',editors)
        return view(backend,tid,slot)
    if name=='upload':
        uri=data.get('data_url','');match=re.fullmatch(r'data:image/(?:png|jpeg|webp);base64,([A-Za-z0-9+/=]+)',uri) if isinstance(uri,str) else None
        if not match:raise ValueError('请上传PNG/JPG/WEBP封面')
        raw=image_bytes({'b64':match[1]});commit(backend,tid,slot,raw,{'provider':'upload','prompt':'(本地上传)'})
        editors=read(folder/'cover-editor.json',{});editors[str(slot)]={**editors.get(str(slot),{}),'mode':'local'};write(folder/'cover-editor.json',editors)
        write(job_path,{});return view(backend,tid,slot)
    if name not in ('generate','query'):raise ValueError('封面操作不存在')
    if name=='generate':
        op=data.get('operation_id')
        if not isinstance(op,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',op):raise ValueError('缺少有效封面操作编号')
        if replacement_intent(job) and (op!=job.get('operationId') or info['provider']!=job.get('targetProvider')):
            raise ValueError('请继续已确认的封面操作及目标引擎，不能重置替换意图')
        if job.get('operationId')==op and job.get('status')=='ok':
            if paths(folder,slot)[1].is_file():return info
            if job.get('taskId') or job.get('result'):return _action(backend,folder,tid,slot,'query',{'slot':slot},checkpoint=checkpoint)
            raise ValueError('本次生成的缓存丢失，请先核对供应商记录')
    # A saved image is already paid for. Download/restore it without consulting
    # current provider settings; ID-only queries still verify original credentials.
    cfg=({'provider':job.get('provider') or info['provider']}
         if name=='query' and job.get('result') else
         backend.resolve_image_config(backend.load_settings(),job.get('provider') if name=='query' else info['provider'] or None))
    if name=='generate' and cfg.get('provider')=='runninghub_workflow':
        import rh_workflow_provider
        cfg=rh_workflow_provider.resolve(backend,info.get('workflow'))
    if name=='generate' and replacement_intent(job) and cfg.get('provider')!=job.get('targetProvider'):raise ValueError('当前绘图配置与已确认的新封面引擎不一致')
    task_config=read(folder/'creative.json',{}).get('config',{})
    if name=='query' and job.get('model'):cfg={**cfg,'model':job['model']}
    elif name=='generate' and 'coverProvider' not in task_config and task_config.get('imageModel') and task_config.get('imageProvider')==cfg.get('provider'):
        from creative_workflows import image_config
        cfg=image_config(backend,backend.load_settings(),task_config)
    cfg={**cfg,'auto_fallback_gpt':bool(cfg.get('auto_fallback_gpt') and cfg.get('fallback_provider')=='runninghub' and not replacement_intent(job))}
    if name=='query' and cfg['provider']=='modelscope':
        cfg=next(({**cfg,'api_key':token} for token in cfg.get('tokens') or [cfg.get('api_key')] if credential({**cfg,'api_key':token})==job.get('credential')),cfg)
    if not (name=='query' and job.get('result')) and not cfg.get('api_key') and not (cfg.get('ak') and cfg.get('sk')):raise ValueError('请先配置绘图凭据')
    if name=='query':
        result=job.get('result')
        if not result:
            if not job.get('taskId') or job.get('provider') not in ('runninghub','runninghub_workflow','modelscope'):raise ValueError('没有可查询的供应商任务编号，请核对供应商记录')
            if job.get('credential')!=credential(cfg):raise ValueError('绘图凭据或服务地址已经变化，请恢复原设置再查图')
            if checkpoint:checkpoint()
            try:response=query_provider(backend,cfg,job['taskId'])
            except Exception as error:record_error(job_path,job,error)
            if response.get('status')=='FAILED':
                job['status']='failed'
                record_error(job_path,job,ValueError(response.get('failReason') or response.get('errorMessage') or response.get('errorCode') or response.get('error') or response.get('message') or '上游确认封面失败'))
            if response.get('status')!='SUCCESS':return {**info,'message':'上游还在排队/生成中，请稍后查图'}
            result=next((x for x in response.get('results',[]) if isinstance(x,dict) and x.get('url')),None)
            if not result:raise ValueError('上游成功但没有封面图片地址')
    else:
        prompt=data.get('prompt',info['prompt'])
        if not isinstance(prompt,str) or not prompt.strip() or len(prompt)>20000:raise ValueError('封面提示词应为1至20000字')
        import visual_requirements
        prompt=visual_requirements.apply(prompt,visual_requirements.load(folder))
        if checkpoint:checkpoint()
        retained={k:job[k] for k in ('replacement','targetProvider') if k in job} if replacement_intent(job) else {}
        job={**retained,'operationId':op,'status':'submitting','provider':cfg['provider'],'model':cfg.get('model'),'credential':credential(cfg),'prompt':prompt,'ratio':info['ratio'],'template':info['template']};write(job_path,job)
        def remember(task_id,actual_cfg=None):
            used=actual_cfg or cfg
            job.update(taskId=task_id,status='pending',provider=used['provider'],model=used.get('model'),credential=credential(used));write(job_path,job)
        if cfg.get('provider')=='runninghub_workflow':cfg={**cfg,'_checkpoint':checkpoint}
        try:result=backend.image_dispatcher(cfg,prompt,ratio=info['ratio'],resolution=cfg.get('resolution') or '1k',on_task_id=remember)
        except Exception as error:
            job['status']='unsubmitted' if getattr(error,'image_not_submitted',False) else 'failed' if isinstance(error,backend.ImageSubmissionRejected) else 'pending' if job.get('taskId') else 'unknown'
            record_error(job_path,job,error)
    job['result']={k:result[k] for k in ('url','b64') if isinstance(result,dict) and isinstance(result.get(k),str)}
    job['status']='download_pending';write(job_path,job)
    if checkpoint:checkpoint()
    try:raw=image_bytes(job['result'])
    except Exception as error:
        # A completed, invalid output is terminal; transport failures remain resumable.
        if isinstance(error,ValueError):job['status']='failed'
        record_error(job_path,job,error)
    commit(backend,tid,slot,raw,{'prompt':job.get('prompt',''),'provider':job.get('provider',cfg['provider']),'provider_task_id':job.get('taskId')})
    job['status']='ok';job.pop('error',None);write(job_path,job);return view(backend,tid,slot)
