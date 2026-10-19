"""Actual desktop backend, isolated task and disabled execution; never providers."""
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

repo=Path(__file__).resolve().parents[1]
audit=repo/'.desktop-tools/pause-parameter-edit-20261019'
host=Path.home()/'AppData/Local/074 创作工作台/app074-backend'


def main():
    installed='--installed' in sys.argv
    resource=host/'_internal' if installed else audit/'static'
    with tempfile.TemporaryDirectory(prefix='074-pause-parameter-fixture-') as temp:
        data=Path(temp)/'data';folder=data/'tasks/fixture';folder.mkdir(parents=True)
        config={'generate':{'title':'暂停参数验收','reference':'fixture','targets':{'shots':10}},
                'tts':{},'image':{},'cover':{'mode':'off'},'pauseMode':'never'}
        for name,value in [('client_config.json',config),('request.json',{'title':'暂停参数验收'}),
                           ('02-meta.json',{'title':'暂停参数验收'}),('03-shots.json',[{'idx':1,'text':'原有分镜保留'}]),
                           ('progress.json',{'step':'2','status':'running'})]:
            (folder/name).write_text(json.dumps(value,ensure_ascii=False),'utf8')
        (folder/'saved-artifact.png').write_bytes(b'preserved fixture output')
        job={'id':'fixture-job','task_id':'fixture','kind':'image','status':'paused','manual_pause':True,
             'config':config,'approved_stages':[],'from_step':None,'stage':'generate','created_at':time.time(),'updated_at':time.time()}
        (data/'task-queue.json').write_text(json.dumps({'version':1,'jobs':[job],'batches':[]}),'utf8')
        marker=audit/'fixture-pause-finished';marker.unlink(missing_ok=True)
        imports=[str(host/'_internal')] if installed else [str(audit/'payload/_internal'),str(host/'_internal')]
        fixture_code="""
import threading,time
def fixture_start(self):
    if getattr(self,'fixture_started',False):return
    self.fixture_started=True
    self._find('fixture')['status']='pausing'
    self._save()
    def finish_pause():
        while not Path(MARKER).exists():time.sleep(.05)
        with self.lock:
            self._find('fixture')['status']='paused'
            self._save()
    threading.Thread(target=finish_pause,daemon=True).start()
task_queue.TaskQueue.start=fixture_start
""".replace('MARKER',repr(str(marker)))
        code="import sys,runpy;sys.path[:0]="+repr(imports)+";import server,task_queue;from pathlib import Path;server.ROOT=Path("+repr(str(resource))+");exec("+repr(fixture_code)+");sys.argv="+repr(['desktop_backend.pyc','--data-dir',str(data),'--legacy-data-dir',str(Path(temp)/'absent')])+";runpy.run_path("+repr(str(host/'_internal/desktop_backend.pyc'))+",run_name='__main__')"
        token=secrets.token_hex(24)
        process=subprocess.Popen([str(host/'python.exe'),'-B','-c',code],env={**os.environ,'APP074_SESSION_TOKEN':token,'PYTHONUTF8':'1'},
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf8',errors='replace',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        errors=[];reader=threading.Thread(target=lambda:errors.extend(process.stderr.readlines()),daemon=True);reader.start()
        try:
            ready_queue=queue.Queue();threading.Thread(target=lambda:ready_queue.put(process.stdout.readline()),daemon=True).start()
            ready=json.loads(ready_queue.get(timeout=30));assert ready['event']=='ready',errors
            def request(method,path,body=None,authorized=True):
                c=http.client.HTTPConnection('127.0.0.1',ready['port'],timeout=10)
                headers={'Content-Type':'application/json'}
                if authorized:headers['Cookie']='app074_session='+token
                c.request(method,path,json.dumps(body) if body is not None else None,headers)
                r=c.getresponse();raw=r.read();status=r.status;c.close()
                try:return status,json.loads(raw)
                except ValueError:return status,raw.decode('utf8')
            assert request('GET','/api/task/fixture')[1]['info']['queue']['status']=='pausing'
            assert request('POST','/api/task/fixture/config',config,False)[0]==403
            assert request('POST','/api/task/fixture/config',config)[0] in (400,409)
            assert json.loads((folder/'client_config.json').read_text('utf8'))==config
            manifest=host/'backend-runtime.json' if installed else audit/'payload/backend-runtime.json'
            sha=hashlib.sha256(manifest.read_bytes()).hexdigest()
            result={'success':True,'manifestSha256':sha,'actualDesktopEntry':True,'workerDisabled':True,
                    'pausingSaveRejected':True,'providerRequests':0,'productionDataAccess':False}
            (audit/('installed-entry-results.json' if installed else 'candidate-entry-results.json')).write_text(json.dumps(result,indent=2),'utf8')
            print(json.dumps(result),flush=True)
            if '--serve' in sys.argv:
                (audit/'browser-fixture.json').write_text(json.dumps({'base':f'http://127.0.0.1:{ready["port"]}',
                    'bootstrap':f'http://127.0.0.1:{ready["port"]}/desktop/bootstrap?token={token}','manifestSha256':sha}),'utf8')
                stop=audit/'browser-stop';stop.unlink(missing_ok=True)
                deadline=time.monotonic()+900
                while not stop.exists() and time.monotonic()<deadline:time.sleep(.2)
                assert (folder/'saved-artifact.png').read_bytes()==b'preserved fixture output'
                final=json.loads((folder/'client_config.json').read_text('utf8'))
                assert final['generate']['targets']['shots']==12,final
                assert json.loads((data/'task-queue.json').read_text('utf8'))['jobs'][0]['from_step']=='2'
        finally:
            process.terminate();process.wait(timeout=10);reader.join(2);process.stdout.close();process.stderr.close()


if __name__=='__main__':main()
