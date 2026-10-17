"""Guarded 07 deployment. No provider calls or production jobs in acceptance."""
import difflib
import ast
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
host=Path.home()/'AppData/Local/074 创作工作台/app074-backend'
data=Path.home()/'AppData/Local/com.app074.desktop/data'
audit=repo/'.desktop-tools/benchmark-batch-recovery-20261017'
payload=audit/'payload'
sys.path.insert(0,str(repo/'scripts'))
from backend_runtime_manifest import digest,verify


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n','utf8')


def signature(code):
    return (code.co_code,code.co_names,code.co_varnames,code.co_freevars,code.co_cellvars,
        code.co_argcount,code.co_kwonlyargcount,code.co_flags,
        tuple(signature(x) if isinstance(x,types.CodeType) else x for x in code.co_consts))


def protected():
    paths=[data/name for name in ['settings.json','profiles.json','task-queue.json','tasks.json','benchmark.json']]
    for pattern in ['*/client_config.json','*/request.json','*/05-tts-segments.json','*/05-captions.json','*/creative.json','*/song.mp3','*/output.mp4']:
        paths+=list((data/'tasks').glob(pattern))
    paths+=list((data/'benchmark').rglob('*.sqlite'))
    return {str(path):digest(path) for path in paths if path.is_file()}


def idle():
    queue=data/'task-queue.json'
    if queue.exists():
        value=json.loads(queue.read_text('utf8'))
        if any(x.get('status') in ('running','queued','pausing','cancelling') for x in value.get('jobs',[])):return False
    for path in (data/'benchmark/batch-jobs').glob('*.json'):
        if json.loads(path.read_text('utf8')).get('status') in ('running','queued','stopping'):return False
    return True


def prepare():
    assert not (audit/'prepared.json').exists(),'Already prepared; do not overwrite audit baseline'
    baseline=verify(host);before=audit/'source-before';header=importlib.util.MAGIC_NUMBER+struct.pack('<III',0,0,0)
    allowed={'benchmark':{'transcribe','ai_action'},'benchmark_ai_receipts':{'reserve','UnconfirmedReceiptError'},'story1245_runtime':{'install'},
             'task_queue':{'TaskQueue'},'task_cover':{'initial'}}
    for module,expected in allowed.items():
        relative='_internal/'+module+'.pyc';original=marshal.loads((host/relative).read_bytes()[16:])
        prior=compile((before/(module+'.py')).read_text('utf8'),'<baseline>','exec')
        assert signature(original)==signature(prior),'Unrelated installed drift: '+module
        code=compile((repo/(module+'.py')).read_text('utf8'),str(host/relative),'exec')
        old={c.co_name:c for c in prior.co_consts if isinstance(c,types.CodeType)}
        new={c.co_name:c for c in code.co_consts if isinstance(c,types.CodeType)}
        changed={name for name in old.keys()|new.keys() if name not in old or name not in new or signature(old[name])!=signature(new[name])}
        if module=='task_queue' and 'dispatch' in changed:
            # Python 3.14 embeds a nested class's __firstlineno__ in constants.
            # A preceding method edit shifts it without changing dispatch logic.
            def node(path):return next(x for x in ast.parse(path.read_text('utf8')).body if isinstance(x,ast.FunctionDef) and x.name=='dispatch')
            assert ast.dump(node(before/(module+'.py')))==ast.dump(node(repo/(module+'.py'))),'Unexpected dispatch behavior change'
            changed.remove('dispatch')
        assert changed==expected,'Unexpected source changes: '+module+str(changed)
        target=payload/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(header+marshal.dumps(code))
    for module in ['benchmark_batch_actions','benchmark_batch_jobs','benchmark_batch_http']:
        relative='_internal/'+module+'.pyc';assert not (host/relative).exists(),'Module already exists'
        (payload/relative).write_bytes(header+marshal.dumps(compile((repo/(module+'.py')).read_text('utf8'),str(host/relative),'exec')))
    for name in ['assets/benchmark.js','assets/benchmark_batch.js']:
        assert digest(host/'_internal'/name)==digest(before/name),'Unrelated installed UI drift'
        target=payload/'_internal'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(repo/name,target)
    # This existing asset has unrelated source/installed drift. Apply only our
    # captured-baseline hunks, with unique context, to installed bytes.
    name='assets/workflow_view.js';old=(before/name).read_text('utf8').splitlines(True);new=(repo/name).read_text('utf8').splitlines(True)
    installed=(host/'_internal'/name).read_text('utf8')
    for group in difflib.SequenceMatcher(a=old,b=new).get_grouped_opcodes(2):
        a=''.join(old[group[0][1]:group[-1][2]]);b=''.join(new[group[0][3]:group[-1][4]])
        assert installed.count(a)==1,'Workflow summary context changed'
        installed=installed.replace(a,b,1)
    (payload/'_internal'/name).write_text(installed,'utf8')
    old_hashes={}
    for path in payload.rglob('*'):
        if not path.is_file() or path==payload/'backend-runtime.json':continue
        relative=path.relative_to(payload).as_posix();original=host/relative
        old_hashes[relative]=digest(original) if original.is_file() else None
        if original.is_file():
            backup=audit/'before'/relative;backup.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(original,backup)
    shutil.copyfile(host/'backend-runtime.json',audit/'manifest-before.json')
    manifest=json.loads((host/'backend-runtime.json').read_text('utf8'))
    for path in payload.rglob('*'):
        if path.is_file() and path!=payload/'backend-runtime.json':manifest['files'][path.relative_to(payload).as_posix()]=digest(path)
    manifest['moduleCount']+=3;write(payload/'backend-runtime.json',manifest)
    # Capture only changes made since this execution began in dirty old modules.
    deltas={}
    for path in before.rglob('*'):
        if not path.is_file():continue
        relative=path.relative_to(before).as_posix();current=repo/relative
        delta=''.join(difflib.unified_diff(path.read_text('utf8').splitlines(True),current.read_text('utf8').splitlines(True),fromfile='before/'+relative,tofile=relative))
        output=audit/'source-deltas'/(relative+'.diff');output.parent.mkdir(parents=True,exist_ok=True);output.write_text(delta,'utf8')
        deltas[relative]={'before':digest(path),'after':digest(current)}
    static=audit/'static';static.mkdir(parents=True,exist_ok=True)
    for path in (host/'_internal').glob('*.html'):shutil.copyfile(path,static/path.name)
    shutil.copytree(host/'_internal/assets',static/'assets',dirs_exist_ok=True)
    for name in ['assets/benchmark.js','assets/benchmark_batch.js','assets/workflow_view.js']:shutil.copyfile(payload/'_internal'/name,static/name)
    write(audit/'prepared.json',{'baseline':baseline,'protected':protected(),'oldHashes':old_hashes,'sourceDeltas':deltas,'providerRequests':0})
    print(json.dumps({'prepared':True,'newModules':3,'files':len(old_hashes)}))


