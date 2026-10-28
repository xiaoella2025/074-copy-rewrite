"""Install only lab worker/UI changes, with hashes and business-data guards."""
import importlib.util
import json
import marshal
from pathlib import Path
import shutil
import struct
import sys

sys.dont_write_bytecode=True
repo=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('guard',repo/'scripts/deploy-benchmark-batch-recovery.py')
guard=importlib.util.module_from_spec(spec);spec.loader.exec_module(guard)
host=guard.host
audit=repo/'.desktop-tools/image-lab-background-20261028'
old={'_internal/image_lab.pyc':'9ca037bb6063f50d015b8a8e6beb4d32249fd40df82977256981685d9dd40f3f',
     '_internal/assets/image_lab.js':'d9c14fa3d16d39c3ab301ad55ffa1c76de4b8ec91ec130782f447502ce41eb57',
     '_internal/image_lab_jobs.pyc':None}


def install():
    assert not (audit/'installed.json').exists(),'Already installed'
    baseline=guard.verify(host);protected=guard.protected()
    manifest_path=host/'backend-runtime.json'
    manifest=json.loads(manifest_path.read_text('utf8'))
    payload={}
    for relative,expected in old.items():
        target=host/relative
        assert (guard.digest(target) if target.exists() else None)==expected,'Runtime drift: '+relative
        source=repo/(relative.removeprefix('_internal/').removesuffix('c') if relative.endswith('.pyc') else relative.removeprefix('_internal/'))
        payload[relative]=(importlib.util.MAGIC_NUMBER+struct.pack('<III',0,0,0)+marshal.dumps(compile(source.read_text('utf8'),str(target),'exec')) if relative.endswith('.pyc') else source.read_bytes())
        if target.exists():
            backup=audit/'before'/relative;backup.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(target,backup)
    shutil.copy2(manifest_path,audit/'manifest-before.json')
    assert guard.digest(manifest_path)==baseline['manifestSha256']
    try:
        for relative,content in payload.items():
            target=host/relative;temporary=target.with_name(target.name+'.lab-tmp')
            temporary.write_bytes(content);temporary.replace(target)
            manifest['files'][relative]=guard.digest(target)
        manifest['moduleCount']+=1
        temporary=manifest_path.with_name('backend-runtime.lab-tmp.json')
        guard.write(temporary,manifest);temporary.replace(manifest_path)
        verified=guard.verify(host)
        assert guard.protected()==protected,'Business data changed during installation'
    except BaseException:
        for relative,expected in old.items():
            if expected:shutil.copy2(audit/'before'/relative,host/relative)
            else:(host/relative).unlink(missing_ok=True)
        shutil.copy2(audit/'manifest-before.json',manifest_path)
        raise
    guard.write(audit/'installed.json',{'runtime':verified,'protectedFilesUnchanged':len(protected),'providerRequests':0})
    print(json.dumps({'installed':True,'filesChecked':verified['filesChecked'],'protectedFilesUnchanged':len(protected),'providerRequests':0}))


if __name__=='__main__':install()
