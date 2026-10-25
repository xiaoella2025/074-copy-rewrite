"""Cover slots with immutable pixel history and recoverable metadata commits.

Viewing is read-only. Local edits use the scene editor's geometry and image
validation, but never share its numbered scene files or paid receipts.
"""
import base64,hashlib,json,re,time,uuid
import scene_images as images
from image_motion import read,write

PENDING=images.PENDING

def context(backend,tid,slot):
 import task_cover
 task_cover.slot_for({'slot':slot});folder=task_cover.folder_for(backend,tid)
 meta,target=task_cover.paths(folder,slot)
 for path in (meta,target,folder/'.cover-images',folder/'cover-images.json',folder/'cover-image-transaction.json'):
  if not path.resolve().is_relative_to(folder.resolve()):raise ValueError('封面图片路径越界')
 return folder,meta,target

def source(backend,tid,slot):
 import task_cover
 folder,meta_path,target=context(backend,tid,slot)
 meta=read(meta_path,{})
 found=task_cover.local_cover(backend,folder,slot,meta)
 if found:return found
 return (target,target.read_bytes()) if target.is_file() else (target,None)

def revision(raw):return hashlib.sha256(raw).hexdigest() if raw else 'empty'

def store(folder,raw):
 path=folder/'.cover-images'/('image-'+revision(raw)+'.png');path.parent.mkdir(exist_ok=True)
 if not path.exists():path.write_bytes(raw)
 return path.relative_to(folder).as_posix()

def manifest(folder):
 value=read(folder/'cover-images.json',{'version':1,'items':{}})
 if value.get('version')!=1 or not isinstance(value.get('items'),dict):raise ValueError('封面图片历史损坏，请保留原记录')
 return value

def recover(folder):
 journal=folder/'cover-image-transaction.json'
 if not journal.exists():return
 tx=read(journal,{})
 for source,target in tx['copies']:
  src=images.bounded(folder,source);dest=images.bounded(folder,target)
  tmp=dest.with_name(dest.name+'.'+uuid.uuid4().hex+'.tmp')
  try:tmp.write_bytes(src.read_bytes());__import__('os').replace(tmp,dest)
  finally:tmp.unlink(missing_ok=True)
 for relative,value in tx['writes'].items():write(images.bounded(folder,relative),value)
 journal.unlink()

def commit(backend,tid,slot,raw,extra,extra_writes=None):
 import task_cover
 folder,meta_path,target=context(backend,tid,slot)
 with images.LOCK:
  recover(folder);raw=images.png_bytes(raw);data=manifest(folder);item=data['items'].get(str(slot),{})
  previous=source(backend,tid,slot)[1]
  oldmeta=read(meta_path,{})
  history=item.get('history',[])
  if previous is not None:
   prior=store(folder,previous)
   origin=item.get('origin') if item.get('revision')==revision(previous) else prior
   history=[{'id':uuid.uuid4().hex,'file':prior,'origin':origin or prior,'crop':item.get('crop') if item.get('revision')==revision(previous) else None,'meta':oldmeta,'savedAt':time.time()},*history][:5]
  extra=dict(extra);crop=extra.pop('_cover_crop',None);origin=extra.pop('_cover_origin',None)
  current=store(folder,raw);origin=origin or current
  # Every referenced path is owned by this task, including restored origins.
  images.bounded(folder,origin)
  value={**extra,'path':str(target),'url':f'/api/task_cover/{tid}/{slot}.png','updatedAt':time.time_ns()}
  data['items'][str(slot)]={'file':current,'origin':origin,'crop':crop,'revision':revision(raw),'history':history}
  writes={meta_path.name:value,'cover-images.json':data,**(extra_writes or {})}
  if (folder/'creative.json').is_file():
   state=read(folder/'creative.json',{});state['cover2' if slot==2 else 'cover']=value['url'];state['revision']=state.get('revision',0)+1;writes['creative.json']=state
  write(folder/'cover-image-transaction.json',{'copies':[[current,target.name]],'writes':writes});recover(folder)
  return value

