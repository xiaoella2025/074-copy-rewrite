"""Install always-visible cover recovery controls; no generation or data edits."""
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
source=repo/'assets/task_cover.js'
relative='_internal/assets/task_cover.js'
target=host/relative
manifest_path=host/'backend-runtime.json'
audit=repo/'.desktop-tools/cover-recovery-buttons-20261027'


def install():
    assert not audit.exists(),'Recovery controls already installed'
    baseline=guard.verify(host)
    protected=guard.protected()
    assert guard.digest(target)=='022cb007256b1825f0d169659af3152bcfcdcce8571f66bc135406f37806dd3b','Installed asset drift'
    assert guard.digest(source)=='80a1fb46ca1143e4dda22104f0c91bd1534c14b26425a040c0c6cb932d0b27c3','Source asset drift'
    manifest=json.loads(manifest_path.read_text('utf8'))
    assert manifest['files'][relative]==guard.digest(target)
    manifest['files'][relative]=guard.digest(source)
    audit.mkdir(parents=True)
    shutil.copy2(target,audit/'task_cover.before.js')
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
        shutil.copy2(audit/'task_cover.before.js',target)
        shutil.copy2(audit/'backend-runtime.before.json',manifest_path)
        temporary.unlink(missing_ok=True);manifest_temp.unlink(missing_ok=True)
        guard.verify(host)
        raise
    guard.write(audit/'installed.json',{'runtime':result,'protectedFilesUnchanged':len(protected),'providerRequests':0})
    print(json.dumps({'installed':True,'filesVerified':result['filesChecked'],'protectedFilesUnchanged':len(protected),'providerRequests':0}))


if __name__=='__main__':install()
