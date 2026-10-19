"""Candidate desktop HTTP/UI fixture. Worker disabled; no real task execution."""
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

repo=Path(__file__).resolve().parents[1];audit=repo/'.desktop-tools/image-progress-switch-20261019'
host=Path.home()/'AppData/Local/074 创作工作台/app074-backend'


def main():
    installed='--installed' in sys.argv
    imports=[str(host/'_internal')] if installed else [str(audit/'payload/_internal'),str(host/'_internal')]
    resource=host/'_internal' if installed else audit/'static'
    with tempfile.TemporaryDirectory(prefix='074-image-progress-fixture-') as directory:
        data=Path(directory)/'data';data.mkdir()
        jobs=[]
        for i,title in enumerate(['前面的任务保留进度','第二个任务正常排队','后面的任务需要优先执行']):
            tid='fixture-'+str(i+1);folder=data/'tasks'/tid;folder.mkdir(parents=True)
            config={'generate':{'title':title,'reference':'fixture only'},'tts':{},'image':{}}
            (folder/'client_config.json').write_text(json.dumps(config,ensure_ascii=False),'utf8')
            (folder/'request.json').write_text(json.dumps({'title':title}),'utf8')
            (folder/'02-meta.json').write_text(json.dumps({'title':title}),'utf8')
            (folder/'saved.png').write_bytes(b'fixture-saved-artifact')
            (folder/'03-shots.json').write_text(json.dumps([{'idx':n,'text':'本地分镜显示验收'} for n in (1,2,3)],ensure_ascii=False),'utf8')
            (folder/'progress.json').write_text(json.dumps({'step':'4','status':'running'}),'utf8')
            jobs.append({'id':'fixture-job-'+str(i),'task_id':tid,'kind':'image','config':config,'from_step':None,
                'approved_stages':[],'status':'queued','created_at':time.time(),'updated_at':time.time()})
        (data/'task-queue.json').write_text(json.dumps({'version':1,'jobs':jobs,'batches':[]}),'utf8')
        token=secrets.token_hex(24)
        advance=audit/'fixture-complete-one';advance.unlink(missing_ok=True)
        fixture_code="""
import base64,threading,time,image_generation_progress
def advance_fixture():
    marker=Path(ADVANCE)
    while not marker.exists():time.sleep(.05)
    folder=Path(FOLDER)
    (folder/'covers').mkdir(exist_ok=True)
    (folder/'covers/1.png').write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jPRkAAAAASUVORK5CYII='))
    with image_generation_progress._lock:image_generation_progress._workers[str(folder.resolve())]={2:1}
threading.Thread(target=advance_fixture,daemon=True).start()
""".replace('ADVANCE',repr(str(advance))).replace('FOLDER',repr(str(data/'tasks/fixture-1')))
        code="import sys,runpy;sys.path[:0]="+repr(imports)+";import server,task_queue;from pathlib import Path;server.ROOT=Path("+repr(str(resource))+");task_queue.TaskQueue.start=lambda self:None;import image_generation_progress;image_generation_progress._workers["+repr(str((data/'tasks/fixture-1').resolve()))+"]={1:1,2:1};sys.argv="+repr(['desktop_backend.pyc','--data-dir',str(data),'--legacy-data-dir',str(Path(directory)/'absent')])+";runpy.run_path("+repr(str(host/'_internal/desktop_backend.pyc'))+",run_name='__main__')"
        code=code.replace(';sys.argv=', ';exec('+repr(fixture_code)+');sys.argv=')
        process=subprocess.Popen([str(host/'python.exe'),'-B','-c',code],env={**os.environ,'APP074_SESSION_TOKEN':token,'PYTHONUTF8':'1'},
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf8',errors='replace',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        errors=[];threading.Thread(target=lambda:errors.extend(process.stderr.readlines()),daemon=True).start()
        try:
            lines=queue.Queue();threading.Thread(target=lambda:lines.put(process.stdout.readline()),daemon=True).start()
            ready=json.loads(lines.get(timeout=30));assert ready['event']=='ready',errors
            def request(method,path,body=None,authorized=True,foreign=False):
                c=http.client.HTTPConnection('127.0.0.1',ready['port'],timeout=10);headers={'Content-Type':'application/json'}
                if authorized:headers['Cookie']='app074_session='+token
                if foreign:headers['Origin']='https://foreign.invalid'
                c.request(method,path,json.dumps(body) if body is not None else None,headers)
                r=c.getresponse();raw=r.read();status=r.status;c.close()
                try:return status,json.loads(raw)
                except ValueError:return status,raw.decode('utf8')
            body={'task_id':'fixture-3','action':'first'}
            assert request('POST','/api/task-queue/order',body,authorized=False)[0]==403
            assert request('POST','/api/task-queue/order',body,foreign=True)[0]==403
            status,value=request('POST','/api/task-queue/order',body);assert status==200 and value['position']==1,value
            assert request('POST','/api/task-queue/order',{'task_id':'fixture-3','action':'defer'})[1]['deferred']
            restored=request('POST','/api/task-queue/order',{'task_id':'fixture-3','action':'resume'})[1]
            assert restored['position']==3 and not restored.get('deferred'),restored
            saved=json.loads((data/'task-queue.json').read_text('utf8'));assert [j['task_id'] for j in saved['jobs']]==['fixture-1','fixture-2','fixture-3']
            assert all((data/'tasks'/j['task_id']/'saved.png').read_bytes()==b'fixture-saved-artifact' for j in saved['jobs'])
            assert request('POST','/api/task-queue/order',{'task_id':'fixture-3','action':'defer'})[1]['status']=='paused'
            started=request('POST','/api/task-queue/order',{'task_id':'fixture-3','action':'start'})[1]
            assert started['status']=='queued' and started['position']==1,started
            status,page=request('GET','/tasks.html');assert status==200 and 'queue_controls.js' in page
            manifest=host/'backend-runtime.json' if installed else audit/'payload/backend-runtime.json'
            sha=hashlib.sha256(manifest.read_bytes()).hexdigest()
            assert request('GET','/api/task/fixture-1')[1]['steps']['image_generating']==[1,2]
            result={'success':True,'actualDesktopEntry':True,'workerDisabled':True,'authenticatedRouteAndForeignOriginChecked':True,
                'orderAndDeferPersisted':True,'successfulArtifactsUnchanged':True,'manifestSha256':sha,'providerRequests':0,'productionDataAccess':False}
            name='installed-entry-results.json' if installed else 'candidate-entry-results.json'
            (audit/name).write_text(json.dumps(result,indent=2),'utf8')
            print(json.dumps(result),flush=True)
            if '--serve' in sys.argv:
                # Local fixture token only; never uses a production desktop session.
                (audit/'browser-fixture.json').write_text(json.dumps({'base':f'http://127.0.0.1:{ready["port"]}',
                    'bootstrap':f'http://127.0.0.1:{ready["port"]}/desktop/bootstrap?token={token}',
                    'manifestSha256':sha}), 'utf8')
                stop=audit/'browser-stop';stop.unlink(missing_ok=True)
                deadline=time.monotonic()+900
                while not stop.exists() and time.monotonic()<deadline:time.sleep(1)
        finally:
            process.terminate();process.wait(timeout=10);process.stdout.close();process.stderr.close()


if __name__=='__main__':main()
