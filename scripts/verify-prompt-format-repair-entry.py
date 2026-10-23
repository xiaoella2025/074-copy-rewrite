"""Disposable desktop entry, original supplier query mocked; no real generation."""
import hashlib,http.client,json,os,queue,secrets,subprocess,sys,tempfile,threading,time
from pathlib import Path
sys.stdout.reconfigure(encoding='utf8')
repo=Path(__file__).resolve().parents[1]
audit=repo/'.desktop-tools/prompt-format-repair-20261023'
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
import prompt_format_repair
task_queue.TaskQueue.start=lambda self:None
folder=Path(FOLDER)
shots=[{'idx':1,'text':'fixture'}]
(folder/'client_config.json').write_text(json.dumps({'generate':{'extra':'不要添加人名，保留事实和数字。'}}),'utf8')
raw='[{"id":1,"cap":"fixture "quote" text","desc_prompt":"老人站在庭院里看向远方"}]'
server.call_llm=lambda *args,**kwargs:raw
prompts=server.step3_image_prompts({'_prompt_response_dir':folder},shots,'character-story','vintage-film')
for name,value in [('03-shots.json',shots),('04-prompts.json',prompts)]:
 (folder/name).write_text(json.dumps(value),'utf8')
(folder/'covers/1.png').write_bytes(b'preserved')
def forbidden(*args,**kwargs):raise AssertionError('provider transport forbidden')
server.call_llm=forbidden;server.image_dispatcher=forbidden;server.urllib.request.urlopen=forbidden
'''.replace('FOLDER',repr(str(folder)))
  code='import sys,runpy,json;from pathlib import Path;sys.path[:0]='+repr(imports)+';import server,task_queue;server.ROOT=Path('+repr(str(resource))+');exec('+repr(fixture)+');sys.argv='+repr(['desktop_backend.pyc','--data-dir',str(data),'--legacy-data-dir',str(Path(directory)/'absent')])+';runpy.run_path('+repr(str(host/'_internal/desktop_backend.pyc'))+',run_name="__main__")'
  token=secrets.token_hex(24)
  process=subprocess.Popen([str(host/'python.exe'),'-B','-c',code],env={**os.environ,'APP074_SESSION_TOKEN':token,'PYTHONUTF8':'1'},stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf8',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
  errors=[];threading.Thread(target=lambda:errors.extend(process.stderr.readlines()),daemon=True).start()
  try:
   readyq=queue.Queue();threading.Thread(target=lambda:readyq.put(process.stdout.readline()),daemon=True).start()
   line=readyq.get(timeout=30)
   if not line:raise RuntimeError(''.join(errors))
   ready=json.loads(line);assert ready['event']=='ready',errors
   def request(method,path,body=None,auth=True):
    client=http.client.HTTPConnection('127.0.0.1',ready['port'],timeout=10);headers={'Content-Type':'application/json'}
    if auth:headers['Cookie']='app074_session='+token
    client.request(method,path,json.dumps(body) if body else None,headers);response=client.getresponse();raw=response.read();status=response.status;client.close();return status,json.loads(raw)
   prompts=json.loads((folder/'04-prompts.json').read_text('utf8'))
   assert prompts[0]['diagnostic']['fellBackToSkeleton']
   identity=prompts[0]['diagnostic']['repairId']
   body={'repair_id':identity};route='/api/task/fixture/repair-prompts'
   assert request('POST',route,body,False)[0]==403
   assert request('POST',route,body)[1]['repaired']==1
   assert request('POST',route,body)[1]['repaired']==0
   assert (folder/'covers/1.png').read_bytes()==b'preserved'
   assert json.loads((folder/'04-prompts.json').read_text('utf8'))[0]['diagnostic']['formatRepaired']
   result={'success':True,'manifestSha256':sha,'actualDesktopEntry':True,'explicitLocalRepair':True,'idempotent':True,'existingImagesUnchanged':True,'realProviderRequests':0}
   (audit/('installed-entry-results.json' if installed else 'candidate-entry-results.json')).write_text(json.dumps(result),'utf8');print(json.dumps(result),flush=True)
   if '--serve' in sys.argv:
    (folder/'04-prompts.json').write_text(json.dumps(prompts),'utf8')
    (audit/'browser-fixture.json').write_text(json.dumps({'base':f'http://127.0.0.1:{ready["port"]}','bootstrap':f'http://127.0.0.1:{ready["port"]}/desktop/bootstrap?token={token}'}),'utf8')
    stop=audit/'browser-stop';stop.unlink(missing_ok=True);deadline=time.monotonic()+900
    while not stop.exists() and time.monotonic()<deadline:time.sleep(.2)
  finally:
   process.terminate();process.wait(timeout=10);process.stdout.close();process.stderr.close()

if __name__=='__main__':main()
