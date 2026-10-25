"""Actual desktop entry with temporary tasks and fake image/LLM providers only."""
import base64,hashlib,http.client,io,json,os,queue,secrets,subprocess,sys,tempfile,threading,time
from pathlib import Path
from PIL import Image

sys.stdout.reconfigure(encoding='utf8')
repo=Path(__file__).resolve().parents[1]
audit=repo/'.desktop-tools/cover-multiline-20261025'
host=Path.home()/'AppData/Local/074 创作工作台/app074-backend'

def main():
 installed='--installed' in sys.argv
 resource=host/'_internal' if installed else audit/'static'
 imports=[str(host/'_internal')] if installed else [str(audit/'payload/_internal'),str(host/'_internal')]
 sha=hashlib.sha256((host/'backend-runtime.json' if installed else audit/'payload/backend-runtime.json').read_bytes()).hexdigest()
 with tempfile.TemporaryDirectory(prefix='074-cover-multiline-') as tmp:
  root=Path(tmp);data=root/'data';data.mkdir()
  def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False),'utf8')
  write(data/'settings.json',{'image':{'provider':'modelscope'},'modelscope':{'tokens':['fixture-only'],'model':'fixture','auto_fallback_gpt':False}})
  write(data/'profiles.json',[]);write(data/'task-queue.json',{'version':1,'jobs':[],'batches':[]})
  folder=data/'tasks/multiline';folder.mkdir(parents=True)
  write(folder/'02-meta.json',{'title':'旧封面文字','subtitle':[],'cover_image_prompts':['厨房静物']})
  write(folder/'client_config.json',{'cover':{'mode':'title','provider':'modelscope'}})
  write(folder/'request.json',{'title':'独立任务名'})
  (folder/'02-rewrite.txt').write_text('已完成的文案保持不动。','utf8')
  (folder/'scene.png').write_bytes(b'existing scene');(folder/'voice.mp3').write_bytes(b'existing voice')
  protected={str(p.relative_to(data)):p.read_bytes() for p in [data/'settings.json',data/'profiles.json',folder/'02-rewrite.txt',folder/'scene.png',folder/'voice.mp3']}
  events=root/'events.json';write(events,[])
  buf=io.BytesIO();Image.new('RGB',(32,48),'#304050').save(buf,'PNG')
  fixture="""
import base64,json
task_queue.TaskQueue.start=lambda self:None
def fake_generate(cfg,prompt,*args,**kwargs):
 path=Path(EVENTS);items=json.loads(path.read_text('utf8'));items.append({'prompt':prompt});path.write_text(json.dumps(items,ensure_ascii=False),'utf8')
 return {'b64':PNG,'provider':'modelscope'}
server.image_dispatcher=fake_generate
server.call_llm=lambda *args,**kwargs:'{"title":"AI题字","short_title":"发布短题"}'
def forbidden(*args,**kwargs):raise AssertionError('real provider network forbidden')
server.urllib.request.urlopen=forbidden
""".replace('EVENTS',repr(str(events))).replace('PNG',repr(base64.b64encode(buf.getvalue()).decode()))
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
   result={'success':True,'manifestSha256':sha,'actualDesktopEntry':True,'multilineTitleRoundTrip':True,'threeSubtitleLinesSaved':True,'initialWorkflowCoverAccepted':True,'submittedPromptPreservesLines':True,'duplicateContinueReusesImage':True,'existingOutputsUnchanged':True,'saveDoesNotGenerate':True,'authenticatedRoutes':True,'mockSubmissions':1,'realProviderRequests':0}
   write(audit/('installed-entry-results.json' if installed else 'candidate-entry-results.json'),result);print(json.dumps(result),flush=True)
   if '--serve' in sys.argv:
    write(audit/'browser-fixture.json',{'base':f'http://127.0.0.1:{ready["port"]}','bootstrap':f'http://127.0.0.1:{ready["port"]}/desktop/bootstrap?token={token}','manifestSha256':sha})
    stop=audit/'browser-stop';stop.unlink(missing_ok=True);deadline=time.monotonic()+900
    while not stop.exists() and time.monotonic()<deadline:time.sleep(.2)
  finally:
   process.terminate();process.wait(timeout=10)

if __name__=='__main__':main()
