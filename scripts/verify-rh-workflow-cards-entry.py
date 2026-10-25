"""Actual desktop entry, isolated data, fake RH workflow HTTP; no paid generation."""
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
audit=repo/'.desktop-tools/rh-workflow-cards-20261025'
host=Path.home()/'AppData/Local/074 创作工作台/app074-backend'


def main():
    installed='--installed' in sys.argv
    resource=host/'_internal' if installed else audit/'static'
    manifest=host/'backend-runtime.json' if installed else audit/'payload/backend-runtime.json'
    sha=hashlib.sha256(manifest.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix='074-rh-workflow-provider-') as temporary:
        root=Path(temporary);data=root/'data';data.mkdir();normal=data/'tasks/unchanged';normal.mkdir(parents=True)
        (normal/'existing.png').write_bytes(b'preserved original paid output')
        def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2),'utf8')
        settings={'image':{'provider':'modelscope'},'modelscope':{'tokens':['fixture-token'],'model':'ordinary-model','auto_fallback_gpt':False}}
        write(data/'settings.json',settings);write(data/'profiles.json',[])
        write(data/'task-queue.json',{'version':1,'jobs':[],'batches':[]})
        events=root/'events.json';write(events,[])
        task=data/'tasks/formal-cover';task.mkdir()
        write(task/'client_config.json',{'cover':{'provider':'modelscope','mode':'title'}})
        write(task/'cover-editor.json',{'1':{'provider':'modelscope'}})
        write(task/'02-meta.json',{'title':'古人雅事','cover_image_prompts':['旧书房，完全背影']})
        write(task/'request.json',{'title':'古人雅事','content':'书房故事'})
        write(task/'progress.json',{'status':'failed','step':6})
        original={'status':'unknown','provider':'runninghub','operationId':'old-operation','opaque':{'preserve':['all']}}
        write(task/'cover-job-1.json',original)
        (task/'existing-scene.png').write_bytes(b'original scene');(task/'original.mp3').write_bytes(b'original voice')
        buffer=io.BytesIO();Image.new('RGB',(32,48),'blue').save(buffer,'PNG');png=buffer.getvalue()
        fixture_image=audit/'fixture-reference.png';fixture_image.write_bytes(png)
        sys.path[:0]=[str(repo/'tests'),str(repo)]
        from test_rh_coins_experiment import graph
        from test_rh_workflow_graphs import fixture as fixture_graph
        workflow_graphs={'1819583592967110658':fixture_graph('flux'),'1912776705101234178':fixture_graph('sdxl'),'1954942638128599042':fixture_graph('qwen-chinese')}
        fixture=r'''
import base64,json
import task_cover,rh_coins_workflow

task_queue.TaskQueue.start=lambda self:None
events=Path(EVENTS)
png=base64.b64decode(PNG)
graph=GRAPH
workflow_graphs=WORKFLOW_GRAPHS

def record(value):
    items=json.loads(events.read_text('utf8'));items.append(value);events.write_text(json.dumps(items),'utf8');return len(items)

def fake_post(url,headers,body,**kwargs):
    payload=json.loads(body)
    if url.endswith('/accountStatus'):
        record({'kind':'account'})
        return 200,json.dumps({'code':0,'data':{'remainCoins':'73100','remainMoney':'0.001','apiType':'NORMAL'}})
    if url.endswith('/getJsonApiFormat'):
        record({'kind':'workflow'})
        return 200,json.dumps({'code':0,'data':{'prompt':json.dumps(workflow_graphs.get(payload['workflowId'],graph))}})
    if url.endswith('/create'):
        frozen=json.loads(payload['workflow']);summary=rh_coins_workflow.audit_graph(frozen)
        assert frozen[summary['sizeNode']]['inputs']['batch_size']==1 and payload['nodeInfoList']==[]
        assert all(not node['class_type'].startswith('RH_') for node in frozen.values())
        number=record({'kind':'submit','workflowId':payload['workflowId'],'family':summary['kind'],'prompt':frozen[summary['promptNode']]['inputs']['text']})
        return 200,json.dumps({'code':0,'data':{'taskId':'fixture-rh-'+str(number),'taskStatus':'QUEUED'}})
    if url.endswith('/outputs'):
        previous=json.loads(events.read_text('utf8'))
        record({'kind':'query'})
        if not any(item['kind']=='query' for item in previous):return 200,json.dumps({'code':804})
        return 200,json.dumps({'code':0,'data':[{'fileUrl':'https://fixture.invalid/rh.png','fileType':'png','nodeId':'9'}]})
    raise AssertionError('Unexpected transport '+url)

original_bytes=task_cover.image_bytes
task_cover.image_bytes=lambda result: png if result.get('url')=='https://fixture.invalid/rh.png' else original_bytes(result)
original_dispatch=server.image_dispatcher
server.image_dispatcher=lambda cfg,*args,**kwargs: {'b64':base64.b64encode(png).decode(),'provider':'modelscope'} if cfg.get('provider')=='modelscope' else original_dispatch(cfg,*args,**kwargs)
server._rh_coins_post_json=fake_post

def forbidden(request,*args,**kwargs):
    if (getattr(request,'full_url',request))=='https://fixture.invalid/rh.png':
        import io
        return io.BytesIO(png)
    raise AssertionError('unmocked transport is forbidden')
server.urllib.request.urlopen=forbidden
'''.replace('EVENTS',repr(str(events))).replace('PNG',repr(base64.b64encode(png).decode())).replace('WORKFLOW_GRAPHS',repr(workflow_graphs)).replace('GRAPH',repr(graph()))
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
            base='/api/rh-coins-experiment'
            protected={str(path.relative_to(data)):path.read_bytes() for path in [data/'profiles.json',data/'task-queue.json',normal/'existing.png',task/'existing-scene.png',task/'original.mp3']}
            original_bytes=(task/'cover-job-1.json').read_bytes()
            assert request('GET',base,authorized=False)[0]==403
            assert request('POST','/api/task-cover/formal-cover/replace-unknown',{},False)[0]==403
            assert request('GET','/api/settings')[1]['image']['provider']=='modelscope'
            assert request('POST',base+'/config',{'enabled':True,'api_key':'fixture-member-key','member_key_confirmed':True,'web_tested':True})[0]==200
            status,value=request('POST',base+'/check',{});assert status==200 and value['checked'],(status,value)
            assert request('POST',base+'/workflows/add',{'name':'custom','url':'1912776705101234178'},False)[0]==403
            for key in ['flux-native','sdxl-native']:
                assert request('POST',base+'/config',{'preset':key,'web_tested':True})[0]==200
                status,value=request('POST',base+'/check',{});assert status==200 and value['checked'],(status,value)
            status,value=request('POST',base+'/workflows/add',{'name':'我的SDXL','url':'https://www.runninghub.cn/post/1912776705101234178'});assert status==200,(status,value)
            assert any(item['key']=='custom-1912776705101234178' for item in value['candidates'])
            assert request('GET',base)[1]['preset']=='sdxl-native'
            assert request('POST',base+'/config',{'preset':'flux-native','web_tested':True})[0]==200
            projected=request('GET','/api/settings')[1]
            assert projected['runninghub_workflow']['configured']
            assert 'fixture-member-key' not in json.dumps(projected)
            assert request('POST','/api/settings',{'image_provider':'runninghub_workflow'})[0]==200
            assert request('GET','/api/settings')[1]['image']['provider']=='runninghub_workflow'
            assert not any(item['kind']=='submit' for item in json.loads(events.read_text('utf8')))
            current=request('GET','/api/task-cover/formal-cover?slot=1')[1]
            assert current['job']['status']=='unknown' and current['localCoverAvailable'] is False
            confirm={'slot':1,'provider':'modelscope','operation_id':'entry-switch-operation','acknowledge_unknown':True}
            assert request('POST','/api/task-cover/formal-cover/replace-unknown',{**confirm,'acknowledge_unknown':False})[0]==409
            status,value=request('POST','/api/task-cover/formal-cover/replace-unknown',confirm);assert status==200,(status,value)
            assert value['job']['status']=='replacement_ready'
            archives=list((task/'.cover-replacements').glob('*.json'));assert len(archives)==1 and archives[0].read_bytes()==original_bytes
            assert request('POST','/api/task-cover/formal-cover/replace-unknown',confirm)[1]['job']['operationId']=='entry-switch-operation'
            assert not any(item['kind']=='submit' for item in json.loads(events.read_text('utf8')))
            # Use a second task for the real provider integration through the actual authenticated cover route.
            formal=data/'tasks/formal-workflow';formal.mkdir()
            write(formal/'client_config.json',{'generate':{'title':'完整主标题','reference':'书房故事'},'image':{'provider':'runninghub_workflow','workflow':'flux-native'},'cover':{'provider':'runninghub_workflow','mode':'title','workflow':'sdxl-native'},'tts':{}})
            write(formal/'02-meta.json',{'title':'完整主标题','subtitle':['完整副标题']})
            write(formal/'request.json',{'extra':'不露脸'})
            prompt='主标题完整主标题，副标题完整副标题；保留排版，人物完全背对镜头。'
            body={'slot':1,'operation_id':'entry-formal-operation','prompt':prompt}
            status,value=request('POST','/api/task-cover/formal-workflow/generate',body);assert status==200,(status,value)
            assert value['job']['status']=='ok' and value['job']['taskId'].startswith('fixture-rh-')
            assert value['localCoverAvailable'] and (formal/'cover-poster-1.png').is_file()
            assert request('POST','/api/task-cover/formal-workflow/generate',body)[1]['job']['taskId']==value['job']['taskId']
            submitted=[item for item in json.loads(events.read_text('utf8')) if item['kind']=='submit']
            assert len(submitted)==1 and submitted[0]['workflowId']=='1912776705101234178' and '完整主标题' in submitted[0]['prompt'] and '不露脸' in submitted[0]['prompt']
            scene=data/'tasks/formal-scene';scene.mkdir()
            status,value=request('POST','/api/step4_generate_images',{'task_id':'formal-scene','provider':'runninghub_workflow','workflow':'flux-native','prompts':[{'idx':1,'desc_prompt':'书房环境，无人物'}],'ratio':'9:16','resolution':'1k','concurrency':1,'retry':False})
            assert status==200 and value['results'][0]['ok'],(status,value)
            creates=[event for event in json.loads(events.read_text('utf8')) if event['kind']=='submit']
            assert len(creates)==2 and creates[-1]['workflowId']=='1819583592967110658'
            assert request('GET','/settings.html')[0]==200
            assert b'rh_workflow_settings.js' in request('GET','/settings.html')[1]
            assert b'runninghub_workflow' in request('GET','/assets/task_cover.js')[1]
            assert request('GET','/rh-coins-experiment.html')[0]==200
            for path,value in protected.items():assert (data/path).read_bytes()==value,path
            result={'success':True,'manifestSha256':sha,'actualDesktopEntry':True,'formalSettingsSave':True,
                    'catalogAddsWithoutSubmit':True,'independentSceneAndCoverWorkflows':True,'normalizedLocalGraphOnly':True,'sharedMemberConfig':True,'defaultSwitchIsExplicit':True,'authenticatedRoutes':True,
                    'coverReplacementArchivesExactBytes':True,'replacementConfirmationDoesNotSubmit':True,
                    'formalCoverPromptAndRequirementPreserved':True,'formalTaskIdSaved':True,'duplicateSubmitReusesId':True,
                    'keyNotReturned':True,'productionArtifactsUnchanged':True,'mockSubmissions':2,'realProviderRequests':0}
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
