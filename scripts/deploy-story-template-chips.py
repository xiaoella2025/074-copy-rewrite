"""Guarded creation form recovery installation; no production task or provider execution."""
import difflib
import importlib.util
import json
import marshal
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
sys.dont_write_bytecode=True
sys.stdout.reconfigure(encoding='utf8')
repo=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('queue_deploy_previous',repo/'scripts/deploy-image-auto-retry.py')
prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
base=prior.base;base.audit=repo/'.desktop-tools/story-template-chips-20261022';base.payload=base.audit/'payload'
audit,payload,host=base.audit,base.payload,base.host
assets=['index.html','assets/form_libraries.js']
new_assets=[]
python_tests=['test_task_pause']
node_tests=['form_template_visibility.test.cjs','task_form_recovery.test.cjs','task_model_ui.test.cjs','task_reuse.test.js','pause_parameter_editor.test.cjs','workflow_failure.test.js']
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
    hashes={}
    for path in payload.rglob('*'):
        if not path.is_file() or path.name=='backend-runtime.json':continue
        relative=path.relative_to(payload).as_posix();old=host/relative
        hashes[relative]=base.digest(old) if old.exists() else None
        if old.exists():
            backup=audit/'before'/relative;backup.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(old,backup)
    shutil.copyfile(host/'backend-runtime.json',audit/'manifest-before.json')
    manifest=json.loads((host/'backend-runtime.json').read_text('utf8'));manifest['moduleCount']+=0
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
    sys.path[:0]=[str(payload/'_internal'),str(host/'_internal')]
    stdlib=Path.home()/'AppData/Local/Programs/Python/Python314/Lib';sys.path.append(str(stdlib))
    import unittest
    unittest.__path__.append(str(stdlib/'unittest'))
    import server,story1245_runtime
    server.ROOT=audit/'static';server.PROMPTS_DIR=host/'_internal/prompts';story1245_runtime.install(server)
    suites=[]
    for name in python_tests:
        spec=importlib.util.spec_from_file_location(name,repo/'tests'/(name+'.py'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        suites.append(unittest.defaultTestLoader.loadTestsFromModule(module))
    result=unittest.TextTestRunner().run(unittest.TestSuite(suites))
    base.write(audit/'tested.json',{'testsRun':result.testsRun,'success':result.wasSuccessful(),'manifestSha256':base.digest(payload/'backend-runtime.json'),'providerRequests':0})
    raise SystemExit(not result.wasSuccessful())


def node_test():
    node=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'
    result=subprocess.run([str(node),'--test',*[str(Path('tests')/name) for name in node_tests]],cwd=audit/'static',capture_output=True,text=True,encoding='utf8')
    (audit/'candidate-node.log').write_text(result.stdout+result.stderr,'utf8')
    base.write(audit/'candidate-node-results.json',{'success':result.returncode==0,'manifestSha256':base.digest(payload/'backend-runtime.json')})
    print(result.stdout[-1600:]);raise SystemExit(result.returncode)


def apply():
    manifest=json.loads((payload/'backend-runtime.json').read_text('utf8'))
    for name in ['tested.json','candidate-node-results.json','candidate-entry-results.json','browser-results.json']:
        gate=json.loads((audit/name).read_text('utf8'))
        assert gate['success'] and gate['manifestSha256']==base.digest(payload/'backend-runtime.json'),'Stale/failed gate: '+name
    for relative in json.loads((audit/'prepared.json').read_text('utf8'))['oldHashes']:
        assert base.digest(payload/relative)==manifest['files'][relative],'Payload changed after test'
    # This release contains only static pages. Atomic replacement leaves the
    # running page and backend untouched, so unsaved form input isn't closed.
    saved=json.loads((audit/'prepared.json').read_text('utf8'))
    allowed={'_internal/'+name for name in assets}
    assert set(saved['oldHashes'])==allowed,'Static-only deployment boundary changed'
    assert base.digest(host/'backend-runtime.json')==base.digest(audit/'manifest-before.json'),'Runtime changed'
    for relative,sha in saved['oldHashes'].items():
        target=host/relative
        assert (base.digest(target) if target.exists() else None)==sha,'Installed file changed'
    before=base.protected()
    for relative in ['_internal/'+name for name in assets if name!='index.html']+['_internal/index.html']:
        target=host/relative
        temporary=target.with_name(target.name+'.template-draft.tmp')
        shutil.copyfile(payload/relative,temporary);os.replace(temporary,target)
    target=host/'backend-runtime.json';temporary=target.with_suffix('.template-draft.tmp')
    shutil.copyfile(payload/'backend-runtime.json',temporary);os.replace(temporary,target)
    result=base.verify(host)
    assert before==base.protected(),'Business data changed during static installation'
    base.write(audit/'installed.json',{'runtime':result,'protected':before,'businessFilesChanged':0,'providerRequests':0,'staticOnly':True,'appClosed':False})
    print(json.dumps({'installed':True,'filesVerified':result['filesChecked'],'protectedFiles':len(before),'businessFilesChanged':0,'staticOnly':True,'appClosed':False}))


if __name__=='__main__':{'prepare':prepare,'test':test,'node-test':node_test,'apply':apply,'verify':base.verify_install}[sys.argv[1]]()
