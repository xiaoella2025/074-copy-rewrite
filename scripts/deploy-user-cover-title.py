"""Patch only title selection functions; preserve other installed runtime changes."""
import difflib
import importlib.util
import json
import marshal
from pathlib import Path
import shutil
import struct
import sys
sys.dont_write_bytecode = True
repo = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('previous_deploy', repo / 'scripts/deploy-image-auto-retry.py')
prior = importlib.util.module_from_spec(spec); spec.loader.exec_module(prior)
base = prior.base
base.audit = repo / '.desktop-tools/user-title-priority-20261019/story-aligned-final'
base.payload = base.audit / 'payload'
audit, payload, host = base.audit, base.payload, base.host
SUITES = ['test_user_cover_title', 'test_task_cover', 'test_cover_settings1245',
          'test_cover_title1250', 'test_culture_titles', 'test_metadata_response', 'test_llm_response']


def prepare():
    assert not (audit / 'prepared.json').exists(), 'Already prepared'
    baseline = base.verify(host)
    header = importlib.util.MAGIC_NUMBER + struct.pack('<III', 0, 0, 0)
    hashes = {}
    delta = ''
    for module, names in [('server', ['step1_meta']), ('task_cover', ['view', '_action'])]:
        relative = '_internal/' + module + '.pyc'
        old_source = audit.parent / 'story-aligned-final-baseline' / (module + '.py')
        old = compile(old_source.read_text('utf8'), '<before>', 'exec')
        installed = marshal.loads((host / relative).read_bytes()[16:])
        new = compile((repo / (module + '.py')).read_text('utf8'), str(host / relative), 'exec')
        patched = installed
        for name in names:
            target = (name,)
            actual = base.signature(prior.nested(installed, target))
            assert actual == base.signature(prior.nested(old, target)), 'Installed function drift: ' + module + '.' + name
            patched = prior.replace(patched, target, prior.nested(new, target))
        out = payload / relative; out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(header + marshal.dumps(patched))
        backup = audit / 'before' / relative; backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(host / relative, backup)
        hashes[relative] = base.digest(host / relative)
        delta += ''.join(difflib.unified_diff(old_source.read_text('utf8').splitlines(True),
            (repo / (module + '.py')).read_text('utf8').splitlines(True), fromfile='before/' + module + '.py', tofile=module + '.py'))
    (audit / 'source-deltas.patch').write_text(delta, 'utf8')
    shutil.copyfile(host / 'backend-runtime.json', audit / 'manifest-before.json')
    manifest = json.loads((host / 'backend-runtime.json').read_text('utf8'))
    for relative in hashes: manifest['files'][relative] = base.digest(payload / relative)
    base.write(payload / 'backend-runtime.json', manifest)
    base.write(audit / 'prepared.json', {'baseline': baseline, 'oldHashes': hashes, 'protected': base.protected(), 'realProviderRequests': 0})
    print(json.dumps({'prepared': True, 'changedFiles': len(hashes)}))


def test():
    installed = sys.argv[-1] == 'installed'
    sys.path[:0] = ([str(host / '_internal')] if installed else [str(payload / '_internal'), str(host / '_internal')])
    stdlib = Path.home() / 'AppData/Local/Programs/Python/Python314/Lib'; sys.path.append(str(stdlib))
    import unittest
    unittest.__path__.append(str(stdlib / 'unittest'))
    import server, story1245_runtime
    server.ROOT = host / '_internal'; server.PROMPTS_DIR = server.ROOT / 'prompts'; story1245_runtime.install(server)
    suites = []
    for name in SUITES:
        spec = importlib.util.spec_from_file_location(name, repo / 'tests' / (name + '.py'))
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        suites.append(unittest.defaultTestLoader.loadTestsFromModule(module))
    result = unittest.TextTestRunner(verbosity=1).run(unittest.TestSuite(suites))
    base.write(audit / ('installed-tested.json' if installed else 'tested.json'),
               {'testsRun': result.testsRun, 'success': result.wasSuccessful(), 'realProviderRequests': 0})
    raise SystemExit(not result.wasSuccessful())


if __name__ == '__main__':
    {'prepare': prepare, 'test': test, 'apply': base.apply, 'verify': base.verify_install}[sys.argv[1]]()