def test():
    sys.path[:0]=[str(payload/'_internal'),str(host/'_internal')]
    stdlib=Path.home()/'AppData/Local/Programs/Python/Python314/Lib';sys.path.append(str(stdlib))
    import unittest
    unittest.__path__.append(str(stdlib/'unittest'))
    import server,story1245_runtime
    story1245_runtime.install(server);server.ROOT=host/'_internal';server.PROMPTS_DIR=server.ROOT/'prompts'
    os.environ['PATH']=str(host/'_internal')+os.pathsep+os.environ.get('PATH','')
    names=['test_queue_cover_completion','test_task_pause','test_cover_workflow_resume','test_cover_provider_resume',
        'test_benchmark_asr_race','test_benchmark_batch_jobs','test_benchmark_batch_http','test_benchmark_promo_receipts',
        'test_benchmark_backup','test_benchmark_auto_backup','test_benchmark_video','test_benchmark','test_task_queue',
        'test_runtime_updates1245','test_connected_modules_http','test_subtitle_alignment1245','test_volc_v3_1245',
        'test_workbench_protocol1245','test_workbench_stream','test_llm_credentials1245','test_tts','test_task_cover',
        'test_captions_export','test_saved_llm_failure','test_llm_response','test_metadata_response','test_draft_text_parity']
    suites=[]
    for name in names:
        spec=importlib.util.spec_from_file_location(name,repo/'tests'/(name+'.py'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        if name=='test_draft_text_parity':module.ROOT=host/'_internal'
        suites.append(unittest.defaultTestLoader.loadTestsFromModule(module))
    result=unittest.TextTestRunner(verbosity=1).run(unittest.TestSuite(suites))
    write(audit/'tested.json',{'testsRun':result.testsRun,'skipped':len(result.skipped),'success':result.wasSuccessful(),'providerRequests':0})
    raise SystemExit(not result.wasSuccessful())


def restage():
    assert not (audit/'installed.json').exists(),'Already installed'
    history=audit/('attempt-'+str(__import__('time').time_ns()));history.mkdir()
    for name in ['prepared.json','tested.json']:
        path=audit/name
        if path.exists():path.replace(history/name)
    prepare()


def apply():
    assert json.loads((audit/'tested.json').read_text('utf8'))['success'],'Acceptance failed'
    saved=json.loads((audit/'prepared.json').read_text('utf8'))
    assert digest(host/'backend-runtime.json')==digest(audit/'manifest-before.json'),'Runtime changed'
    for relative,sha in saved['oldHashes'].items():
        original=host/relative;assert (digest(original) if original.is_file() else None)==sha,'Installed drift: '+relative
    # Native app must have been closed normally before apply.
    import subprocess
    command="@(Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'app074-desktop.exe' }).Count"
    count=subprocess.check_output(['powershell','-NoProfile','-Command',command],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),text=True)
    assert count.strip()=='0','Close 074 normally before installation'
    command="@(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like '*desktop_backend.pyc*' -and $_.CommandLine -like '*com.app074.desktop*' }).Count"
    count=subprocess.check_output(['powershell','-NoProfile','-Command',command],creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),text=True)
    assert count.strip()=='0','Production backend is still running; preserve active operations'
    # A closed app may leave stale running/queued records. Preserve those bytes;
    # queue startup will mark the interrupted current task and wait for the user.
    before=protected()
    for path in payload.rglob('*'):
        if path.is_file() and path.name!='backend-runtime.json':
            target=host/path.relative_to(payload);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
    shutil.copyfile(payload/'backend-runtime.json',host/'backend-runtime.json')
    result=verify(host);assert before==protected(),'Business data changed'
    write(audit/'installed.json',{'runtime':result,'protected':before,'businessFilesChanged':0,'providerRequests':0})
    print(json.dumps({'installed':True,'filesVerified':result['filesChecked'],'protectedFiles':len(before),'businessFilesChanged':0}))


def verify_install():
    result=verify(host);saved=json.loads((audit/'installed.json').read_text('utf8'))
    assert saved['protected']==protected(),'Protected data differs since apply'
    write(audit/'verified.json',{'runtime':result,'protectedFiles':len(saved['protected']),'businessFilesChanged':0,'providerRequests':0})
    print(json.dumps({'verified':True,'filesVerified':result['filesChecked'],'protectedFiles':len(saved['protected'])}))


if __name__=='__main__':{'prepare':prepare,'restage':restage,'test':test,'apply':apply,'verify':verify_install}[sys.argv[1]]()
