"""Reuse the scene video engines in a cover-owned, isolated media workspace."""
import hashlib,re,uuid
from pathlib import Path
import cover_images,image_motion,task_cover,task_versions

class Backend:
 def __init__(self,backend,data):self.backend=backend;self.DATA_DIR=data
 def __getattr__(self,name):return getattr(self.backend,name)

def workspace(backend,tid,slot,create=False):
 folder,_,_=cover_images.context(backend,tid,slot);_,raw=cover_images.source(backend,tid,slot)
 if not raw:raise ValueError('请先生成或上传封面图片')
 raw=cover_images.images.png_bytes(raw);key=hashlib.sha256(raw).hexdigest()
 data=folder/'.cover-motion'/str(slot);target=data/'tasks'/key
 if not target.resolve().is_relative_to(folder.resolve()):raise ValueError('封面视频路径无效')
 if create and not target.exists():
  (target/'covers').mkdir(parents=True);(target/'covers/1.png').write_bytes(raw)
  image_motion.write(target/'03-shots.json',[{'idx':1,'text':'封面视频'}])
  image_motion.write(target/'client_config.json',{'generate':{}})
 return Backend(backend,data),key,target

def require_idle(folder):
 for path in (folder/'.cover-motion').glob('*/tasks/*/04-video-meta.json'):
  job=image_motion.read(path,{}).get('items',{}).get('1',{})
  if job.get('status') in ('pending','unknown','submitting','download_pending'):raise ValueError('封面AI视频在途或提交状态不明，请继续查询原视频任务')

def view(backend,tid,slot):
 try:_,_,folder=workspace(backend,tid,slot)
 except ValueError:return {}
 ai=image_motion.read(folder/'04-video-meta.json',{}).get('items',{}).get('1',{})
 result=image_motion.read(folder/'cover-video-selected.json',{})
 name='animation.mp4' if result.get('engine')=='local-panzoom' else 'ai.mp4'
 if not image_motion.valid_video(folder/name):result={}
 cached=folder/'videos/seg_001.mp4';download=folder/'ai.mp4'
 restoring=ai.get('status')=='ok' and (result.get('provider_task_id')!=ai.get('taskId') or not image_motion.valid_video(download) or cached.is_file() and download.is_file() and cached.stat().st_size!=download.stat().st_size)
 return {'restoring':restoring,'job':{k:ai[k] for k in ('status','taskId','operationId','request') if k in ai},
         'result':{**result,'video_url':f'/api/cover-motion/{tid}/{slot}/{name}'} if result else {}}

def media(backend,tid,slot,name):
 if name not in ('animation.mp4','ai.mp4'):raise ValueError('封面视频地址无效')
 _,_,folder=workspace(backend,tid,slot);path=folder/name
 if not path.resolve().is_relative_to(folder.resolve()) or not image_motion.valid_video(path):raise ValueError('封面视频尚未生成')
 return path

def action(backend,tid,slot,name,data):
 folder,_,_=cover_images.context(backend,tid,slot)
 if name=='prompt':return {'prompt':'保持封面人物、物品和构图不变，镜头缓慢轻微推进；所有标题、副标题的字形、位置和笔画保持静止清晰，不增加、删除或替换任何文字。'}
 if name not in ('animation','generate','query'):raise ValueError('未知封面视频操作')
 if name=='generate' and not backend.load_settings().get('runninghub',{}).get('api_key'):raise ValueError('请先配置RunningHub钱包视频接口Key；RH币工作流Key不用于此视频接口')
 folder,_,_=cover_images.context(backend,tid,slot)
 with backend.task_operation(tid,allow_reference=True):
  if task_versions.completed(folder) and name!='query':
   op=data.get('operation_id')
   if not isinstance(op,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',op):raise ValueError('缺少封面视频操作编号')
   child=task_versions.fork(backend,tid,'cover-video',operation_key=f'cover-video:{slot}:{name}:{op}')
   try:return {**action(backend,child,slot,name,data),'task_id':child,'source_task_id':tid}
   except Exception as error:error.task_id=child;error.source_task_id=tid;raise
  if name!='query':task_cover.require_idle(folder)
  adapter,key,target=workspace(backend,tid,slot,name!='query')
  if name=='animation':
   # Same Ken Burns renderer as scene gallery; six seconds, silent output.
   old=image_motion.read(target/'cover-animation.json',{})
   path=target/'animation.mp4'
   ratio=task_cover.view(backend,tid,slot)['ratio']
   if not image_motion.valid_video(path) or old.get('ratio')!=ratio:
    sound=target/'silence.wav'
    pcm=bytes(8000*2*6)
    header=b'RIFF'+(36+len(pcm)).to_bytes(4,'little')+b'WAVEfmt '+(16).to_bytes(4,'little')+(1).to_bytes(2,'little')+(1).to_bytes(2,'little')+(8000).to_bytes(4,'little')+(16000).to_bytes(4,'little')+(2).to_bytes(2,'little')+(16).to_bytes(2,'little')+b'data'+len(pcm).to_bytes(4,'little')
    sound.write_bytes(header+pcm)
    ratio=task_cover.view(backend,tid,slot)['ratio']
    temporary=target/'animation-building.mp4'
    try:
     backend.make_intro_video(target/'covers/1.png',sound,temporary,6,ratio,include_audio=False)
     if not image_motion.valid_video(temporary):raise RuntimeError('未取得有效封面动画视频')
     temporary.replace(path)
    finally:temporary.unlink(missing_ok=True)
   image_motion.write(target/'cover-animation.json',{'ratio':ratio})
   result={'ok':True,'engine':'local-panzoom','duration':6,'ratio':ratio}
  else:
   state=image_motion.read(target/'04-video-meta.json',{}).get('items',{}).get('1',{})
   if name=='query':
    if not state or state.get('status') not in ('pending','ok','download_pending'):raise ValueError('没有可查询的原视频编号，请核对供应商记录，不会重新提交')
    request=state.get('request',{});movement=request.get('prompt');seconds=request.get('duration');ratio=request.get('aspectRatio');operation=state.get('operationId')
   else:
    movement=data.get('prompt');seconds=data.get('duration_sec',6);ratio=task_cover.view(backend,tid,slot)['ratio'];ratio=ratio if ratio in ('2:3','3:2','1:1','16:9','9:16') else '9:16';operation=data.get('operation_id')
   try:result=image_motion.generate(adapter,key,1,movement,seconds,ratio,operation_id=operation,regenerate=data.get('regenerate') is True and name!='query')
   except (ValueError,RuntimeError,OSError) as error:
    if isinstance(error,ValueError):raise
    details=task_cover.cover_error(error);raise RuntimeError('封面AI视频未完成：'+details['title']+'。原视频记录已保留，请查询原任务，不自动重发。') from None
   path=Path(result['video_path']);destination=target/'ai.mp4'
   if path!=destination:
    temporary=target/('ai-copying-'+uuid.uuid4().hex+'.mp4')
    try:
     __import__('shutil').copyfile(path,temporary)
     if not image_motion.valid_video(temporary) or temporary.stat().st_size!=path.stat().st_size:raise OSError('封面视频复制未完成')
     temporary.replace(destination)
    finally:temporary.unlink(missing_ok=True)
   result={k:v for k,v in result.items() if k not in ('video_url','video_path')}
  image_motion.write(target/'cover-video-selected.json',result)
  return view(backend,tid,slot)
