"""Real installed entry, disposable data/session, cached local operations only."""
import http.client
import json
import os
from pathlib import Path
import queue
import secrets
import subprocess
import tempfile
import threading
import time


def main():
    repo=Path(__file__).resolve().parent.parent
    host=Path.home()/'AppData/Local/074 创作工作台/app074-backend'
    with tempfile.TemporaryDirectory(prefix='074-batch-entry-') as directory:
        root=Path(directory);data=root/'data';folder=data/'benchmark/batch-jobs';folder.mkdir(parents=True)
        token=secrets.token_hex(24)
        items=[{'accountId':'v2_fixture','feedId':str(i)} for i in range(2)]
        (data/'benchmark.json').write_text(json.dumps({'version':1,'accounts':[],
            'feeds':[{**item,'title':'fixture','transcript':'fixture cached manuscript','createdTask':True} for item in items]}),'utf8')
        (folder/('f'*32+'.json')).write_text(json.dumps({'version':1,'id':'f'*32,'kind':'mark','mark':False,
            'items':items,'status':'running','rows':[{**item,'status':('succeeded' if i==0 else 'running'),'error':'','result':{}} for i,item in enumerate(items)]}),'utf8')
        process=subprocess.Popen([str(host/'python.exe'),'-B',str(host/'_internal/desktop_backend.pyc'),
            '--data-dir',str(data),'--legacy-data-dir',str(root/'nonexistent')],
            env={**os.environ,'APP074_SESSION_TOKEN':token},stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            text=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            lines=queue.Queue();threading.Thread(target=lambda:lines.put(process.stdout.readline()),daemon=True).start()
            ready=json.loads(lines.get(timeout=30));assert ready['event']=='ready'
            def request(method,path,value=None,auth=True,origin=None,raw=False):
                c=http.client.HTTPConnection('127.0.0.1',ready['port'],timeout=5)
                headers={'Content-Type':'application/json'}
                if auth:headers['Cookie']='app074_session='+token
                if origin:headers['Origin']=origin
                c.request(method,path,json.dumps(value) if value is not None else None,headers)
                response=c.getresponse();status=response.status;body=response.read();c.close()
                return status,body if raw else json.loads(body)
            def finished(job_id):
                deadline=time.monotonic()+5
                while time.monotonic()<deadline:
                    status,value=request('GET','/api/benchmark/batch-jobs');assert status==200
                    job=next(x for x in value['jobs'] if x['id']==job_id)
                    if job['status']=='completed':return job
                    time.sleep(.05)
                raise AssertionError('fixture job did not complete')
            assert request('GET','/api/benchmark/batch-jobs',auth=False)[0]==403
            status,value=request('GET','/api/benchmark/batch-jobs');assert status==200
            assert value['jobs'][0]['status']=='interrupted'
            assert request('GET','/api/benchmark')[1]['feeds'][1]['createdTask'] is True
            assert request('POST','/api/benchmark/batch-control',{'id':'f'*32,'action':'resume'},origin='https://foreign.invalid')[0]==403
            assert request('POST','/api/benchmark/batch-control',{'id':'f'*32,'action':'resume'})[0]==200
            job=finished('f'*32);assert job['succeeded']==2
            feeds=request('GET','/api/benchmark')[1]['feeds']
            assert [x['createdTask'] for x in feeds]==[True,False],'successful row was rerun'
            payload={'id':'a'*32,'kind':'download','items':items}
            assert request('POST','/api/benchmark/batch-start',payload)[0]==200
            # The submit connection is closed; completion belongs to the backend.
            job=finished('a'*32);assert job['succeeded']==2
            for row in job['rows']:
                result=row['result'];path=Path(result['path']);assert path.resolve().is_relative_to(data.resolve())
                assert path.is_file()
                status,body=request('GET',result['download_url'],raw=True)
                assert status==200 and b'fixture cached manuscript' in body
            assert request('POST','/api/benchmark/batch-start',payload)[0]==200
            assert len(request('GET','/api/benchmark/batch-jobs')[1]['jobs'])==2
            status,body=request('GET','/assets/benchmark_batch.js',raw=True)
            assert status==200 and body==(repo/'assets/benchmark_batch.js').read_bytes()
            result={'installedEntryReady':True,'authenticatedRoutes':True,'wrongOriginRejected':True,
                'restartWaitsForExplicitResume':True,'succeededRowNotRepeated':True,'backgroundCachedExports':2,
                'exportDownloadsHttp200':2,'sameIdDoesNotDuplicate':True,'installedAssetsMatch':True,
                'providerRequests':0,'productionDataAccess':False}
            target=repo/'.desktop-tools/benchmark-batch-recovery-20261017/installed-entry-verified.json'
            target.write_text(json.dumps(result,indent=2),'utf8');print(json.dumps(result))
        finally:
            process.terminate();process.wait(timeout=10);process.stdout.close();process.stderr.close()


if __name__=='__main__':main()
