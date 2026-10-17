"""Installed entry and browser fixture, disposable data and no paid actions."""
from contextlib import contextmanager
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import queue
import secrets
import subprocess
import sys
import tempfile
import threading

repo=Path(__file__).resolve().parent.parent
host=Path.home()/'AppData/Local/074 创作工作台/app074-backend'
audit=repo/'.desktop-tools/story1245-followups-20261017'

@contextmanager
def installed():
    with tempfile.TemporaryDirectory(prefix='074-cover-entry-') as directory:
        root=Path(directory);data=root/'data';task=data/'tasks/cover-fixture';task.mkdir(parents=True)
        def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False),'utf8')
        write(task/'02-meta.json',{'title':'测试标题','subtitle':['测试副标题'],'cover_image_prompts':['安静山景，人物位于左侧']})
        write(task/'client_config.json',{'generate':{'profile_id':'task-profile'},'cover':{'mode':'titled'},'image':{}})
        (task/'02-rewrite.txt').write_text('独立测试文案，不调用模型。','utf8')
        write(data/'profiles.json',[
            {'id':'task-profile','name':'任务文字配置','model':'fixture-a','apiKey':'offline-only-key','enabled':True},
            {'id':'cover-profile','name':'封面文字配置','model':'fixture-b','apiKey':'offline-only-key'}])
        token=secrets.token_hex(24)
        process=subprocess.Popen([str(host/'python.exe'),'-B',str(host/'_internal/desktop_backend.pyc'),
            '--data-dir',str(data),'--legacy-data-dir',str(root/'absent')],
            env={**os.environ,'APP074_SESSION_TOKEN':token},stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            text=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            lines=queue.Queue();threading.Thread(target=lambda:lines.put(process.stdout.readline()),daemon=True).start()
            ready=json.loads(lines.get(timeout=30));assert ready['event']=='ready'
            def request(method,path,value=None,auth=True,origin=None,raw=False):
                connection=http.client.HTTPConnection('127.0.0.1',ready['port'],timeout=5)
                headers={'Content-Type':'application/json'}
                if auth:headers['Cookie']='app074_session='+token
                if origin:headers['Origin']=origin
                connection.request(method,path,json.dumps(value) if value is not None else None,headers)
                response=connection.getresponse();status=response.status;body=response.read();connection.close()
                return status,body if raw else json.loads(body)
            yield request,data
        finally:
            process.terminate();process.wait(timeout=10);process.stdout.close();process.stderr.close()

def main():
    with installed() as (request,data):
        base='/api/task-cover/cover-fixture'
        assert request('GET',base,auth=False)[0]==403
        assert request('POST',base+'/save',{'slot':1,'profile_id':'cover-profile'},origin='https://foreign.invalid')[0]==403
        original=request('GET',base)[1]
        assert len(original['templates'])==6
        assert len(original['profiles'])==2
        assert 'offline-only-key' not in json.dumps(original)
        assert request('POST',base+'/save',{'slot':1,'profile_id':'cover-profile'})[0]==200
        assert request('POST',base+'/save',{'slot':2,'title':'第二张测试标题','profile_id':'task-profile'})[0]==200
        template={**original['templates'][0],'name':'我的封面模板','compositionRule':'人物居左，山景留白','titleLayout':'顶端大字「{{TITLE}}」'}
        status,second=request('POST',base+'/save-template',{'slot':2,'template':template})
        assert status==200 and second['template'].startswith('custom-')
        first=request('GET',base)[1];second=request('GET',base+'?slot=2')[1]
        assert first['profile_override']=='cover-profile' and second['profile_override']=='task-profile'
        assert first['title']=='测试标题' and second['title']=='第二张测试标题'
        assert first['template']=='cinematic-poster' and second['template'].startswith('custom-')
        assert '顶端大字' in second['prompt']
        assert request('POST',base+'/save',{'slot':1,'profile_id':'deleted'})[0]==409
        assert (data/'template-library.json').is_file()
        assert not list((data/'tasks').rglob('cover-job-*.json'))
        result={'installedEntryReady':True,'authAndOriginChecked':True,'independentModelsAndTitles':True,
                'customLibraryAndSnapshot':True,'reloadRetainsSettings':True,'noCredentialsInCoverResponse':True,
                'providerRequests':0,'productionDataAccess':False}
        (audit/'installed-entry-verified.json').write_text(json.dumps(result,indent=2),'utf8')
        print(json.dumps(result),flush=True)
        if '--serve' not in sys.argv:return
        html='''<!doctype html><html lang="zh"><meta charset="utf-8"><title>074 封面设置 · 独立验收</title>
<link rel="stylesheet" href="/assets/story_theme.css"><link rel="stylesheet" href="/assets/task_cover.css">
<style>body{margin:20px;background:#0b1012;color:#e5eaec;font-family:Arial}main{max-width:1100px;margin:auto}button{cursor:pointer}.btn{border:1px solid #303a40;border-radius:5px;background:#151c20;color:#e5eaec;padding:6px}.btn-primary{background:#00b899;color:#041411}select{height:26px}</style>
<main><h3>封面设置 · 独立数据验收</h3><div id="one"></div><div id="two"></div></main>
<script src="/assets/task_cover.js"></script><script>window.cards=[app074TaskCover.render(document.querySelector('#one'),{taskId:'cover-fixture',slot:1}),app074TaskCover.render(document.querySelector('#two'),{taskId:'cover-fixture',slot:2})];</script></html>'''.encode()
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                if self.path=='/':status,body,kind=200,html,'text/html; charset=utf-8'
                elif self.path in ('/assets/task_cover.js','/assets/task_cover.css','/assets/story_theme.css'):
                    status,body=request('GET',self.path,raw=True);kind='text/javascript' if self.path.endswith('.js') else 'text/css'
                elif self.path.startswith(base):status,value=request('GET',self.path);body=json.dumps(value).encode();kind='application/json'
                else:status,body,kind=404,b'not found','text/plain'
                self.send_response(status);self.send_header('Content-Type',kind);self.end_headers();self.wfile.write(body)
            def do_POST(self):
                if self.path not in (base+'/save',base+'/save-template'):self.send_error(403);return
                value=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))))
                status,result=request('POST',self.path,value)
                self.send_response(status);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(json.dumps(result).encode())
        httpd=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        print(json.dumps({'fixtureUrl':f'http://127.0.0.1:{httpd.server_port}/'}),flush=True)
        try:httpd.serve_forever()
        finally:httpd.server_close()

if __name__=='__main__':main()