def view(backend,tid,slot,selection=None):
 if selection is None:return __import__('task_cover').view(backend,tid,slot)['imageInfo']
 folder,meta_path,target=context(backend,tid,slot)
 with images.LOCK:
  if (folder/'cover-image-transaction.json').exists():return {'recoveryNeeded':True,'current':None,'original':None,'actualPrompt':'','history':[],'revision':'recover','ratio':selection['ratio'],'referenceJob':{}}
  raw=source(backend,tid,slot)[1];data=manifest(folder);item=data['items'].get(str(slot),{})
  same=item.get('revision')==revision(raw);meta=read(meta_path,{})
  base=f'/api/cover-image/{tid}/{slot}/'
  width=height=0
  if raw:
   try:
    with images.Image.open(__import__('io').BytesIO(raw)) as im:width,height=im.size
   except (OSError,ValueError):pass
  editor=read(folder/'cover-editor.json',{}).get(str(slot),{})
  cfg=read(folder/'client_config.json',{}).get('cover',{})
  job=read(folder/f'cover-reference-{slot}.json',{})
  return {'index':slot,'slot':slot,'current':base+'current.png' if raw else None,'original':base+'original.png' if raw else None,
   'revision':revision(raw),'width':width,'height':height,'ratio':selection['ratio'],'crop':item.get('crop') if same else None,
   'actualPrompt':meta.get('prompt','') if raw else '', 'provider':meta.get('provider',''),
   'history':[{'id':e['id'],'url':base+e['id']+'.png','savedAt':e['savedAt'],'prompt':e.get('meta',{}).get('prompt',''),'provider':e.get('meta',{}).get('provider','')} for e in item.get('history',[])],
   'editProviderLabel':selection['provider'] or '跟随系统',
   'referenceJob':{k:job[k] for k in ('status','taskId','provider','operationId','prompt','error') if k in job}}

def media(backend,tid,slot,key):
 folder,_,target=context(backend,tid,slot)
 with images.LOCK:
  if key=='current':return source(backend,tid,slot)[0]
  item=manifest(folder)['items'].get(str(slot),{})
  if key=='original':
   current,raw=source(backend,tid,slot)
   return images.bounded(folder,item['origin']) if raw and item.get('revision')==revision(raw) else current
  entry=next((e for e in item.get('history',[]) if e['id']==key),None)
  if not entry:raise ValueError('历史封面不存在')
  return images.bounded(folder,entry['file'])

def require_idle(folder):
 if any(read(folder/f'cover-reference-{slot}.json',{}).get('status') in PENDING for slot in (1,2)):
  raise ValueError('封面参考图编辑在途或提交状态不明，请先查询原任务')

