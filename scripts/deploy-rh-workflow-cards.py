"""Guarded formal RH workflow provider installation; no production task or provider execution."""
import difflib
import importlib.util
import json
import marshal
from pathlib import Path
import shutil
import struct
import subprocess
import sys
sys.stdout.reconfigure(encoding='utf8')
sys.dont_write_bytecode=True
repo=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('queue_deploy_previous',repo/'scripts/deploy-image-auto-retry.py')
prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
base=prior.base;base.audit=repo/'.desktop-tools/rh-workflow-cards-20261025';base.payload=base.audit/'payload'
audit,payload,host=base.audit,base.payload,base.host
assets=['settings.html','assets/rh_workflow_settings.js']
new_assets=[]
new_modules=[]
full_modules=[]
python_tests=[]
node_tests=['rh_workflow_cards.test.cjs','rh_workflow_frontend.test.cjs','rh_workflow_catalog_ui.test.cjs','rh_coins_experiment.test.cjs']
targets={}






def prepare():
    assert not (audit/'installed.json').exists(),'Already installed'
    before=audit/'source-before';baseline=base.verify(host)
    header=importlib.util.MAGIC_NUMBER+struct.pack('<III',0,0,0);internal=payload/'_internal';internal.mkdir(parents=True,exist_ok=True)
    delta=''
    for name,paths in targets.items():
        relative='_internal/'+name+'.pyc';original=host/relative
        old=compile((before/(name+'.py')).read_text('utf8'),'<baseline>','exec')
        installed=marshal.loads(original.read_bytes()[16:]);new=compile((repo/(name+'.py')).read_text('utf8'),str(original),'exec')
        for path in paths:
            live=prior.nested(installed,path);previous=prior.nested(old,path);current=prior.nested(new,path)
            assert base.signature(live)==base.signature(previous),'Installed drift: '+str((name,path))
            assert live.co_freevars==current.co_freevars,'Closure changed'
            installed=prior.replace(installed,path,current)
        (payload/relative).write_bytes(header+marshal.dumps(installed))
        delta+=''.join(difflib.unified_diff((before/(name+'.py')).read_text('utf8').splitlines(True),
            (repo/(name+'.py')).read_text('utf8').splitlines(True),fromfile='before/'+name+'.py',tofile=name+'.py',n=0))
    for name in full_modules:
        relative='_internal/'+name+'.pyc';original=host/relative
        old=compile((before/(name+'.py')).read_text('utf8'),'<baseline>','exec')
        installed=marshal.loads(original.read_bytes()[16:])
        assert base.signature(old)==base.signature(installed),'Full module baseline drift: '+name
        (payload/relative).write_bytes(header+marshal.dumps(compile((repo/(name+'.py')).read_text('utf8'),str(original),'exec')))
        delta+=''.join(difflib.unified_diff((before/(name+'.py')).read_text('utf8').splitlines(True),(repo/(name+'.py')).read_text('utf8').splitlines(True),fromfile='before/'+name+'.py',tofile=name+'.py',n=0))
    for name in assets:
        a=(before/name).read_text('utf8').splitlines(True);b=(repo/name).read_text('utf8').splitlines(True)
        value=(host/'_internal'/name).read_text('utf8')
        for group in difflib.SequenceMatcher(a=a,b=b).get_grouped_opcodes(3):
            old=''.join(a[group[0][1]:group[-1][2]]);new=''.join(b[group[0][3]:group[-1][4]])
            assert value.count(old)==1,'Installed UI drift: '+name;value=value.replace(old,new,1)
        target=internal/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(value,'utf8')
        delta+=''.join(difflib.unified_diff(a,b,fromfile='before/'+name,tofile=name,n=0))
    (audit/'source-deltas.patch').write_text(delta,'utf8')
    for name in new_assets:
        assert not (host/'_internal'/name).exists(),'New asset already installed'
        target=internal/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(repo/name,target)
    for name in new_modules:
        relative='_internal/'+name+'.pyc';assert not (host/relative).exists(),'New module already installed'
        (payload/relative).write_bytes(header+marshal.dumps(compile((repo/(name+'.py')).read_text('utf8'),str(host/relative),'exec')))
    hashes={}
    for path in payload.rglob('*'):
        if not path.is_file() or path.name=='backend-runtime.json':continue
        relative=path.relative_to(payload).as_posix();old=host/relative
        hashes[relative]=base.digest(old) if old.exists() else None
        if old.exists():
            backup=audit/'before'/relative;backup.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(old,backup)
    shutil.copyfile(host/'backend-runtime.json',audit/'manifest-before.json')
    manifest=json.loads((host/'backend-runtime.json').read_text('utf8'));manifest['moduleCount']+=len(new_modules)
    for relative in hashes:manifest['files'][relative]=base.digest(payload/relative)
    base.write(payload/'backend-runtime.json',manifest)
    static=audit/'static';static.mkdir(exist_ok=True)
    for path in (host/'_internal').glob('*.html'):shutil.copyfile(path,static/path.name)
    shutil.copytree(host/'_internal/assets',static/'assets',dirs_exist_ok=True)
    for name in assets+new_assets:shutil.copyfile(internal/name,static/name)
    shutil.copytree(host/'_internal/scripts',static/'scripts',dirs_exist_ok=True)
    tests=static/'tests';tests.mkdir(exist_ok=True)
    for name in node_tests:shutil.copyfile(repo/'tests'/name,tests/name)
    base.write(audit/'prepared.json',{'baseline':baseline,'oldHashes':hashes,'protected':base.protected(),'providerRequests':0})
    print(json.dumps({'prepared':True,'files':len(hashes),'manifestSha256':base.digest(payload/'backend-runtime.json')}))


