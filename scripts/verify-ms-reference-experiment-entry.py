"""Actual desktop entry, isolated data, fake ModelScope HTTP; no paid generation."""
import base64
import hashlib
import http.client
import importlib.util
import io
import json
import os
from pathlib import Path
import queue
import secrets
import subprocess
import sys
import tempfile
import threading
import time
from PIL import Image

sys.stdout.reconfigure(encoding='utf8')
repo=Path(__file__).resolve().parents[1]
audit=repo/'.desktop-tools/modelscope-reference-experiment-20261022'
host=Path.home()/'AppData/Local/074 创作工作台/app074-backend'


def main():
    installed='--installed' in sys.argv
    resource=host/'_internal' if installed else audit/'static'
    manifest=host/'backend-runtime.json' if installed else audit/'payload/backend-runtime.json'
    sha=hashlib.sha256(manifest.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix='074-ms-reference-experiment-') as temporary:
        root=Path(temporary);data=root/'data';data.mkdir();normal=data/'tasks/unchanged';normal.mkdir(parents=True)
        (normal/'existing.png').write_bytes(b'preserved original paid output')
        def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2),'utf8')
        settings={'image':{'provider':'modelscope'},'modelscope':{'tokens':['fixture-token'],'model':'ordinary-model','auto_fallback_gpt':False}}
        write(data/'settings.json',settings);write(data/'profiles.json',[])
        write(data/'task-queue.json',{'version':1,'jobs':[],'batches':[]})
        events=root/'events.json';write(events,[])
        buffer=io.BytesIO();Image.new('RGB',(32,48),'blue').save(buffer,'PNG');png=buffer.getvalue()
        fixture_image=audit/'fixture-reference.png';fixture_image.write_bytes(png)
        fixture=r'''
import base64,json
import task_cover
task_queue.TaskQueue.start=lambda self:None
events=Path(EVENTS)
png=base64.b64decode(PNG)
def record(value):
    items=json.loads(events.read_text('utf8'));items.append(value);events.write_text(json.dumps(items),'utf8');return len(items)
def fake_post(url,headers,body,**kwargs):
    payload=json.loads(body)
    assert url=='https://api-inference.modelscope.cn/v1/images/generations'
    assert payload['model']=='Qwen/Qwen-Image-Edit-2511' and len(payload['image_url'])==1
    assert payload['image_url'][0].startswith('data:image/png;base64,')
    number=record({'kind':'submit','model':payload['model']})
    return 200,json.dumps({'task_id':'fixture-task-'+str(number)})
def fake_get(url,headers,**kwargs):
    assert url.startswith('https://api-inference.modelscope.cn/v1/tasks/fixture-task-')
    record({'kind':'query'})
    return 200,json.dumps({'task_status':'SUCCEED','output_images':['https://fixture.invalid/result.png']})
original_bytes=task_cover.image_bytes
task_cover.image_bytes=lambda result: png if result.get('url')=='https://fixture.invalid/result.png' else original_bytes(result)
server._http_post_json=fake_post;server._http_get_json=fake_get
def forbidden(*args,**kwargs):raise AssertionError('unmocked transport is forbidden')
server.urllib.request.urlopen=forbidden
'''.replace('EVENTS',repr(str(events))).replace('PNG',repr(base64.b64encode(png).decode()))
        imports=[str(host/'_internal')] if installed else [str(audit/'payload/_internal'),str(host/'_internal')]
        code="import sys,runpy;sys.path[:0]="+repr(imports)+";import server,task_queue;from pathlib import Path;server.ROOT=Path("+repr(str(resource))+");exec("+repr(fixture)+");sys.argv="+repr(['desktop_backend.pyc','--data-dir',str(data),'--legacy-data-dir',str(root/'absent')])+";runpy.run_path("+repr(str(host/'_internal/desktop_backend.pyc'))+",run_name='__main__')"
        token=secrets.token_hex(24)
        process=subprocess.Popen([str(host/'python.exe'),'-B','-c',code],env={**os.environ,'APP074_SESSION_TOKEN':token,'PYTHONUTF8':'1'},
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf8',errors='replace',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        errors=[];reader=threading.Thread(target=lambda:errors.extend(process.stderr.readlines()),daemon=True);reader.start()
        try:
            readyq=queue.Queue();threading.Thread(target=lambda:readyq.put(process.stdout.readline()),daemon=True).start()
            ready=json.loads(readyq.get(timeout=30));assert ready['event']=='ready',errors
            def request(method,path,body=None,authorized=True):
                client=http.client.HTTPConnection('127.0.0.1',ready['port'],timeout=15);headers={'Content-Type':'application/json'}
                if authorized:headers['Cookie']='app074_session='+token
                client.request(method,path,json.dumps(body) if body is not None else None,headers)
                response=client.getresponse();status=response.status;raw=response.read();client.close()
                try:return status,json.loads(raw)
                except ValueError:return status,raw
            base='/api/ms-reference-experiment';operation='a'*32
            protected={str(path.relative_to(data)):path.read_bytes() for path in [data/'settings.json',data/'profiles.json',data/'task-queue.json',normal/'existing.png']}
            assert request('GET',base,authorized=False)[0]==403
            assert request('POST',base+'/config',{'enabled':True},False)[0]==403
            assert request('GET',base)[1]['enabled'] is False
            body={'operation_id':operation,'prompt':'保持产品外观，只改变背景','reference':'data:image/png;base64,'+base64.b64encode(png).decode()}
            assert request('POST',base+'/generate',body)[0]==400
            assert json.loads(events.read_text('utf8'))==[]
            assert request('POST',base+'/config',{'enabled':True})[0]==200
            status,job=request('POST',base+'/generate',body);assert status==200 and job['taskId']=='fixture-task-1',(status,job)
            assert request('POST',base+'/generate',body)[1]['taskId']==job['taskId']
            assert request('POST',base+'/config',{'enabled':False})[0]==200
            assert request('POST',base+'/generate',{**body,'operation_id':'b'*32})[0]==400
            assert request('POST',base+'/query',{'operation_id':operation})[1]['status']=='ok'
            assert request('POST',base+'/query',{'operation_id':operation})[1]['status']=='ok'
            assert request('GET',base+'/image/'+operation)[1]==png
            assert len(json.loads(events.read_text('utf8')))==2
            assert request('GET','/ms-reference-experiment.html')[0]==200
            assert request('GET','/settings.html')[0]==200
            assert request('GET','/api/settings')[1]['modelscope']['model']=='ordinary-model'
            for path,value in protected.items():assert (data/path).read_bytes()==value,path
            result={'success':True,'manifestSha256':sha,'actualDesktopEntry':True,'defaultOff':True,'explicitOneImageOnly':True,
                    'duplicateSubmitReusesId':True,'disabledQueryRecoversOriginal':True,'authenticatedRoutes':True,
                    'productionProviderConfigUnchanged':True,'normalTaskArtifactsUnchanged':True,'mockSubmissions':1,'mockQueries':1,'realProviderRequests':0}
            write(audit/('installed-entry-results.json' if installed else 'candidate-entry-results.json'),result);print(json.dumps(result),flush=True)
            if '--serve' in sys.argv:
                write(audit/'browser-fixture.json',{'base':f'http://127.0.0.1:{ready["port"]}',
                    'bootstrap':f'http://127.0.0.1:{ready["port"]}/desktop/bootstrap?token={token}','manifestSha256':sha})
                stop=audit/'browser-stop';stop.unlink(missing_ok=True);deadline=time.monotonic()+900
                while not stop.exists() and time.monotonic()<deadline:time.sleep(.2)
                for path,value in protected.items():assert (data/path).read_bytes()==value,path
        finally:
            process.terminate();process.wait(timeout=10);reader.join(2);process.stdout.close();process.stderr.close()


if __name__=='__main__':main()
