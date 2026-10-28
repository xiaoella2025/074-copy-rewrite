"""Install resilient settings initialization; no generation or data edits."""
import importlib.util
import json
from pathlib import Path
import shutil
import sys

sys.dont_write_bytecode=True
repo=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('guard',repo/'scripts/deploy-benchmark-batch-recovery.py')
guard=importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
host=guard.host
source=repo/'settings.html'
relative='_internal/settings.html'
target=host/relative
manifest_path=host/'backend-runtime.json'
audit=repo/'.desktop-tools/settings-image-loading-20261028'


def install():
    assert not audit.exists(),'Recovery controls already installed'
    baseline=guard.verify(host)
    protected=guard.protected()
    assert guard.digest(target)=='8cd8c7959ac0f3f33a0ece34771f969c4735138f4f94ff45ed26452129dc63ea','Installed asset drift'
    assert guard.digest(source)=='ef3c9d816c072a5fb4a4245af14a7e63b5835952d7d41ce6205080e19658c657','Source asset drift'
    manifest=json.loads(manifest_path.read_text('utf8'))
    assert manifest['files'][relative]==guard.digest(target)
    manifest['files'][relative]=guard.digest(source)
    audit.mkdir(parents=True)
    shutil.copy2(target,audit/'settings.before.html')
    shutil.copy2(manifest_path,audit/'backend-runtime.before.json')
    candidate=audit/'backend-runtime.candidate.json'
    guard.write(candidate,manifest)
    assert guard.digest(manifest_path)==baseline['manifestSha256'],'Runtime changed during preparation'
    temporary=target.with_name(target.name+'.recovery-tmp')
    manifest_temp=manifest_path.with_name('backend-runtime.recovery-tmp.json')
    try:
        shutil.copy2(source,temporary);temporary.replace(target)
        shutil.copy2(candidate,manifest_temp);manifest_temp.replace(manifest_path)
        result=guard.verify(host)
        assert guard.protected()==protected,'Business data changed'
    except BaseException:
        shutil.copy2(audit/'settings.before.html',target)
        shutil.copy2(audit/'backend-runtime.before.json',manifest_path)
        temporary.unlink(missing_ok=True);manifest_temp.unlink(missing_ok=True)
        guard.verify(host)
        raise
    guard.write(audit/'installed.json',{'runtime':result,'protectedFilesUnchanged':len(protected),'providerRequests':0})
    print(json.dumps({'installed':True,'filesVerified':result['filesChecked'],'protectedFilesUnchanged':len(protected),'providerRequests':0}))


if __name__=='__main__':install()
