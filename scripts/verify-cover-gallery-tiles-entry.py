"""Actual desktop entry with temporary tasks and fake image/LLM providers only."""
import base64,hashlib,http.client,io,json,os,queue,secrets,subprocess,sys,tempfile,threading,time
from pathlib import Path
from PIL import Image

sys.stdout.reconfigure(encoding='utf8')
repo=Path(__file__).resolve().parents[1]
audit=repo/'.desktop-tools/cover-gallery-tiles-20261025'
host=Path.home()/'AppData/Local/074 创作工作台/app074-backend'

def main():
 installed='--installed' in sys.argv
 resource=host/'_internal' if installed else audit/'static'
 imports=[str(host/'_internal')] if installed else [str(audit/'payload/_internal'),str(host/'_internal')]
 sha=hashlib.sha256((host/'backend-runtime.json' if installed else audit/'payload/backend-runtime.json').read_bytes()).hexdigest()
 with tempfile.TemporaryDirectory(prefix='074-cover-history-') as tmp:
  root=Path(tmp);data=root/'data';data.mkdir()
  video_fixture=root/'fixture.mp4'
  subprocess.run([str(host/'_internal/ffmpeg.exe'),'-v','error','-f','lavfi','-i','color=c=0x304050:s=64x96:d=6','-c:v','libx264','-pix_fmt','yuv420p','-an','-y',str(video_fixture)],check=True,capture_output=True,timeout=30)
  def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False),'utf8')
  write(data/'settings.json',{'jianying':{'draft_path':str(root/'drafts')},'image':{'provider':'modelscope'},'modelscope':{'tokens':['fixture-only'],'model':'fixture','auto_fallback_gpt':False}})
  write(data/'profiles.json',[]);write(data/'task-queue.json',{'version':1,'jobs':[],'batches':[]})
  folder=data/'tasks/multiline';folder.mkdir(parents=True)
  write(folder/'02-meta.json',{'title':'旧封面文字','subtitle':[],'cover_image_prompts':['厨房静物']})
  write(folder/'client_config.json',{'cover':{'mode':'title','provider':'modelscope'}})
  write(folder/'request.json',{'title':'独立任务名'})
  (folder/'02-rewrite.txt').write_text('已完成的文案保持不动。','utf8')
  (folder/'scene.png').write_bytes(b'existing scene');(folder/'voice.mp3').write_bytes(b'existing voice')
  protected={str(p.relative_to(data)):p.read_bytes() for p in [data/'settings.json',data/'profiles.json',folder/'02-rewrite.txt',folder/'scene.png',folder/'voice.mp3']}
  history=data/'tasks/history';history.mkdir()
  write(history/'02-meta.json',{'title':'正确封面文字','subtitle':['副标题也要正确']})
  write(history/'client_config.json',{'cover':{'mode':'title','provider':'modelscope'}})
  write(history/'request.json',{'title':'提示词查看验收'})
  write(history/'cover-prompt-1.json',{'key':'expired','prompt':'上次保存的完整提示词：书房静物，主标题“旧文字”，副标题“旧副题”，居中横排。'})
  (history/'02-rewrite.txt').write_text('封面提示词查看验收正文','utf8')
  events=root/'events.json';write(events,[])
  buf=io.BytesIO();Image.new('RGB',(32,48),'#304050').save(buf,'PNG')
  complete=data/'tasks/completed';complete.mkdir()
  write(complete/'02-meta.json',{'title':'历史原成品','subtitle':['原成品副标题'],'cover_image_prompts':['旧书房']})
  write(complete/'client_config.json',{'generate':{},'image':{},'tts':{},'cover':{'mode':'title','provider':'modelscope'}})
  write(complete/'request.json',{'title':'历史原成品'})
  write(complete/'06-draft-meta.json',{'ok':True,'draft_dir':str(root/'original-draft')})
  (complete/'02-rewrite.txt').write_text('原成品文案不改变。','utf8')
  (complete/'cover-poster-1.png').write_bytes(buf.getvalue())
  write(complete/'cover-meta.json',{'path':str(complete/'cover-poster-1.png'),'url':'/api/task_cover/completed/1.png','provider':'modelscope','prompt':'原图提示词'})
  write(complete/'03-shots.json',[{'idx':1,'text':'原成品字幕'}])
  write(complete/'04-prompts.json',[{'idx':1,'text':'原成品字幕','desc_prompt':'旧书房'}])
  write(complete/'05-tts-segments.json',[{'index':1,'text':'原成品字幕','duration':1}])
  write(complete/'05-captions.json',{'max_chars':12,'items':[{'id':'1','idx':1,'lines':['原成品字幕'],'cues':[]}]})
  (complete/'covers').mkdir();(complete/'covers/1.png').write_bytes(buf.getvalue())
  original_bytes={str(p.relative_to(complete)):p.read_bytes() for p in complete.rglob('*') if p.is_file()}
  write(data/'task-queue.json',{'version':1,'jobs':[{'id':'original-terminal','task_id':'completed','kind':'image','status':'completed','config':{},'created_at':1,'updated_at':1}],'batches':[]})
  fixture="""
import base64,json
task_queue.TaskQueue.start=lambda self:None
def fake_generate(cfg,prompt,*args,**kwargs):
 path=Path(EVENTS);items=json.loads(path.read_text('utf8'));items.append({'prompt':prompt});path.write_text(json.dumps(items,ensure_ascii=False),'utf8')
 return {'b64':PNG,'provider':'modelscope'}
import task_cover,time
def fake_export(folder,*args):
 value={'ok':True,'draft_dir':str(folder.parent.parent/'drafts'/folder.name),'exportNonce':time.time_ns()};task_cover.write(folder/'06-draft-meta.json',value);return value
def fake_captions(folder,*args):task_cover.write(folder/'05-captions.json',{'items':[]});return {'ok':True}
server.export_jianying_draft=fake_export
server.save_captions=fake_captions
server.image_dispatcher=fake_generate
server.call_llm=lambda *args,**kwargs:'{"title":"AI题字","short_title":"发布短题"}'
def forbidden(*args,**kwargs):raise AssertionError('real provider network forbidden')
server.urllib.request.urlopen=forbidden
original_get=server.Handler.do_GET
def debug_get(self):
 try:return original_get(self)
 except BaseException:
  Path(EVENTS).with_suffix('.error').write_text(__import__('traceback').format_exc(),'utf8');raise
server.Handler.do_GET=debug_get
server.make_intro_video=lambda image,audio,output,*args,**kwargs: Path(output).write_bytes(base64.b64decode(VALID_VIDEO_FIXTURE))
""".replace('EVENTS',repr(str(events))).replace('PNG',repr(base64.b64encode(buf.getvalue()).decode())).replace('VALID_VIDEO_FIXTURE',repr(base64.b64encode(video_fixture.read_bytes()).decode()))
  code="import sys,runpy;sys.path[:0]="+repr(imports)+";import server,task_queue;from pathlib import Path;server.ROOT=Path("+repr(str(resource))+");exec("+repr(fixture)+");sys.argv="+repr(['desktop_backend.pyc','--data-dir',str(data),'--legacy-data-dir',str(root/'absent')])+";runpy.run_path("+repr(str(host/'_internal/desktop_backend.pyc'))+",run_name='__main__')"
  token=secrets.token_hex(24)
  process=subprocess.Popen([str(host/'python.exe'),'-B','-c',code],env={**os.environ,'APP074_SESSION_TOKEN':token,'PYTHONUTF8':'1'},stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf8',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
  errors=[];threading.Thread(target=lambda:errors.extend(process.stderr.readlines()),daemon=True).start()
  try:
   readyq=queue.Queue();threading.Thread(target=lambda:readyq.put(process.stdout.readline()),daemon=True).start()
   ready=json.loads(readyq.get(timeout=30));assert ready['event']=='ready',errors
   def request(method,path,body=None,authorized=True):
    c=http.client.HTTPConnection('127.0.0.1',ready['port'],timeout=15);headers={'Content-Type':'application/json'}
    if authorized:headers['Cookie']='app074_session='+token
    c.request(method,path,json.dumps(body) if body is not None else None,headers);r=c.getresponse();status=r.status;raw=r.read();c.close()
    try:return status,json.loads(raw)
    except ValueError:return status,raw
   history_info=request('GET','/api/task-cover/history')[1]
   assert history_info['prompt']=='' and '上次保存' in history_info['lastPrompt']
   status,changed=request('POST','/api/task-cover/history/save',{'title':'新封面文字'})
   assert status==200 and changed['prompt']=='' and changed['lastPrompt']==history_info['lastPrompt']
   assert json.loads(events.read_text('utf8'))==[]
   base='/api/task-cover/multiline'
   assert request('POST',base+'/save',{},False)[0]==403
   title='为什么放着\n反而容易坏';subs=['生活里的老道理','越不用越容易坏','看完就明白']
   status,value=request('POST',base+'/save',{'title':title,'subtitle':subs});assert status==200,(status,value)
   assert value['title']==title and value['subtitle']==subs
   assert '所有字必须在同一水平行' not in value['prompt'] and '按用户换行' in value['prompt']
   assert json.loads(events.read_text('utf8'))==[]
   # Exercise the original workflow cover endpoint, the failing screenshot path.
   body={'task_id':'multiline','title':title,'subtitle':'\n'.join(subs),'cover_mode':'title','cover_template':'movie','ratio':'9:16'}
   status,value=request('POST','/api/cover',body);assert status==200,(status,value)
   assert request('POST','/api/cover',body)[0]==200
   submits=json.loads(events.read_text('utf8'));assert len(submits)==1
   assert title in submits[0]['prompt'] and all(s in submits[0]['prompt'] for s in subs)
   assert (folder/'cover-poster-1.png').is_file()
   after=request('GET',base)[1];assert after['title']==title and after['subtitle']==subs
   # Existing image and voice files remain byte-identical.
   assert all((data/p).read_bytes()==raw for p,raw in protected.items())
   before_submits=len(json.loads(events.read_text('utf8')))
   status,cover_child=request('POST','/api/task-cover/completed/save',{'title':'修改后的新版本'})
   assert status==200 and cover_child['task_id']!='completed' and cover_child['source_task_id']=='completed'
   assert not (data/'tasks'/cover_child['task_id']/'06-draft-meta.json').exists()
   status,config_child=request('POST','/api/task/completed/config',{'generate':{},'image':{},'tts':{}})
   assert status==200 and config_child['task_id'] not in ('completed',cover_child['task_id'])
   status,rerun_child=request('POST','/api/task/completed/enqueue',{'from_step':'6'})
   assert status==200 and rerun_child['task_id']!='completed'
   status,retry_child=request('POST','/api/task/completed/retry-image',{'index':1,'operation_id':'same-cached-image'})
   assert status==200 and retry_child.get('task_id')!='completed',(status,retry_child)
   status,cap_child=request('POST','/api/task/completed/captions',{'items':[],'operation_id':'caption-once'})
   assert status==200 and cap_child['task_id']!='completed'
   status,pack_child=request('POST','/api/task/completed/repack',{'operation_id':'pack-once'})
   assert status==200 and pack_child['task_id']!='completed'
   again=request('POST','/api/task/completed/repack',{'operation_id':'pack-once'})[1]
   assert again['task_id']==pack_child['task_id'] and again['exportNonce']==pack_child['exportNonce']
   repeated=request('POST','/api/task/completed/enqueue',{'from_step':'6'})[1]
   assert repeated['task_id']==rerun_child['task_id']
   assert all((complete/path).read_bytes()==raw for path,raw in original_bytes.items())
   assert len(json.loads(events.read_text('utf8')))==before_submits
   original_detail=request('GET','/api/task/completed')[1]
   assert 6 in original_detail['info']['completed_steps'] and original_detail['info']['queue']['status']=='completed'
   # Cover gallery's real authenticated endpoints use separate cover slots.
   status,cover_image=request('GET','/api/cover-image/completed/1')
   assert status==200 and cover_image['actualPrompt']=='原图提示词' and cover_image['current']
   assert request('GET','/api/cover-image/completed/1',authorized=False)[0]==403
   assert request('POST','/api/cover-image/completed/1/replace',{},False)[0]==403
   assert request('GET','/api/task-cover/completed?slot=2')[1]['available'] is False
   local_uri='data:image/png;base64,'+base64.b64encode(buf.getvalue()).decode()
   status,local_child=request('POST','/api/cover-image/completed/1/replace',{'data_url':local_uri,'expectedRevision':cover_image['revision']})
   assert status==200 and local_child['task_id']!='completed',(status,local_child)
   child_id=local_child['task_id'];image_path='/api/cover-image/'+child_id+'/1'
   assert local_child['history'][0]['prompt']=='原图提示词'
   history_id=local_child['history'][0]['id']
   assert request('GET',image_path+'/'+history_id+'.png')[0]==200
   status,restored=request('POST',image_path+'/restore',{'id':history_id,'expectedRevision':local_child['revision']})
   assert status==200 and restored['actualPrompt']=='原图提示词',(status,restored)
   status,cropped=request('POST',image_path+'/crop',{'rect':{'x':0,'y':0,'w':.5,'h':1},'aspect':None,'expectedRevision':restored['revision']})
   assert status==200 and cropped['width']==16 and cropped['height']==48,(status,cropped)
   status,rejected=request('POST',image_path+'/reference',{'action':'generate','operation_id':'unsupported-reference','prompt':'改正确文字','references':[local_uri]})
   assert status==409 and '不支持' in rejected['error'],(status,rejected)
   assert all((complete/path).read_bytes()==raw for path,raw in original_bytes.items())
   assert len(json.loads(events.read_text('utf8')))==before_submits
   status,default_motion=request('POST','/api/cover-motion/completed/1/prompt',{})
   assert status==200 and '文字' in default_motion['prompt']
   status,animated=request('POST','/api/cover-motion/completed/1/animation',{'operation_id':'local-cover-once'})
   assert status==200 and animated['task_id']!='completed' and animated['result']['engine']=='local-panzoom',(status,animated)
   assert request('GET',animated['result']['video_url'])[0]==200
   assert request('GET',animated['result']['video_url'],authorized=False)[0]==403
   repeated_motion=request('POST','/api/cover-motion/completed/1/animation',{'operation_id':'local-cover-once'})[1]
   assert repeated_motion['task_id']==animated['task_id']
   assert all((complete/path).read_bytes()==raw for path,raw in original_bytes.items())
   assert len(json.loads(events.read_text('utf8')))==before_submits
   result={'success':True,'manifestSha256':sha,'actualDesktopEntry':True,'interceptedImageRetryForks':True,'directCaptionsAndRepackFork':True,'queueRequestRetryReusesChild':True,'repackRetryDoesNotExportAgain':True,'completedTaskBytesUnchanged':True,'coverEditsFork':True,'configEditsFork':True,'rerunCreatesNewQueueTask':True,'originalRemainsCompleted':True,'historyAvailableAfterParameterEdit':True,'expiredPromptNotUsedAsCurrent':True,'multilineTitleRoundTrip':True,'threeSubtitleLinesSaved':True,'initialWorkflowCoverAccepted':True,'submittedPromptPreservesLines':True,'duplicateContinueReusesImage':True,'existingOutputsUnchanged':True,'saveDoesNotGenerate':True,'authenticatedRoutes':True,'coverGalleryAuthenticated':True,'coverCropRestoreRoundTrip':True,'coverImageHistoryRetainsPrompt':True,'unsupportedReferenceNotSubmitted':True,'secondCoverNotInvented':True,'coverLocalVideoForkAndMedia':True,'coverVideoRetryReusesChild':True,'mockSubmissions':1,'realProviderRequests':0}
   write(audit/('installed-entry-results.json' if installed else 'candidate-entry-results.json'),result);print(json.dumps(result),flush=True)
   if '--serve' in sys.argv:
    write(audit/'browser-fixture.json',{'base':f'http://127.0.0.1:{ready["port"]}','bootstrap':f'http://127.0.0.1:{ready["port"]}/desktop/bootstrap?token={token}','manifestSha256':sha,'coverVideoTask':animated['task_id']})
    stop=audit/'browser-stop';stop.unlink(missing_ok=True);deadline=time.monotonic()+900
    while not stop.exists() and time.monotonic()<deadline:time.sleep(.2)
    assert all((complete/path).read_bytes()==raw for path,raw in original_bytes.items()),'Browser editor changed original completed files'
    assert all((data/path).read_bytes()==raw for path,raw in protected.items()),'Browser editor changed protected original inputs'
    write(audit/'browser-source-results.json',{'success':True,'manifestSha256':sha,'originalCompletedBytesUnchangedAfterUI':True,'originalInputsUnchanged':True,'realProviderRequests':0})
  finally:
   if events.with_suffix('.error').exists():print(events.with_suffix('.error').read_text('utf8'),file=sys.stderr)
   if errors:print(''.join(errors[-35:]),file=sys.stderr)
   process.terminate();process.wait(timeout=10)

if __name__=='__main__':main()