def action(backend,tid,slot,name,data):
 import task_cover,task_versions
 folder,_,_=context(backend,tid,slot)
 if name not in ('crop','replace','restore','reference'):raise ValueError('未知封面图片操作')
 query=name=='reference' and data.get('action')=='query'
 with backend.task_operation(tid,allow_reference=True):
  if task_versions.completed(folder) and not query:
   identity=data.get('operation_id') or hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
   child=task_versions.fork(backend,tid,'cover-image',operation_key=f'cover-image:{slot}:{name}:{identity}')
   try:result=action(backend,child,slot,name,data)
   except Exception as error:error.task_id=child;error.source_task_id=tid;raise
   return {**result,'task_id':child,'source_task_id':tid}
  if name=='reference':
   with images.LOCK:recover(folder)
   return reference(backend,tid,slot,data)
  with images.LOCK:
   recover(folder)
   task_cover.require_idle(folder)
   info=view(backend,tid,slot)
   if 'expectedRevision' in data and data['expectedRevision']!=info['revision']:raise ValueError('封面已在其他窗口更新，请重新打开')
   _,meta_path,target=context(backend,tid,slot);meta=read(meta_path,{})
   if name=='replace':raw=images.decode_image(data.get('data_url'));meta={'provider':'upload','prompt':'(本地上传)'}
   elif name=='crop':
    if not source(backend,tid,slot)[1]:raise ValueError('没有封面图片，不能裁剪')
    origin_path=media(backend,tid,slot,'original');raw,crop=images.crop_bytes(origin_path.read_bytes(),data)
    meta={**meta,'_cover_crop':crop,'_cover_origin':store(folder,origin_path.read_bytes())}
   else:
    entry=next((e for e in manifest(folder)['items'].get(str(slot),{}).get('history',[]) if e['id']==data.get('id')),None)
    if not entry:raise ValueError('历史封面不存在')
    raw=images.bounded(folder,entry['file']).read_bytes();meta={**entry.get('meta',{}),'_cover_crop':entry.get('crop'),'_cover_origin':entry['origin']}
   writes={f'cover-job-{slot}.json':{}}
   if name in ('replace','restore'):
    editors=read(folder/'cover-editor.json',{});editors[str(slot)]={**editors.get(str(slot),{}),'mode':'local' if meta.get('provider')=='upload' else 'titled'};writes['cover-editor.json']=editors
   commit(backend,tid,slot,raw,meta,extra_writes=writes)
   return view(backend,tid,slot)

def completed_reference(backend,tid,slot,job):
 import task_cover
 folder,_,target=context(backend,tid,slot)
 if target.is_file():return view(backend,tid,slot)
 item=manifest(folder)['items'].get(str(slot),{});relative=item.get('file')
 if not relative:raise ValueError('当前封面版本缓存缺失，请核对原任务，不重新生成')
 cached=images.bounded(folder,relative)
 if not cached.is_file():
  if item.get('revision')!=job.get('appliedRevision') or not job.get('result'):raise ValueError('后续封面缓存缺失，不能用旧编辑结果覆盖')
  raw=images.png_bytes(task_cover.image_bytes(job['result']))
  if revision(raw)!=item['revision']:raise ValueError('封面缓存与当前版本不一致')
  relative=store(folder,raw)
 if revision(images.bounded(folder,relative).read_bytes())!=item['revision']:raise ValueError('当前封面缓存校验失败')
 with images.LOCK:
  write(folder/'cover-image-transaction.json',{'copies':[[relative,target.name]],'writes':{}});recover(folder)
 return view(backend,tid,slot)

