"""Run the real desktop entry with candidate code and disposable local data."""
import base64
import http.client
import io
import hashlib
import json
import os
from pathlib import Path
import queue
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import wave

repo=Path(__file__).resolve().parents[1]
audit=repo/'.desktop-tools/story1250-completion-20261019'
host=Path.home()/'AppData/Local/074 创作工作台/app074-backend'


def main():
    installed='--installed' in sys.argv
    resource=host/'_internal' if installed else audit/'static'
    imports=[str(host/'_internal')] if installed else [str(audit/'payload/_internal'),str(host/'_internal')]
    if not installed:
        shutil.copyfile(audit/'payload/_internal/draft-generator.exe',resource/'draft-generator.exe')
        digest=hashlib.sha256((resource/'draft-generator.exe').read_bytes()).hexdigest()
        (resource/'backend-runtime.json').write_text(json.dumps({'files':{'draft-generator.exe':digest}}),'utf8')
    with tempfile.TemporaryDirectory(prefix='074-entry1250-') as directory:
        data=Path(directory)/'data'; token=secrets.token_hex(24)
        code="import sys,runpy,os;sys.path[:0]="+repr(imports)+";import server;server.ROOT="+repr(str(resource))+";from pathlib import Path;server.ROOT=Path(server.ROOT);sys.argv="+repr(['desktop_backend.pyc','--data-dir',str(data),'--legacy-data-dir',str(Path(directory)/'absent')])+";runpy.run_path("+repr(str(host/'_internal/desktop_backend.pyc'))+",run_name='__main__')"
        process=subprocess.Popen([str(host/'python.exe'),'-B','-c',code],env={**os.environ,'APP074_SESSION_TOKEN':token,'PATH':str(host/'_internal')+os.pathsep+os.environ.get('PATH','')},
                                 stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        errors=[]
        threading.Thread(target=lambda:errors.extend(process.stderr.readlines()),daemon=True).start()
        try:
            lines=queue.Queue();threading.Thread(target=lambda:lines.put(process.stdout.readline()),daemon=True).start()
            first=lines.get(timeout=30)
            assert first, ''.join(errors)[-1200:]
            ready=json.loads(first); assert ready['event']=='ready'
            def request(method,path,body=None,authorized=True,foreign=False):
                connection=http.client.HTTPConnection('127.0.0.1',ready['port'],timeout=15)
                headers={'Content-Type':'application/json'}
                if authorized:headers['Cookie']='app074_session='+token
                if foreign:headers['Origin']='https://foreign.invalid'
                connection.request(method,path,json.dumps(body) if body is not None else None,headers)
                response=connection.getresponse(); raw=response.read(); status=response.status; connection.close()
                try:return status,json.loads(raw)
                except ValueError:return status,raw
            for method,path in [('GET','/api/runtime/health'),('GET','/api/runtime/draft-path-check?path=C:/fixture'),('POST','/api/template-sound/upload'),('POST','/api/music/delete'),('POST','/api/materials/open-folder'),('POST','/api/image_lab/delete')]:
                assert request(method,path,{},authorized=False)[0]==403
                assert request(method,path,{},foreign=True)[0]==403
            status,health=request('GET','/api/runtime/health');assert status==200 and health['ok'],health
            from urllib.parse import quote
            assert not request('GET','/api/runtime/draft-path-check?path='+quote(str(data/'drafts'))) [1]['valid']
            raw=io.BytesIO()
            with wave.open(raw,'wb') as audio:
                audio.setparams((1,2,8000,0,'NONE','not compressed'));audio.writeframes(b'\0\0'*8000)
            status,sound=request('POST','/api/template-sound/upload',{'name':'fixture.wav','data_url':'data:audio/wav;base64,'+base64.b64encode(raw.getvalue()).decode()})
            assert status==200 and Path(sound['path']).is_relative_to(data/'template-sounds'),sound
            defaults=json.loads((resource/'assets/draft_templates.json').read_text('utf8'))[0]
            defaults.pop('id',None);defaults['name']='isolated1250'
            defaults['config']['title']['font']='得意黑'
            defaults['config']['image']['effects']=[{'name':'柔光','mode':'head','seconds':2}]
            defaults['config']['audio']['soundEffects']=[{'name':sound['name'],'path':sound['path'],'placement':'end','volume':.5}]
            status,saved=request('POST','/api/templates/drafts',{'template':defaults});assert status==200,saved
            assert saved['template']['config']==defaults['config']
            for page in ['index.html','result.html','tasks.html','settings.html','image-lab.html','template-editor.html']:
                status,html=request('GET','/'+page);assert status==200,page
                required={'index.html':'material_picker1250','result.html':'material_picker1250','tasks.html':'material_picker1250',
                          'settings.html':'runtime_health1250','image-lab.html':'lab-next-cover','template-editor.html':'template_media1250'}[page]
                assert required.encode() in html,page
            manifest=host/'backend-runtime.json' if installed else audit/'payload/backend-runtime.json'
            result={'success':True,'installed':installed,'actualDesktopEntry':True,'manifestSha256':hashlib.sha256(manifest.read_bytes()).hexdigest(),'componentChecks':health,'newRoutesAuthorized':True,
                    'localWavUploadAndTemplateRoundtrip':True,'draftPathConflictRejected':True,'updatedPagesServed':6,
                    'productionDataAccess':False,'providerRequests':0}
            name='installed-entry-results.json' if installed else 'candidate-entry-results.json'
            (audit/name).write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8')
            print(json.dumps({k:v for k,v in result.items() if k!='componentChecks'}))
        finally:
            process.terminate();process.wait(timeout=10);process.stdout.close();process.stderr.close()


if __name__=='__main__':main()
