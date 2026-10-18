"""Real installed UI/HTTP, disposable scenes and a localhost fake image provider."""
import base64,hashlib,http.client,io,json,os,queue,secrets,subprocess,sys,tempfile,threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from PIL import Image

repo=Path(__file__).resolve().parent.parent
host=Path.home()/'AppData/Local/074 创作工作台/app074-backend'
audit=repo/'.desktop-tools/image-completion-repair-20261018'

def main():
 with tempfile.TemporaryDirectory(prefix='074-image-recovery-fixture-') as directory:
  root=Path(directory);data=root/'data';folder=data/'tasks/fixture';(folder/'covers').mkdir(parents=True)
  out=io.BytesIO();Image.new('RGB',(120,180),'#587268').save(out,'PNG');png=out.getvalue();calls=[]
  class Provider(BaseHTTPRequestHandler):
   def log_message(self,*args):pass
   def do_POST(self):
    body=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))));calls.append(body)
    assert self.path=='/v1/images/generations'
    self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(json.dumps({'data':[{'b64_json':base64.b64encode(png).decode()}]}).encode())
  mock=ThreadingHTTPServer(('127.0.0.1',0),Provider);threading.Thread(target=mock.serve_forever,daemon=True).start()
  def write(path,value):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,ensure_ascii=False),'utf8')
  cfg={'generate':{},'tts':{},'image':{'provider':'custom_image','ratio':'9:16','resolution':'1k'},'cover':{'mode':'off'}}
  write(data/'settings.json',{'image':{'provider':'custom_image'},'custom_image':{'base_url':f'http://127.0.0.1:{mock.server_port}','api_key':'fixture-local-only','model':'fixture'}})
  write(folder/'client_config.json',cfg);write(folder/'02-meta.json',{'title':'图片恢复验证（测试任务）'})
  (folder/'02-rewrite.txt').write_text('独立测试场景，不是正式业务数据。','utf8')
  write(folder/'03-shots.json',[{'idx':i,'text':f'测试场景 {i}'} for i in range(1,12)])
  write(folder/'04-prompts.json',[{'idx':i,'desc_prompt':f'fixture visual {i}'} for i in range(1,12)])
  for i in range(1,12):
   if i!=6:(folder/'covers'/f'{i}.png').write_bytes(png)
  write(folder/'image-jobs/6.json',{'status':'failed','provider':'custom_image','prompt':'fixture visual 6','ratio':'9:16','resolution':'1k'})
  write(data/'task-queue.json',{'version':1,'batches':[],'jobs':[{'id':'fixture-job','task_id':'fixture','kind':'image','config':cfg,'approved_stages':[],'status':'failed','stage':'images','stage_status':'failed','error':'images未完成：上游确认出图失败','failure_hold':True}]})
  token=secrets.token_hex(24)
  process=subprocess.Popen([str(host/'python.exe'),'-B',str(host/'_internal/desktop_backend.pyc'),'--data-dir',str(data),'--legacy-data-dir',str(root/'absent')],env={**os.environ,'APP074_SESSION_TOKEN':token},stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
  try:
   lines=queue.Queue();threading.Thread(target=lambda:lines.put(process.stdout.readline()),daemon=True).start();ready=json.loads(lines.get(timeout=30));assert ready['event']=='ready'
   def request(method,path,value=None,auth=True,origin=None):
    c=http.client.HTTPConnection('127.0.0.1',ready['port'],timeout=10);headers={'Content-Type':'application/json'}
    if auth:headers['Cookie']='app074_session='+token
    if origin:headers['Origin']=origin
    c.request(method,path,json.dumps(value) if value is not None else None,headers);response=c.getresponse();result=response.status,response.read(),response.getheader('Content-Type','application/octet-stream');c.close();return result
   route='/api/task/fixture/retry-image';payload={'index':6,'operation_id':'installed-fixture-operation'}
   assert request('POST',route,payload,auth=False)[0]==403
   assert request('POST',route,payload,origin='https://foreign.invalid')[0]==403
   def hashes():return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (folder/'covers').glob('*') if p.stem!='6'}
   before=hashes()
   def verify():
    assert len(calls)==1 and calls[0]['prompt']=='fixture visual 6'
    assert len(json.loads(request('GET','/api/task/fixture')[1])['steps']['images'])==11
    assert request('POST',route,payload)[0]==200;assert len(calls)==1
    assert before==hashes()
    value={'installedEntry':True,'sessionAndOrigin':True,'onlyMissingSceneGenerated':True,'duplicateReusesResult':True,'successfulImagesUnchanged':10,'localFakeProviderRequests':1,'realGenerationRequests':0,'productionDataAccess':False}
    (audit/'installed-entry-verified.json').write_text(json.dumps(value,indent=2),'utf8');print(json.dumps(value),flush=True)
   if '--serve' not in sys.argv:
    assert request('POST',route,payload)[0]==200;verify();return
   class Proxy(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def send(self,status,body,kind):self.send_response(status);self.send_header('Content-Type',kind);self.end_headers();self.wfile.write(body)
    def do_GET(self):
     if self.path=='/__verify':
      verify();return self.send(200,b'fixture verified','text/plain')
     path='/result.html?task=fixture' if self.path=='/' else self.path
     self.send(*request('GET',path))
    def do_POST(self):
     if self.path!=route:return self.send(403,b'fixture only','text/plain')
     body=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))))
     if body.get('index')!=6:return self.send(403,b'only fixture scene 6','text/plain')
     self.send(*request('POST',route,body))
   proxy=ThreadingHTTPServer(('127.0.0.1',0),Proxy)
   print(json.dumps({'fixtureUrl':f'http://127.0.0.1:{proxy.server_port}/'}),flush=True)
   try:proxy.serve_forever()
   finally:proxy.server_close()
  finally:
   process.terminate();process.wait(timeout=10);process.stdout.close();process.stderr.close();mock.shutdown();mock.server_close()

if __name__=='__main__':main()
