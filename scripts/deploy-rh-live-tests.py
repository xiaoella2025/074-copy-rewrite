"""Install verified RH API-test acceptance into the desktop backend and UI."""
import hashlib
import importlib.util
import json
import marshal
from pathlib import Path
import shutil
import struct
import subprocess
import sys

sys.dont_write_bytecode = True
repo = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('deployment_guard', repo / 'scripts/deploy-benchmark-batch-recovery.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
host = guard.host
audit = repo / '.desktop-tools/rh-four-live-tests-20261027/deployment'
modules = ('rh_coins_experiment', 'rh_workflow_catalog', 'rh_workflow_provider', 'task_cover')
assets = ('assets/rh_workflow_settings.js', 'assets/rh_coins_experiment.js')
paths = tuple('_internal/' + name + '.pyc' for name in modules) + tuple('_internal/' + name for name in assets)


def tracked_at_head(relative):
    return subprocess.check_output(['git', 'show', 'HEAD:' + relative], cwd=repo).decode('utf8')


def business_hashes():
    root = Path.home() / 'AppData/Local/com.app074.desktop/data/rh-coins-experiment'
    return {str(path): guard.digest(path) for path in root.rglob('*') if path.is_file()}


def install():
    assert not audit.exists(), 'Live-test integration is already installed'
    baseline = guard.verify(host)
    protected = guard.protected()
    business = business_hashes()
    payload = {}
    header = importlib.util.MAGIC_NUMBER + struct.pack('<III', 0, 0, 0)
    for name in modules:
        relative = '_internal/' + name + '.pyc'
        old = marshal.loads((host / relative).read_bytes()[16:])
        expected = compile(tracked_at_head(name + '.py'), str(host / relative), 'exec')
        assert guard.signature(old) == guard.signature(expected), 'Installed module drift: ' + name
        updated = compile((repo / (name + '.py')).read_text('utf8'), str(host / relative), 'exec')
        payload[relative] = header + marshal.dumps(updated)
    for name in assets:
        relative = '_internal/' + name
        assert (host / relative).read_text('utf8') == tracked_at_head(name), 'Installed asset drift: ' + name
        payload[relative] = (repo / name).read_bytes()
    manifest_path = host / 'backend-runtime.json'
    manifest = json.loads(manifest_path.read_text('utf8'))
    for relative, data in payload.items():
        assert manifest['files'][relative] == guard.digest(host / relative)
        manifest['files'][relative] = hashlib.sha256(data).hexdigest()
    audit.mkdir(parents=True)
    for relative in paths:
        target = audit / 'before' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(host / relative, target)
    shutil.copy2(manifest_path, audit / 'backend-runtime.before.json')
    candidate = audit / 'backend-runtime.candidate.json'
    guard.write(candidate, manifest)
    assert guard.digest(manifest_path) == baseline['manifestSha256'], 'Runtime changed during preparation'
    try:
        for relative, data in payload.items():
            target = host / relative
            temporary = target.with_name(target.name + '.rh-live-tmp')
            temporary.write_bytes(data)
            temporary.replace(target)
        temporary = manifest_path.with_name('backend-runtime.rh-live-tmp.json')
        shutil.copy2(candidate, temporary)
        temporary.replace(manifest_path)
        result = guard.verify(host)
        assert guard.protected() == protected and business_hashes() == business, 'Business data changed during code install'
    except BaseException:
        for relative in paths:
            shutil.copy2(audit / 'before' / relative, host / relative)
            (host / relative).with_name(Path(relative).name + '.rh-live-tmp').unlink(missing_ok=True)
        shutil.copy2(audit / 'backend-runtime.before.json', manifest_path)
        manifest_path.with_name('backend-runtime.rh-live-tmp.json').unlink(missing_ok=True)
        guard.verify(host)
        raise
    guard.write(audit / 'installed.json', {'runtime': result, 'files': list(payload), 'businessFilesUnchanged': len(business),
                                           'protectedFilesUnchanged': len(protected), 'providerRequests': 0})
    print(json.dumps({'installed': True, 'filesVerified': result['filesChecked'], 'businessFilesUnchanged': len(business),
                      'protectedFilesUnchanged': len(protected), 'providerRequests': 0}, ensure_ascii=False))


if __name__ == '__main__':
    install()
