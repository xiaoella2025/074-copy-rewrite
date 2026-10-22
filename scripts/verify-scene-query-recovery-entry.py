"""Disposable desktop entry, original supplier query mocked; no real generation."""
import hashlib,http.client,json,os,queue,secrets,subprocess,sys,tempfile,threading,time
from pathlib import Path
sys.stdout.reconfigure(encoding='utf8')
repo=Path(__file__).resolve().parents[1]
audit=repo/'.desktop-tools/scene-query-recovery-20261022'
host=Path.home()/'AppData/Local/074 创作工作台/app074-backend'

def main():
 installed='--installed' in sys.argv
 resource=host/'_internal' if installed else audit/'static'
 manifest=host/'backend-runtime.json' if installed else audit/'payload/backend-runtime.json'
 sha=hashlib.sha256(manifest.read_bytes()).hexdigest()
 with tempfile.TemporaryDirectory(prefix='074-query-only-fixture-') as directory:
  data=Path(directory)/'data';folder=data/'tasks/fixture';(folder/'covers').mkdir(parents=True)
  imports=[str(host/'_internal')] if installed else [str(audit/'payload/_internal'),str(host/'_internal')]
  fixture=r'''
import io,base64,task_cover
from PIL import Image
task_queue.TaskQueue.start=lambda self:None
buffer=io.BytesIO();Image.new('RGB',(64,96),'blue').save(buffer,'PNG');png=buffer.getvalue()
folder=Path(FOLDER)
def write(name,value):
 path=folder/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value),'utf8')
cfg={'generate':{},'tts':{},'image':{'provider':'runninghub'}}
write('client_config.json',cfg);write('02-meta.json',{'title':'fixture recovery'})
write('03-shots.json',[{'idx':i,'text':'fixture'} for i in range(1,11)])
write('04-prompts.json',[{'idx':i,'desc_prompt':'fixture visual'} for i in range(1,11)])
settings={'runninghub':{'api_key':'fake-only'}}
(folder.parent.parent/'settings.json').write_text(json.dumps(settings),'utf8')
write('image-jobs/9.json',{'status':'pending','provider':'runninghub','taskId':'existing-fixture-id','credential':task_cover.credential(server.resolve_image_config(settings,'runninghub'))})
for i in range(1,11):
 if i!=9:(folder/'covers'/f'{i}.png').write_bytes(png)
calls=[]
def query(backend,cfg,tid):
 assert tid=='existing-fixture-id';calls.append(tid)
 return {'status':'SUCCESS','results':[{'url':'https://fixture.invalid/original.png'}]}
task_cover.query_provider=query
task_cover.image_bytes=lambda result:png
def forbidden(*args,**kwargs):raise AssertionError('real provider calls forbidden')
server.image_dispatcher=forbidden;server.urllib.request.urlopen=forbidden
'''.replace('FOLDER',repr(str(folder)))
  code='import sys,runpy,json;from pathlib import Path;sys.path[:0]='+repr(imports)+';import server,task_queue;server.ROOT=Path('+repr(str(resource))+');exec('+repr(fixture)+');sys.argv='+repr(['desktop_backend.pyc','--data-dir',str(data),'--legacy-data-dir',str(Path(directory)/'absent')])+';runpy.run_path('+repr(str(host/'_internal/desktop_backend.pyc'))+',run_name="__main__")'
  token=secrets.token_hex(24)
  process=subprocess.Popen([str(host/'python.exe'),'-B','-c',code],env={**os.environ,'APP074_SESSION_TOKEN':token,'PYTHONUTF8':'1'},stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf8',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
  errors=[];threading.Thread(target=lambda:errors.extend(process.stderr.readlines()),daemon=True).start()
  try:
   readyq=queue.Queue();threading.Thread(target=lambda:readyq.put(process.stdout.readline()),daemon=True).start()
   ready=json.loads(readyq.get(timeout=30));assert ready['event']=='ready',errors
   def request(method,path,body=None,auth=True):
    client=http.client.HTTPConnection('127.0.0.1',ready['port'],timeout=10);headers={'Content-Type':'application/json'}
    if auth:headers['Cookie']='app074_session='+token
    client.request(method,path,json.dumps(body) if body else None,headers);response=client.getresponse();raw=response.read();status=response.status;client.close();return status,json.loads(raw)
   body={'index':9,'operation_id':'fixture-query','query_only':True};route='/api/task/fixture/retry-image'
   assert request('POST',route,body,False)[0]==403
   before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (folder/'covers').glob('*.png')}
   response=request('POST',route,body);assert response[0]==200 and response[1]['recovered'],response
   assert request('POST',route,body)[1]['cached']
   assert all(hashlib.sha256((folder/'covers'/name).read_bytes()).hexdigest()==digest for name,digest in before.items())
   assert len(request('GET','/api/task/fixture')[1]['steps']['images'])==10
   result={'success':True,'manifestSha256':sha,'actualDesktopEntry':True,'queryOriginalAndDownload':True,'duplicateUsesLocalImage':True,'existingImagesUnchanged':9,'realGenerationRequests':0}
   (audit/('installed-entry-results.json' if installed else 'candidate-entry-results.json')).write_text(json.dumps(result),'utf8');print(json.dumps(result),flush=True)
   if '--serve' in sys.argv:
    # Reset only this explicitly disposable fixture image to exercise UI lookup.
    (folder/'covers/9.png').unlink()
    job=json.loads((folder/'image-jobs/9.json').read_text('utf8'));job.update(status='download_pending')
    (folder/'image-jobs/9.json').write_text(json.dumps(job),'utf8')
    (audit/'browser-fixture.json').write_text(json.dumps({'base':f'http://127.0.0.1:{ready["port"]}','bootstrap':f'http://127.0.0.1:{ready["port"]}/desktop/bootstrap?token={token}'}),'utf8')
    stop=audit/'browser-stop';stop.unlink(missing_ok=True);deadline=time.monotonic()+900
    while not stop.exists() and time.monotonic()<deadline:time.sleep(.2)
  finally:
   process.terminate();process.wait(timeout=10);process.stdout.close();process.stderr.close()

if __name__=='__main__':main()
