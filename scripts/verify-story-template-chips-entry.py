"""Real desktop entry with temporary data and fake transports; never production tasks."""
import hashlib
import http.client
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

sys.stdout.reconfigure(encoding='utf8')
repo=Path(__file__).resolve().parents[1]
audit=repo/'.desktop-tools/story-template-chips-20261022'
host=Path.home()/'AppData/Local/074 创作工作台/app074-backend'


def main():
    installed='--installed' in sys.argv
    resource=host/'_internal' if installed else audit/'static'
    manifest=host/'backend-runtime.json' if installed else audit/'payload/backend-runtime.json'
    sha=hashlib.sha256(manifest.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix='074-global-model-fixture-') as temporary:
        root=Path(temporary);data=root/'data';folder=data/'tasks/fixture';folder.mkdir(parents=True)
        def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2),'utf8')
        config={'generate':{'profile_id':'old','title':'隔离封面标题','reference':'隔离正文','track':'character-story'},
                'cover':{'mode':'title','profileId':'old','provider':'runninghub'},'image':{},'tts':{},'pauseMode':'never'}
        write(folder/'client_config.json',config)
        write(folder/'request.json',config['generate'])
        write(folder/'02-meta.json',{'title':'隔离封面标题','subtitle':['保留副题']})
        write(folder/'03-shots.json',[{'idx':i,'text':'保留原分镜'} for i in range(1,12)])
        write(folder/'cover-editor.json',{'1':{'profile_id':'old','title':'手填封面标题','subtitle':['手填副题']}})
        (folder/'02-rewrite.txt').write_text('保留原正文，不重写原文。','utf8')
        for i in range(1,12):
            (folder/f'image-{i}.png').write_bytes(b'preserve existing paid image')
            (folder/f'audio-{i}.mp3').write_bytes(b'preserve existing paid audio')
        protected={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir() if p.name!='cover-editor.json'}
        job={'id':'fixture-job','task_id':'fixture','kind':'image','status':'failed','config':config,
             'approved_stages':[],'stage':'cover','created_at':time.time(),'updated_at':time.time()}
        write(data/'task-queue.json',{'version':1,'jobs':[job],'batches':[]})
        profiles=[{'id':name,'name':label,'provider':'deepseek','protocol':'openai','model':'model-'+name,
                   'baseUrl':'https://'+name+'.invalid','apiKey':'fixture-'+name,'enabled':name=='old'}
                  for name,label in [('old','旧系统模型'),('new','新系统模型')]]
        write(data/'settings.json',{'modelscope':{'api_key':'fixture-image','tokens':['fixture-image']},'image':{'api_key':'fixture-image','model':'fixture'},'runninghub':{'api_key':'fixture-image'},'tts':{'provider':'aura','aura_api_key':'fixture-voice'}})
        custom=json.loads((host/'_internal/assets/prompt_templates.json').read_text('utf8'))[0]
        custom={**custom,'id':'custom-'+('b'*32),'name':'隔离人物模板','baseTrack':'character-story'}
        custom.pop('builtin',None)
        write(data/'template-library.json',{'prompts':[custom],'drafts':[]})
        write(data/'profiles.json',profiles);events=root/'transport.json';write(events,[])
        imports=[str(host/'_internal')] if installed else [str(audit/'payload/_internal'),str(host/'_internal')]
        fixture=r'''
import base64,io,json
from PIL import Image
task_queue.TaskQueue.start=lambda self:None
events=Path(EVENT_PATH)
def fake_transport(request,**options):
    assert request.full_url=='https://new.invalid/v1/chat/completions','unexpected transport'
    payload=json.loads(request.data)
    records=json.loads(events.read_text('utf8'))
    records.append({'model':payload['model'],'url':request.full_url})
    events.write_text(json.dumps(records),'utf8')
    return io.BytesIO(json.dumps({'choices':[{'message':{'content':'隔离画面构图，远山与人物。'}}]}).encode())
server.urllib.request.urlopen=fake_transport
server.resolve_image_config=lambda *a,**k:{'provider':'runninghub','api_key':'fixture-image'}
def fake_image(*args,**kwargs):
    image=io.BytesIO();Image.new('RGB',(32,48),'blue').save(image,'PNG')
    return {'b64':base64.b64encode(image.getvalue()).decode()}
server.image_dispatcher=fake_image
'''.replace('EVENT_PATH',repr(str(events)))
        code="import sys,runpy;sys.path[:0]="+repr(imports)+";import server,task_queue;from pathlib import Path;server.ROOT=Path("+repr(str(resource))+");exec("+repr(fixture)+");sys.argv="+repr(['desktop_backend.pyc','--data-dir',str(data),'--legacy-data-dir',str(root/'absent')])+";runpy.run_path("+repr(str(host/'_internal/desktop_backend.pyc'))+",run_name='__main__')"
        token=secrets.token_hex(24)
        process=subprocess.Popen([str(host/'python.exe'),'-B','-c',code],env={**os.environ,'APP074_SESSION_TOKEN':token,'PYTHONUTF8':'1'},
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf8',errors='replace',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        errors=[];reader=threading.Thread(target=lambda:errors.extend(process.stderr.readlines()),daemon=True);reader.start()
        try:
            readyq=queue.Queue();threading.Thread(target=lambda:readyq.put(process.stdout.readline()),daemon=True).start()
            ready=json.loads(readyq.get(timeout=30));assert ready['event']=='ready',errors
            def request(method,path,body=None,authorized=True):
                client=http.client.HTTPConnection('127.0.0.1',ready['port'],timeout=15)
                headers={'Content-Type':'application/json'}
                if authorized:headers['Cookie']='app074_session='+token
                client.request(method,path,json.dumps(body) if body is not None else None,headers)
                response=client.getresponse();status=response.status;raw=response.read();client.close()
                return status,json.loads(raw)
            assert request('GET','/api/task/fixture',authorized=False)[0]==403
            assert request('GET','/api/profiles')[0]==200
            status,templates=request('GET','/api/templates/prompts')
            assert status==200
            assert any(x['id']==custom['id'] and not x.get('builtin') for x in templates['templates'])
            for name in ['index.html','assets/form_libraries.js']:
                client=http.client.HTTPConnection('127.0.0.1',ready['port'],timeout=10)
                client.request('GET','/'+name,headers={'Cookie':'app074_session='+token})
                response=client.getresponse();content=response.read();client.close()
                assert response.status==200 and content==(resource/name).read_bytes()

            client=http.client.HTTPConnection('127.0.0.1',ready['port'],timeout=10)
            client.request('GET','/assets/task_form_recovery.js',headers={'Cookie':'app074_session='+token})
            response=client.getresponse();asset=response.read();client.close()
            assert response.status==200 and b'createRecovery' in asset
            expected=resource/'assets/task_form_recovery.js'
            assert hashlib.sha256(asset).digest()==hashlib.sha256(expected.read_bytes()).digest()
            result={'success':True,'manifestSha256':sha,'actualDesktopEntry':True,'workerDisabled':True,
                    'authenticatedRecoveryAssetServed':True,'customPromptTemplateListed':True,'updatedIndexAndLayoutServed':True,'unauthorizedAccessRejected':True,
                    'realProviderRequests':0,'productionDataAccess':False}
            write(audit/('installed-entry-results.json' if installed else 'candidate-entry-results.json'),result)
            print(json.dumps(result),flush=True)
            if '--serve' in sys.argv:
                write(audit/'browser-fixture.json',{'base':f'http://127.0.0.1:{ready["port"]}',
                    'bootstrap':f'http://127.0.0.1:{ready["port"]}/desktop/bootstrap?token={token}','manifestSha256':sha})
                stop=audit/'browser-stop';stop.unlink(missing_ok=True);deadline=time.monotonic()+900
                while not stop.exists() and time.monotonic()<deadline:time.sleep(.2)
        finally:
            process.terminate();process.wait(timeout=10);reader.join(2);process.stdout.close();process.stderr.close()


if __name__=='__main__':main()
