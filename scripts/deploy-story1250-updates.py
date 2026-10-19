"""Guarded 1.25 existing-module update; preserve installed drift and user data."""
import difflib
import importlib.util
import json
import marshal
from pathlib import Path
import shutil
import struct
import sys
sys.dont_write_bytecode = True
repo = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('previous_deploy1250', repo/'scripts/deploy-image-auto-retry.py')
prior = importlib.util.module_from_spec(spec); spec.loader.exec_module(prior)
base = prior.base
base.audit = repo/'.desktop-tools/story1250-completion-20261019'
base.payload = base.audit/'payload'
audit, payload, host = base.audit, base.payload, base.host
original_protected=base.protected


def protected():
    result=original_protected()
    for name in ['music','materials','image-lab','template-sounds','covers']:
        folder=base.data/name
        if folder.is_dir():
            result.update({str(path):base.digest(path) for path in folder.rglob('*') if path.is_file()})
    return result


base.protected=protected
modules = ['story1245_runtime','template_store','image_lab','music_library','task_queue']
new_modules = ['story1250_safety','story1250_assets']
assets = ['index.html','result.html','tasks.html','settings.html','image-lab.html','template-editor.html',
          'assets/image_lab.js','assets/image_lab.css','assets/template_editor.js','assets/bgm_library.js','assets/scene_image_editor.js','assets/workflow_view.js']
new_assets = ['assets/draft_catalog1250.json','assets/template_media1250.js','assets/template_media1250.css',
              'assets/runtime_health1250.js','assets/material_picker1250.js']
python_tests = ['test_story1250_safety','test_story1250_assets','test_story1250_http','test_template1250','test_image_lab1250',
                'test_template_library','test_image_lab_references','test_material_groups','test_music_library',
                'test_runtime_updates1245','test_culture_titles','test_image_auto_retry','test_scene_image_recovery',
                'test_queue_cover_completion','test_cover_settings1245','test_subtitle_alignment1245','test_resume1250','test_cover_title1250','test_task_queue']
node_tests = ['runtime_health1250.test.js','template_media1250.test.js','image_lab1250.test.cjs','music_delete1250.test.cjs',
              'music_library.test.cjs','material_groups.test.js','scene_reference_editor.test.js','scene_image_editor.test.js',
              'image_pipeline.test.js','task_reuse.test.js','workflow_failure.test.js','resume1250.test.js','workflow_draft_bar.test.js']


def prepare():
    assert not (audit/'prepared.json').exists(), 'Already prepared'
    baseline=base.verify(host); before=audit/'source-before'
    internal=payload/'_internal'; internal.mkdir(parents=True,exist_ok=True)
    header=importlib.util.MAGIC_NUMBER+struct.pack('<III',0,0,0)
    delta=''
    for name in modules+new_modules:
        source=repo/(name+'.py'); original=host/'_internal'/(name+'.pyc')
        if name in modules:
            old=compile((before/(name+'.py')).read_text('utf8'),'<before>','exec')
            live=marshal.loads(original.read_bytes()[16:])
            assert base.signature(old)==base.signature(live), 'Installed Python drift: '+name
            delta+=''.join(difflib.unified_diff((before/(name+'.py')).read_text('utf8').splitlines(True),source.read_text('utf8').splitlines(True),fromfile='before/'+name+'.py',tofile=name+'.py'))
        else: assert not original.exists(), 'New module already installed: '+name
        (internal/(name+'.pyc')).write_bytes(header+marshal.dumps(compile(source.read_text('utf8'),str(original),'exec')))
    for name in assets:
        a=(before/name).read_text('utf8').splitlines(True); b=(repo/name).read_text('utf8').splitlines(True)
        value=(host/'_internal'/name).read_text('utf8')
        for group in difflib.SequenceMatcher(a=a,b=b).get_grouped_opcodes(3):
            previous=''.join(a[group[0][1]:group[-1][2]]); current=''.join(b[group[0][3]:group[-1][4]])
            assert value.count(previous)==1, 'Installed asset drift: '+name
            value=value.replace(previous,current,1)
        target=internal/name; target.parent.mkdir(parents=True,exist_ok=True); target.write_text(value,'utf8')
        delta+=''.join(difflib.unified_diff(a,b,fromfile='before/'+name,tofile=name))
    for name in new_assets:
        assert not (host/'_internal'/name).exists(), 'New asset already installed: '+name
        target=internal/name; target.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(repo/name,target)
    candidate=repo/'.desktop-tools/story1250-audit/installer/draft-generator.exe'
    evidence=json.loads((audit/'offline-generator1250-structure.json').read_text('utf8'))
    assert candidate.is_file() and evidence.get('candidate_sha256')==base.digest(candidate), 'Offline generator acceptance evidence missing or stale'
    shutil.copyfile(candidate,internal/'draft-generator.exe')
    (audit/'source-deltas.patch').write_text(delta,'utf8')
    hashes={}
    for path in payload.rglob('*'):
        if not path.is_file() or path.name=='backend-runtime.json': continue
        relative=path.relative_to(payload).as_posix(); original=host/relative
        hashes[relative]=base.digest(original) if original.is_file() else None
        if original.is_file():
            target=audit/'before'/relative; target.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(original,target)
    shutil.copyfile(host/'backend-runtime.json',audit/'manifest-before.json')
    manifest=json.loads((host/'backend-runtime.json').read_text('utf8')); manifest['moduleCount']+=len(new_modules)
    for relative in hashes: manifest['files'][relative]=base.digest(payload/relative)
    base.write(payload/'backend-runtime.json',manifest)
    static=audit/'static'; static.mkdir(exist_ok=True)
    shutil.copytree(host/'_internal/assets',static/'assets',dirs_exist_ok=True)
    shutil.copytree(host/'_internal/scripts',static/'scripts',dirs_exist_ok=True)
    for path in (host/'_internal').glob('*.html'): shutil.copyfile(path,static/path.name)
    for name in assets+new_assets:
        target=static/name; target.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(internal/name,target)
    (static/'tests').mkdir(exist_ok=True)
    for name in node_tests: shutil.copyfile(repo/'tests'/name,static/'tests'/name)
    # These fixture suites use cwd as resource root. Every referenced local file
    # comes from the merged installed candidate, not the development HTML.
    base.write(audit/'prepared.json',{'baseline':baseline,'oldHashes':hashes,'protected':base.protected(),
                                    'generatorSha256':base.digest(candidate),'realProviderRequests':0})
    print(json.dumps({'prepared':True,'changedFiles':len(hashes),'newModules':len(new_modules),'idle':base.idle()}))


