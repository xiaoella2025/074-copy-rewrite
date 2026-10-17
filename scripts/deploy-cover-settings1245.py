"""Scoped cover follow-up deployment; reuse audited lifecycle/data guards."""
import difflib
import importlib.util
import json
import marshal
import os
from pathlib import Path
import shutil
import struct
import sys
import types

sys.dont_write_bytecode=True
repo=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('prior_deployment',repo/'scripts/deploy-benchmark-batch-recovery.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
base.audit=repo/'.desktop-tools/story1245-followups-20261017'
continuation='--continuation' in sys.argv
if continuation:base.audit=base.audit/'continuation'
base.payload=base.audit/'payload'
audit,payload,host=base.audit,base.payload,base.host
original_protected=base.protected

def protected():
    result=original_protected()
    paths=[base.data/'template-library.json']
    for pattern in ('*/cover*.json','*/cover-poster-*.png','*/02-meta.json','*/02-rewrite.txt'):
        paths+=list((base.data/'tasks').glob(pattern))
    result.update({str(p):base.digest(p) for p in paths if p.is_file()})
    return result

base.protected=protected

def prepare():
    assert not (audit/'prepared.json').exists(),'Baseline already captured'
    baseline=base.verify(host);before=audit/'source-before'
    header=importlib.util.MAGIC_NUMBER+struct.pack('<III',0,0,0)
    allowed=({'task_cover':{'cover_template','build_selected_prompt','initial','_action'}} if continuation else
             {'task_cover':{'cover_template','view','validate_options','_action'},'template_store':{'validate','TemplateStore'}})
    for module,expected in allowed.items():
        relative='_internal/'+module+'.pyc'
        original=marshal.loads((host/relative).read_bytes()[16:])
        old_code=compile((before/(module+'.py')).read_text('utf8'),'<baseline>','exec')
        assert base.signature(original)==base.signature(old_code),'Unrelated installed drift: '+module
        code=compile((repo/(module+'.py')).read_text('utf8'),str(host/relative),'exec')
        old={c.co_name:c for c in old_code.co_consts if isinstance(c,types.CodeType)}
        new={c.co_name:c for c in code.co_consts if isinstance(c,types.CodeType)}
        changed={name for name in old.keys()|new.keys() if name not in old or name not in new or base.signature(old[name])!=base.signature(new[name])}
        assert changed==expected,'Unexpected source changes: '+module+str(changed)
        target=payload/relative;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(header+marshal.dumps(code))
    names=[] if continuation else ['assets/task_cover.js','assets/task_cover.css']
    css_before=before/'assets/task_cover.css'
    if names and not css_before.exists():
        # One additive CSS rule was made in this execution. Prove the rest of
        # source bytes equal installed bytes before capturing that baseline.
        current=(repo/names[1]).read_text('utf8').splitlines(True)
        original=''.join(line for line in current if not line.startswith('.cover-result-editor.cover-template-editor textarea'))
        assert original==(host/'_internal'/names[1]).read_text('utf8'),'Unrelated CSS drift'
        shutil.copyfile(host/'_internal'/names[1],css_before)
    for name in names:
        assert base.digest(host/'_internal'/name)==base.digest(before/name),'Unrelated installed asset drift'
        target=payload/'_internal'/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(repo/name,target)
    old_hashes={}
    for path in payload.rglob('*'):
        if not path.is_file() or path.name=='backend-runtime.json':continue
        relative=path.relative_to(payload).as_posix();original=host/relative
        old_hashes[relative]=base.digest(original)
        backup=audit/'before'/relative;backup.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(original,backup)
    shutil.copyfile(host/'backend-runtime.json',audit/'manifest-before.json')
    manifest=json.loads((host/'backend-runtime.json').read_text('utf8'))
    for relative in old_hashes:manifest['files'][relative]=base.digest(payload/relative)
    base.write(payload/'backend-runtime.json',manifest)
    deltas={}
    for relative in [*(module+'.py' for module in allowed),*names]:
        old,new=before/relative,repo/relative
        delta=''.join(difflib.unified_diff(old.read_text('utf8').splitlines(True),new.read_text('utf8').splitlines(True),fromfile='before/'+relative,tofile=relative))
        target=audit/'source-deltas'/(relative+'.diff');target.parent.mkdir(parents=True,exist_ok=True);target.write_text(delta,'utf8')
        deltas[relative]={'before':base.digest(old),'after':base.digest(new)}
    base.write(audit/'prepared.json',{'baseline':baseline,'oldHashes':old_hashes,'sourceDeltas':deltas,'protected':protected(),'providerRequests':0})
    print(json.dumps({'prepared':True,'files':len(old_hashes)}))

def test():
    sys.path[:0]=[str(payload/'_internal'),str(host/'_internal')]
    stdlib=Path.home()/'AppData/Local/Programs/Python/Python314/Lib';sys.path.append(str(stdlib))
    import unittest
    unittest.__path__.append(str(stdlib/'unittest'))
    import server,story1245_runtime
    story1245_runtime.install(server);server.ROOT=host/'_internal';server.PROMPTS_DIR=server.ROOT/'prompts'
    os.environ['PATH']=str(host/'_internal')+os.pathsep+os.environ.get('PATH','')
    names=['test_cover_settings1245','test_cover_cached1245','test_task_cover','test_cover_provider_resume',
           'test_cover_workflow_resume','test_template_library','test_queue_cover_completion','test_task_pause',
           'test_connected_modules_http','test_task_revision','test_runtime_updates1245']
    suites=[]
    for name in names:
        spec=importlib.util.spec_from_file_location(name,repo/'tests'/(name+'.py'))
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        suites.append(unittest.defaultTestLoader.loadTestsFromModule(module))
    result=unittest.TextTestRunner(verbosity=1).run(unittest.TestSuite(suites))
    base.write(audit/'tested.json',{'testsRun':result.testsRun,'skipped':len(result.skipped),'success':result.wasSuccessful(),'providerRequests':0})
    raise SystemExit(not result.wasSuccessful())

def restage():
    assert not (audit/'installed.json').exists(),'Already installed'
    history=audit/('attempt-'+str(__import__('time').time_ns()));history.mkdir()
    for name in ('prepared.json','tested.json'):
        path=audit/name
        if path.exists():path.replace(history/name)
    prepare()

if __name__=='__main__':{'prepare':prepare,'restage':restage,'test':test,'apply':base.apply,'verify':base.verify_install}[sys.argv[1]]()
