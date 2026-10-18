"""Deploy only this image recovery patch, preserving installed/source drift."""
import difflib,importlib.util,json,marshal,os,shutil,struct,sys,types
from pathlib import Path
sys.dont_write_bytecode=True
repo=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('deployment_guard',repo/'scripts/deploy-benchmark-batch-recovery.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
base.audit=repo/'.desktop-tools/image-completion-repair-20261018';base.payload=base.audit/'payload'
audit,payload,host=base.audit,base.payload,base.host
original_protected=base.protected
def protected():
    result=original_protected();paths=list((base.data/'tasks').rglob('*.json'))+[base.data/'template-library.json']
    for folder in (base.data/'tasks').glob('*/covers'):
        paths+=list(folder.glob('*'))
    result.update({str(p):base.digest(p) for p in paths if p.is_file()})
    return result
base.protected=protected

def prepare():
    assert not (audit/'prepared.json').exists(),'Already prepared'
    baseline=base.verify(host);before=audit/'source-before';payload.mkdir(parents=True,exist_ok=True)
    header=importlib.util.MAGIC_NUMBER+struct.pack('<III',0,0,0)
    name='story1245_runtime';old=compile((before/(name+'.py')).read_text('utf8'),'<before>','exec')
    original=marshal.loads((host/'_internal'/(name+'.pyc')).read_bytes()[16:])
    assert base.signature(old)==base.signature(original),'Unrelated runtime module drift'
    new=compile((repo/(name+'.py')).read_text('utf8'),str(host/'_internal'/(name+'.pyc')),'exec')
    functions=lambda code:{c.co_name:c for c in code.co_consts if isinstance(c,types.CodeType)}
    a,b=functions(old),functions(new)
    assert {key for key in a.keys()|b.keys() if key not in a or key not in b or base.signature(a[key])!=base.signature(b[key])}=={'install'}
    target=payload/'_internal'/f'{name}.pyc';target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(header+marshal.dumps(new))
    name='scene_image_recovery';assert not (host/'_internal'/(name+'.pyc')).exists(),'Recovery already installed'
    (payload/'_internal'/(name+'.pyc')).write_bytes(header+marshal.dumps(compile((repo/(name+'.py')).read_text('utf8'),str(host/'_internal'/(name+'.pyc')),'exec')))
    assets=['assets/workflow_view.js','assets/image_pipeline.js','result.html']
    for name in assets:
        a=(before/name).read_text('utf8').splitlines(True);b=(repo/name).read_text('utf8').splitlines(True)
        installed=(host/'_internal'/name).read_text('utf8')
        for group in difflib.SequenceMatcher(a=a,b=b).get_grouped_opcodes(3):
            previous=''.join(a[group[0][1]:group[-1][2]]);current=''.join(b[group[0][3]:group[-1][4]])
            assert installed.count(previous)==1,'Installed context differs: '+name
            installed=installed.replace(previous,current,1)
        target=payload/'_internal'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(installed,'utf8')
    hashes={}
    for p in payload.rglob('*'):
        if not p.is_file() or p.name=='backend-runtime.json':continue
        relative=p.relative_to(payload).as_posix();original=host/relative
        hashes[relative]=base.digest(original) if original.is_file() else None
        if original.is_file():
            target=audit/'before'/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(original,target)
    shutil.copyfile(host/'backend-runtime.json',audit/'manifest-before.json')
    manifest=json.loads((host/'backend-runtime.json').read_text('utf8'));manifest['moduleCount']+=1
    for relative in hashes:manifest['files'][relative]=base.digest(payload/relative)
    base.write(payload/'backend-runtime.json',manifest)
    delta=''
    for name in ['story1245_runtime.py',*assets]:
        delta+=''.join(difflib.unified_diff((before/name).read_text('utf8').splitlines(True),(repo/name).read_text('utf8').splitlines(True),fromfile='before/'+name,tofile=name))
    (audit/'source-deltas.patch').write_text(delta,'utf8')
    node=audit/'node';(node/'tests').mkdir(parents=True,exist_ok=True);(node/'assets').mkdir(exist_ok=True)
    for name in assets:shutil.copyfile(payload/'_internal'/name,node/name)
    for name in ['image_completion_repair.test.js','workflow_failure.test.js','image_pipeline.test.js','workflow_draft_bar.test.js']:
        shutil.copyfile(repo/'tests'/name,node/'tests'/name)
    base.write(audit/'prepared.json',{'baseline':baseline,'oldHashes':hashes,'protected':protected(),'newGenerationRequests':0})
    print(json.dumps({'prepared':True,'changedFiles':len(hashes)}))

def test():
    sys.path[:0]=[str(payload/'_internal'),str(host/'_internal')]
    stdlib=Path.home()/'AppData/Local/Programs/Python/Python314/Lib';sys.path.append(str(stdlib))
    import unittest
    unittest.__path__.append(str(stdlib/'unittest'))
    import server,story1245_runtime
    server.ROOT=host/'_internal';server.PROMPTS_DIR=server.ROOT/'prompts';story1245_runtime.install(server)
    suites=[]
    for name in ['test_scene_image_recovery','test_batch_image_receipts','test_batch_image_http','test_task_revision',
                 'test_task_queue','test_task_pause','test_queue_cover_completion','test_runtime_updates1245','test_benchmark_batch_http']:
        spec=importlib.util.spec_from_file_location(name,repo/'tests'/(name+'.py'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        suites.append(unittest.defaultTestLoader.loadTestsFromModule(module))
    result=unittest.TextTestRunner(verbosity=1).run(unittest.TestSuite(suites))
    base.write(audit/'tested.json',{'testsRun':result.testsRun,'success':result.wasSuccessful(),'newGenerationRequests':0})
    raise SystemExit(not result.wasSuccessful())

def restage():
    assert not (audit/'installed.json').exists(),'Already installed'
    history=audit/('attempt-'+str(__import__('time').time_ns()));history.mkdir()
    for name in ['prepared.json','tested.json']:
        if (audit/name).exists():(audit/name).replace(history/name)
    prepare()

if __name__=='__main__':{'prepare':prepare,'restage':restage,'test':test,'apply':base.apply,'verify':base.verify_install}[sys.argv[1]]()
