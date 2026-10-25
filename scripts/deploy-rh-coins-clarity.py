"""Hot-update two static experiment assets only. Never restart or reload 074."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys

sys.stdout.reconfigure(encoding='utf8');sys.dont_write_bytecode=True
repo=Path(__file__).resolve().parents[1]
host=Path.home()/'AppData/Local/074 创作工作台/app074-backend'
data=Path.home()/'AppData/Local/com.app074.desktop/data'
audit=repo/'.desktop-tools/rh-coins-clarity-20261025';payload=audit/'payload'
assets=['rh-coins-experiment.html','assets/rh_coins_experiment.js']
sys.path.insert(0,str(repo/'scripts'))
from backend_runtime_manifest import verify,digest


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n','utf8')


def protected():
    paths=[data/'settings.json',data/'profiles.json',data/'task-queue.json']
    paths+=list((data/'rh-coins-experiment').rglob('*'))
    return {str(p):digest(p) for p in paths if p.is_file()}


def prepare():
    assert not (audit/'prepared.json').exists(),'Baseline already prepared; inspect instead of overwriting'
    baseline=verify(host);before=audit/'source-before'
    manifest=json.loads((host/'backend-runtime.json').read_text('utf8'))
    for name in assets:
        original=host/'_internal'/name
        assert digest(original)==digest(before/name),'Installed/source baseline differs: '+name
        target=payload/'_internal'/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(repo/name,target)
        backup=audit/'before/_internal'/name;backup.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(original,backup)
        manifest['files']['_internal/'+name]=digest(target)
    shutil.copyfile(host/'backend-runtime.json',audit/'before/backend-runtime.json')
    write(payload/'backend-runtime.json',manifest)
    static=audit/'static';static.mkdir(exist_ok=True)
    for path in (host/'_internal').glob('*.html'):shutil.copyfile(path,static/path.name)
    shutil.copytree(host/'_internal/assets',static/'assets',dirs_exist_ok=True)
    shutil.copytree(host/'_internal/scripts',static/'scripts',dirs_exist_ok=True)
    for name in assets:shutil.copyfile(payload/'_internal'/name,static/name)
    tests=static/'tests';tests.mkdir(exist_ok=True);shutil.copyfile(repo/'tests/rh_coins_experiment.test.cjs',tests/'rh_coins_experiment.test.cjs')
    write(audit/'prepared.json',{'baseline':baseline,'staticOnly':True,'oldHashes':{'_internal/'+name:digest(host/'_internal'/name) for name in assets}})
    print(json.dumps({'prepared':True,'staticAssets':2,'manifestSha256':digest(payload/'backend-runtime.json')}))


def test():
    node=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'
    result=subprocess.run([str(node),'--test','tests/rh_coins_experiment.test.cjs'],cwd=audit/'static',capture_output=True,text=True,encoding='utf8')
    (audit/'node-tests.log').write_text(result.stdout+result.stderr,'utf8')
    write(audit/'node-results.json',{'success':result.returncode==0,'manifestSha256':digest(payload/'backend-runtime.json'),'realProviderRequests':0})
    print(result.stdout);raise SystemExit(result.returncode)


def restage():
    assert not (audit/'installed.json').exists(),'Already applied'
    assert digest(host/'backend-runtime.json')==digest(audit/'before/backend-runtime.json'),'Runtime changed'
    manifest=json.loads((audit/'before/backend-runtime.json').read_text('utf8'))
    for name in assets:
        shutil.copyfile(repo/name,payload/'_internal'/name)
        shutil.copyfile(repo/name,audit/'static'/name)
        manifest['files']['_internal/'+name]=digest(payload/'_internal'/name)
    write(payload/'backend-runtime.json',manifest)
    print(json.dumps({'restagedStaticAssets':2,'manifestSha256':digest(payload/'backend-runtime.json')}))


def apply():
    sha=digest(payload/'backend-runtime.json');saved=json.loads((audit/'prepared.json').read_text('utf8'))
    assert not (audit/'installed.json').exists(),'Already applied'
    for name in ('node-results.json','candidate-entry-results.json','browser-results.json'):
        gate=json.loads((audit/name).read_text('utf8'));assert gate['success'] and gate['manifestSha256']==sha,'Stale gate: '+name
    assert digest(host/'backend-runtime.json')==digest(audit/'before/backend-runtime.json'),'Runtime changed'
    old=json.loads((host/'backend-runtime.json').read_text('utf8'));new=json.loads((payload/'backend-runtime.json').read_text('utf8'))
    assert {k:v for k,v in old.items() if k!='files'}=={k:v for k,v in new.items() if k!='files'}
    assert set(old['files'])==set(new['files'])
    changed={k for k in old['files'] if old['files'][k]!=new['files'][k]}
    assert changed=={'_internal/'+name for name in assets},'Only two static assets may change'
    for relative,expected in saved['oldHashes'].items():
        assert digest(host/relative)==expected
        assert digest(payload/relative)==new['files'][relative]
        assert (host/relative).resolve().is_relative_to(host.resolve())
    before=protected();installed=[];temporary=[]
    # Python code/executables are untouched. Existing WebViews keep their current
    # document and unsaved form; only the next normal page request sees new assets.
    try:
        for relative in [*sorted(changed),'backend-runtime.json']:
            target=host/relative;temp=target.with_name(target.name+'.074-clarity-'+secrets.token_hex(4)+'.tmp');temporary.append(temp)
            with (payload/relative).open('rb') as source,temp.open('xb') as output:
                shutil.copyfileobj(source,output);output.flush();os.fsync(output.fileno())
            os.replace(temp,target);installed.append(relative)
        result=verify(host)
    except BaseException:
        for relative in reversed(installed):shutil.copyfile(audit/'before'/relative,host/relative)
        raise
    finally:
        for temp in temporary:temp.unlink(missing_ok=True)
    after=protected()
    assert before==after,'Business files changed during installation; inspect before making an unchanged claim'
    write(audit/'installed.json',{'success':True,'runtime':result,'staticAssetsChanged':2,'backendCodeChanged':False,
        'applicationRestarted':False,'applicationPageReloaded':False,'protectedFiles':len(before),'businessFilesChanged':0,'realProviderRequests':0})
    print(json.dumps({'installed':True,'staticAssetsChanged':2,'runtimeFilesVerified':result['filesChecked'],'businessFilesChanged':0,'applicationRestarted':False}))


if __name__=='__main__':{'prepare':prepare,'restage':restage,'test':test,'apply':apply}[sys.argv[1]]()
