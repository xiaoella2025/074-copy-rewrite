"""Install the verified 074 workflow selector visibility fix without touching task data."""
import importlib.util
import json
from pathlib import Path
import shutil
import sys

sys.dont_write_bytecode = True
repo = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('deployment_guard', repo / 'scripts/deploy-benchmark-batch-recovery.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
host = guard.host
audit = repo / '.desktop-tools/rh-workflow-visibility-20261026'
source = repo / 'assets/workflow_actions.js'
target = host / '_internal/assets/workflow_actions.js'
manifest_path = host / 'backend-runtime.json'
relative = '_internal/assets/workflow_actions.js'


def install():
    assert not (audit / 'installed.json').exists(), 'This fix is already installed'
    baseline = guard.verify(host)
    before = guard.protected()
    old = target.read_text('utf8')
    new = source.read_text('utf8')
    assert 'function rhWorkflowActive(' not in old, 'Unexpected installed selector code'
    assert 'function rhWorkflowActive(' in new and 'clearInactiveRhWorkflow' in new
    for marker in ['function _coverReplacementPlan(', 'const syncCoverReplacement=', 'if(stepKey===\'4\'&&nextCfg.image?.source===\'external\')']:
        assert old.count(marker) == new.count(marker) == 1, 'Installed source drift: ' + marker
    import difflib
    changes = [code for code, *_ in difflib.SequenceMatcher(a=old.splitlines(), b=new.splitlines()).get_opcodes() if code != 'equal']
    assert changes == ['insert', 'insert', 'insert'], 'Unexpected unrelated source changes: ' + str(changes)
    audit.mkdir(parents=True, exist_ok=False)
    shutil.copy2(target, audit / 'workflow_actions.before.js')
    shutil.copy2(manifest_path, audit / 'backend-runtime.before.json')
    manifest = json.loads(manifest_path.read_text('utf8'))
    assert manifest['files'][relative] == guard.digest(target)
    manifest['files'][relative] = guard.digest(source)
    candidate = audit / 'backend-runtime.candidate.json'
    guard.write(candidate, manifest)
    assert guard.digest(manifest_path) == baseline['manifestSha256'], 'Runtime changed during preparation'
    try:
        temporary = target.with_name(target.name + '.visibility-tmp')
        shutil.copy2(source, temporary)
        temporary.replace(target)
        manifest_temp = manifest_path.with_name('backend-runtime.visibility-tmp.json')
        shutil.copy2(candidate, manifest_temp)
        manifest_temp.replace(manifest_path)
        result = guard.verify(host)
        assert guard.protected() == before, 'Business data changed'
    except BaseException:
        shutil.copy2(audit / 'workflow_actions.before.js', target)
        shutil.copy2(audit / 'backend-runtime.before.json', manifest_path)
        for temporary in [target.with_name(target.name + '.visibility-tmp'), manifest_path.with_name('backend-runtime.visibility-tmp.json')]:
            temporary.unlink(missing_ok=True)
        guard.verify(host)
        raise
    guard.write(audit / 'installed.json', {'runtime': result, 'oldFileSha256': guard.digest(audit / 'workflow_actions.before.js'), 'newFileSha256': guard.digest(target), 'protectedFiles': len(before), 'realProviderRequests': 0})
    print(json.dumps({'installed': True, 'filesVerified': result['filesChecked'], 'protectedFiles': len(before), 'realProviderRequests': 0}, ensure_ascii=False))


if __name__ == '__main__':
    install()
