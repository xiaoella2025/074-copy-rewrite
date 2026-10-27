"""Install the 074 RH engine labels and adjacent workflow selector."""
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
audit = repo / '.desktop-tools/rh-engine-choices-20261027'
source = repo / 'assets/workflow_actions.js'
target = host / '_internal/assets/workflow_actions.js'
manifest_path = host / 'backend-runtime.json'
relative = '_internal/assets/workflow_actions.js'


def install():
    assert not audit.exists(), 'This fix is already installed'
    baseline = guard.verify(host)
    before = guard.protected()
    assert guard.digest(target) == '0bbf49ee0e2ce6a630ec2951c4767cb0855891fe35b10040f432daf66a50e19f', 'Installed asset drift'
    assert guard.digest(source) == '1e854cff1604f7f1b6ca0be46a3d2e92fa6d9c9788dc81e4439966ee8783ce0a', 'Source asset drift'
    manifest = json.loads(manifest_path.read_text('utf8'))
    assert manifest['files'][relative] == guard.digest(target)
    manifest['files'][relative] = guard.digest(source)
    audit.mkdir(parents=True)
    shutil.copy2(target, audit / 'workflow_actions.before.js')
    shutil.copy2(manifest_path, audit / 'backend-runtime.before.json')
    candidate = audit / 'backend-runtime.candidate.json'
    guard.write(candidate, manifest)
    assert guard.digest(manifest_path) == baseline['manifestSha256'], 'Runtime changed during preparation'
    tmp_asset = target.with_name(target.name + '.choices-tmp')
    tmp_manifest = manifest_path.with_name('backend-runtime.choices-tmp.json')
    try:
        shutil.copy2(source, tmp_asset)
        tmp_asset.replace(target)
        shutil.copy2(candidate, tmp_manifest)
        tmp_manifest.replace(manifest_path)
        result = guard.verify(host)
        assert guard.protected() == before, 'Business data changed'
    except BaseException:
        shutil.copy2(audit / 'workflow_actions.before.js', target)
        shutil.copy2(audit / 'backend-runtime.before.json', manifest_path)
        tmp_asset.unlink(missing_ok=True)
        tmp_manifest.unlink(missing_ok=True)
        guard.verify(host)
        raise
    guard.write(audit / 'installed.json', {'runtime': result, 'oldFileSha256': guard.digest(audit / 'workflow_actions.before.js'), 'newFileSha256': guard.digest(target), 'protectedFiles': len(before), 'providerRequests': 0})
    print(json.dumps({'installed': True, 'filesVerified': result['filesChecked'], 'protectedFiles': len(before), 'providerRequests': 0}, ensure_ascii=False))


if __name__ == '__main__':
    install()