def reference(backend,tid,slot,data):
 import task_cover
 folder,_,_=context(backend,tid,slot);path=folder/f'cover-reference-{slot}.json';job=read(path,{})
 name=data.get('action');op=data.get('operation_id')
 if name not in ('generate','query'):raise ValueError('未知参考图编辑操作')
 if name=='generate' and op==job.get('operationId') and job.get('status')=='ok':return completed_reference(backend,tid,slot,job)
 info=view(backend,tid,slot)
 if name=='generate':
  task_cover.require_idle(folder)
  if 'expectedRevision' in data and data['expectedRevision']!=info['revision']:raise ValueError('封面已在其他窗口更新，请重新打开')
  if not isinstance(op,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',op):raise ValueError('缺少有效操作编号')
  prompt=data.get('prompt');refs=data.get('references')
  if not isinstance(prompt,str) or not prompt.strip() or len(prompt)>20000:raise ValueError('修改指令应为1至20000字')
  if not isinstance(refs,list) or not 1<=len(refs)<=3 or any(not isinstance(x,str) for x in refs) or sum(map(len,refs))>42000000:raise ValueError('参考图应为1至3张，总大小不超过30MB')
  normalized=[]
  for uri in refs:
   raw=images.decode_image(uri)
   if len(raw)>10000000:raise ValueError('单张参考图超过10MB')
   normalized.append('data:image/png;base64,'+base64.b64encode(raw).decode())
  selected=task_cover.view(backend,tid,slot)
  cfg=backend.resolve_image_config(backend.load_settings(),selected['provider'] or None)
  if cfg.get('provider') not in ('runninghub','gpt_image','custom_image','openai'):raise ValueError('所选封面引擎不支持参考图编辑，请明确选择支持图片编辑的引擎')
  if cfg.get('provider')=='runninghub':
   spec=backend.RUNNINGHUB_IMAGE_MODELS.get(cfg.get('model') or 'rh-image-g2')
   if not spec:raise ValueError('未知RunningHub绘图模型')
   if spec.get('image_param')=='image' and len(refs)>1:raise ValueError('当前模型只支持1张参考图')
  if not cfg.get('api_key'):raise ValueError('请先配置绘图凭据')
  cfg={**cfg,'auto_fallback_gpt':False}
  job={'status':'submitting','operationId':op,'provider':cfg['provider'],'credential':task_cover.credential(cfg),'prompt':prompt.strip(),'sourcePrompt':info['actualPrompt'],'ratio':selected['ratio'],'revision':info['revision']};write(path,job)
  def remember(task_id,actual_cfg=None):
   job.update(taskId=task_id,status='pending',credential=task_cover.credential(actual_cfg or cfg));write(path,job)
  try:result=backend.image_dispatcher(cfg,prompt.strip(),ratio=job['ratio'],resolution=cfg.get('resolution') or '1k',reference_data_url=normalized,on_task_id=remember)
  except Exception as error:
   details=task_cover.cover_error(error);message=details['title']+'：'+details['body']
   job.update(status='failed' if isinstance(error,backend.ImageSubmissionRejected) else 'pending' if job.get('taskId') else 'unknown',error=message);write(path,job)
   kind=type(error) if isinstance(error,(backend.ImageSubmissionRejected,TimeoutError,InterruptedError)) else RuntimeError
   raise kind(message) from None
 else:
  if job.get('status')=='ok':return completed_reference(backend,tid,slot,job)
  result=job.get('result')
  if not result:
   if not job.get('taskId'):raise ValueError('没有可查询任务编号，请核对供应商记录，不会重新提交')
   cfg=backend.resolve_image_config(backend.load_settings(),job.get('provider'))
   if task_cover.credential(cfg)!=job.get('credential'):raise ValueError('凭据或地址已变化，请恢复原设置查询')
   response=task_cover.query_provider(backend,cfg,job['taskId'])
   if response.get('status')=='FAILED':job['status']='failed';write(path,job);raise ValueError('平台确认参考图编辑失败，可以重新生成')
   if response.get('status')!='SUCCESS':return {**view(backend,tid,slot),'message':'原任务还在生成，请稍后查询'}
   result=next((x for x in response.get('results',[]) if isinstance(x,dict) and (x.get('url') or x.get('b64'))),None)
   if not result:raise ValueError('平台成功但未返回图片，请核对原任务')
 job.update(result={k:result[k] for k in ('url','b64') if isinstance(result,dict) and isinstance(result.get(k),str)},status='download_pending');write(path,job)
 try:raw=images.png_bytes(task_cover.image_bytes(job['result']))
 except ValueError as error:
  job.update(status='failed',error=str(error));write(path,job);raise
 current=view(backend,tid,slot)
 if current['revision']!=job['revision']:raise ValueError('封面已经更新，保留原编辑结果，请核对后处理')
 job.update(status='ok',appliedRevision=revision(raw))
 editors=read(folder/'cover-editor.json',{});editors[str(slot)]={**editors.get(str(slot),{}),'mode':'titled'}
 commit(backend,tid,slot,raw,{'provider':job['provider'],'prompt':'参考图编辑指令：'+job['prompt'],'sourcePrompt':job.get('sourcePrompt','')},extra_writes={path.name:job,f'cover-job-{slot}.json':{},'cover-editor.json':editors})
 return view(backend,tid,slot)
