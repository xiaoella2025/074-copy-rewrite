"""Install only the RH workflow preflight diagnostics into the guarded 074 runtime."""
import importlib.util
import json
import marshal
from pathlib import Path
import shutil
import struct
import sys
import types

sys.dont_write_bytecode = True
repo = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('deployment_guard', repo / 'scripts/deploy-benchmark-batch-recovery.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
host = guard.host
audit = repo / '.desktop-tools/rh-workflow-preflight-20261027'
manifest_path = host / 'backend-runtime.json'
changes = {
    'rh_workflow_provider': (
        'generate',
        """        if not (cfg.get('enabled') and cfg.get('api_key') and cfg.get('member_key_confirmed') and cfg.get('web_tested') and cfg.get('checked')):
            raise ValueError('请先在系统设置启用并核对RH币工作流及会员Key')
""",
        """        if not (cfg.get('enabled') and cfg.get('api_key') and cfg.get('member_key_confirmed')):
            raise ValueError('RH币工作流配置未完成：请在系统设置启用并核对会员Key；未提交生成')
        if not cfg.get('checked'):
            raise ValueError('RH币工作流完整图未核对：请核对所选候选的完整工作流；未提交生成')
        if not cfg.get('web_tested'):
            raise ValueError('RH币工作流尚未网页实测：请在同一账户网页运行所选工作流并确认出图；未提交生成')
""",
    ),
    'task_cover': (
        'cover_error',
        "    text=str(error)\n",
        """    text=str(error)
    if text.startswith('RH币工作流完整图未核对：'):
        return {'kind':'workflow_preflight','title':'所选 RH 币工作流尚未核对完整图',
                'body':'到系统设置核对这条候选工作流后再试；本次未提交生成，也没有产生 RH 任务编号。'}
    if text.startswith('RH币工作流尚未网页实测：'):
        return {'kind':'workflow_preflight','title':'所选 RH 币工作流尚未网页实测',
                'body':'请在同一账户网页运行这条工作流并确认出图，再到系统设置勾选网页实测；本次未提交生成，也没有产生 RH 任务编号。'}
    if text.startswith('RH币工作流配置未完成：'):
        return {'kind':'workflow_preflight','title':'RH 币工作流配置未完成',
                'body':'请到系统设置检查会员 Key 与工作流开关；本次未提交生成，也没有产生 RH 任务编号。'}
""",
    ),
}


def function(code, name):
    return next(item for item in code.co_consts if isinstance(item, types.CodeType) and item.co_name == name)


def replace_function(code, name, replacement):
    return code.replace(co_consts=tuple(replacement if isinstance(item, types.CodeType) and item.co_name == name else item for item in code.co_consts))


def install():
    assert not (audit / 'installed.json').exists(), 'Already installed'
    baseline = guard.verify(host)
    protected = guard.protected()
    target_task = guard.data / 'tasks/task_1793005392679_c94d41c60971'
    protected.update({str(path):guard.digest(path) for path in target_task.glob('*.json') if path.is_file()})
    audit.mkdir(parents=True, exist_ok=False)
    payload = audit / 'payload'
    header = importlib.util.MAGIC_NUMBER + struct.pack('<III', 0, 0, 0)
    old_hashes = {}
    for module, (name, before, after) in changes.items():
        source = (repo / (module + '.py')).read_text('utf8')
        assert source.count(after) == 1, 'Source changed: ' + module
        previous = source.replace(after, before, 1)
        original = host / '_internal' / (module + '.pyc')
        installed = marshal.loads(original.read_bytes()[16:])
        prior = compile(previous, '<baseline>', 'exec')
        current = compile(source, str(original), 'exec')
        assert guard.signature(function(installed, name)) == guard.signature(function(prior, name)), 'Installed function drift: ' + module
        updated = replace_function(installed, name, function(current, name))
        relative = original.relative_to(host)
        destination = payload / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(header + marshal.dumps(updated))
        old_hashes[relative.as_posix()] = guard.digest(original)
        backup = audit / 'before' / relative
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, backup)
    shutil.copy2(manifest_path, audit / 'backend-runtime.before.json')
    manifest = json.loads(manifest_path.read_text('utf8'))
    for relative in old_hashes:
        assert manifest['files'][relative] == old_hashes[relative]
        manifest['files'][relative] = guard.digest(payload / relative)
    candidate = audit / 'backend-runtime.candidate.json'
    guard.write(candidate, manifest)
    assert guard.digest(manifest_path) == baseline['manifestSha256'], 'Runtime changed during preparation'
    try:
        for relative, old_hash in old_hashes.items():
            assert guard.digest(host / relative) == old_hash, 'Installed file changed: ' + relative
            shutil.copy2(payload / relative, host / relative)
        shutil.copy2(candidate, manifest_path)
        result = guard.verify(host)
        assert all(path.is_file() and guard.digest(path) == expected for name, expected in protected.items() if (path := Path(name))), 'Business data changed'
    except BaseException:
        for relative in old_hashes:
            shutil.copy2(audit / 'before' / relative, host / relative)
        shutil.copy2(audit / 'backend-runtime.before.json', manifest_path)
        guard.verify(host)
        raise
    guard.write(audit / 'installed.json', {'runtime': result, 'oldHashes': old_hashes, 'protectedFiles': len(protected), 'realProviderRequests': 0})
    print(json.dumps({'installed': True, 'filesVerified': result['filesChecked'], 'protectedFiles': len(protected), 'realProviderRequests': 0}))


if __name__ == '__main__':
    install()