def test():
    manifest_sha=base.digest(payload/'backend-runtime.json')
    sys.path[:0]=[str(payload/'_internal'),str(host/'_internal')]
    stdlib=Path.home()/'AppData/Local/Programs/Python/Python314/Lib'; sys.path.append(str(stdlib))
    import unittest
    unittest.__path__.append(str(stdlib/'unittest'))
    import server,story1245_runtime
    server.ROOT=audit/'static'; server.PROMPTS_DIR=host/'_internal/prompts'; story1245_runtime.install(server)
    import os
    os.environ['PATH']=str(host/'_internal')+os.pathsep+os.environ.get('PATH','')
    suites=[]
    for name in python_tests:
        spec=importlib.util.spec_from_file_location(name,repo/'tests'/(name+'.py'))
        module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        suites.append(unittest.defaultTestLoader.loadTestsFromModule(module))
    result=unittest.TextTestRunner(verbosity=1).run(unittest.TestSuite(suites))
    assert manifest_sha==base.digest(payload/'backend-runtime.json'), 'Candidate changed during acceptance'
    base.write(audit/'tested.json',{'testsRun':result.testsRun,'success':result.wasSuccessful(),'manifestSha256':manifest_sha,'realProviderRequests':0})
    raise SystemExit(not result.wasSuccessful())


def restage():
    assert not (audit/'installed.json').exists(),'Already installed'
    history=audit/('attempt-'+str(__import__('time').time_ns())); history.mkdir()
    for name in ['prepared.json','tested.json','candidate-node-results.json','candidate-entry-results.json']:
        if (audit/name).exists(): (audit/name).replace(history/name)
    prepare()


def require_gate(name):
    result=json.loads((audit/name).read_text('utf8'))
    assert result.get('success'), 'Candidate gate failed: '+name
    assert result.get('manifestSha256')==base.digest(payload/'backend-runtime.json'), 'Candidate gate stale: '+name


def apply():
    assert json.loads((audit/'source-python-results.json').read_text('utf8'))['success'], 'Offline source acceptance failed'
    for name in ['tested.json','candidate-node-results.json','candidate-entry-results.json']:require_gate(name)
    manifest=json.loads((payload/'backend-runtime.json').read_text('utf8'))
    for relative in json.loads((audit/'prepared.json').read_text('utf8'))['oldHashes']:
        assert base.digest(payload/relative)==manifest['files'][relative], 'Payload changed after manifest: '+relative
    assert json.loads((audit/'prepared.json').read_text('utf8'))['generatorSha256']==base.digest(payload/'_internal/draft-generator.exe')
    base.apply()


if __name__=='__main__':
    {'prepare':prepare,'restage':restage,'test':test,'apply':apply,'verify':base.verify_install}[sys.argv[1]]()