def test():
    node=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'
    script=r"const fs=require('node:fs'),vm=require('node:vm');const html=fs.readFileSync('settings.html','utf8');let n=0;for(const match of html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)){if(match[1].trim()){new vm.Script(match[1]);n++;}}new vm.Script(fs.readFileSync('assets/rh_workflow_settings.js','utf8'));console.log(JSON.stringify({scriptsChecked:n+1}));"
    result=subprocess.run([str(node),'-e',script],cwd=audit/'static',capture_output=True,text=True,encoding='utf8')
    base.write(audit/'tested.json',{'success':result.returncode==0,'manifestSha256':base.digest(payload/'backend-runtime.json'),'staticSyntax':True,'realGenerationSubmissions':0})
    print(result.stdout+result.stderr);raise SystemExit(result.returncode)


def node_test():
    node=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'
    result=subprocess.run([str(node),'--test',*[str(Path('tests')/name) for name in node_tests]],cwd=audit/'static',capture_output=True,text=True,encoding='utf8')
    (audit/'candidate-node.log').write_text(result.stdout+result.stderr,'utf8')
    base.write(audit/'candidate-node-results.json',{'success':result.returncode==0,'manifestSha256':base.digest(payload/'backend-runtime.json')})
    print(result.stdout[-1600:]);raise SystemExit(result.returncode)


def restage():
    assert not (audit/'installed.json').exists(),'Already installed'
    history=audit/('attempt-'+str(__import__('time').time_ns()));history.mkdir()
    for name in ['prepared.json','tested.json','candidate-node-results.json','candidate-entry-results.json','browser-results.json']:
        path=audit/name
        if path.exists():path.replace(history/name)
    prepare()


def apply():
    import os,time,uuid
    saved=json.loads((audit/'prepared.json').read_text('utf8'));manifest=json.loads((payload/'backend-runtime.json').read_text('utf8'))
    for name in ['tested.json','candidate-node-results.json','candidate-entry-results.json','browser-results.json']:
        gate=json.loads((audit/name).read_text('utf8'))
        assert gate['success'] and gate['manifestSha256']==base.digest(payload/'backend-runtime.json'),'Stale/failed gate: '+name
    assert base.digest(host/'backend-runtime.json')==base.digest(audit/'manifest-before.json'),'Runtime changed'
    expected={'_internal/settings.html','_internal/assets/rh_workflow_settings.js'}
    assert set(saved['oldHashes'])==expected,'Static-only deployment boundary changed'
    for relative,sha in saved['oldHashes'].items():
        assert base.digest(host/relative)==sha,'Installed resource changed'
        assert base.digest(payload/relative)==manifest['files'][relative],'Candidate changed'
    def replace(source,target):
        temporary=target.with_name(target.name+'.'+uuid.uuid4().hex+'.tmp')
        try:
            shutil.copyfile(source,temporary)
            for attempt in range(8):
                try:os.replace(temporary,target);break
                except OSError as error:
                    if getattr(error,'winerror',None) not in (5,32,33) or attempt==7:raise
                    time.sleep(.05*(attempt+1))
        finally:temporary.unlink(missing_ok=True)
    protected=base.protected();changed=[]
    try:
        for relative in ['_internal/assets/rh_workflow_settings.js','_internal/settings.html']:
            replace(payload/relative,host/relative);changed.append(relative)
        replace(payload/'backend-runtime.json',host/'backend-runtime.json')
        result=base.verify(host)
    except BaseException:
        for relative in reversed(changed):replace(audit/'before'/relative,host/relative)
        replace(audit/'manifest-before.json',host/'backend-runtime.json');raise
    after=base.protected();differences=[path for path in protected.keys()|after.keys() if protected.get(path)!=after.get(path)]
    base.write(audit/'installed.json',{'runtime':result,'protected':after,'businessFilesChanged':len(differences),'frontendOnly':True,'realGenerationSubmissions':0})
    print(json.dumps({'installed':True,'frontendOnly':True,'filesVerified':result['filesChecked'],'protectedFiles':len(after),'businessFilesChanged':len(differences)}))


if __name__=='__main__':{'prepare':prepare,'restage':restage,'test':test,'node-test':node_test,'apply':apply,'verify':base.verify_install}[sys.argv[1]]()
