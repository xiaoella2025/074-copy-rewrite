"""Install the culture title policy without replacing unrelated runtime changes."""
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
base.audit = repo / '.desktop-tools/culture-titles-20261019'
base.payload = base.audit / 'payload'
audit, payload, host = base.audit, base.payload, base.host


def prepare():
    assert not (audit / 'prepared.json').exists(), 'Already prepared'
    baseline = base.verify(host); before = audit / 'source-before'
    internal = payload / '_internal'; (internal / 'assets').mkdir(parents=True, exist_ok=True)
    header = importlib.util.MAGIC_NUMBER + struct.pack('<III', 0, 0, 0)
    old = compile((before / 'server.py').read_text('utf8'), '<before>', 'exec')
    installed = marshal.loads((host / '_internal/server.pyc').read_bytes()[16:])
    new = compile((repo / 'server.py').read_text('utf8'), str(host / '_internal/server.pyc'), 'exec')
    target = ('step1_meta',)
    assert base.signature(prior.nested(old, target)) == base.signature(prior.nested(installed, target)), 'Metadata function drift'
    installed = prior.replace(installed, target, prior.nested(new, target))
    (internal / 'server.pyc').write_bytes(header + marshal.dumps(installed))
    assert not (host / '_internal/culture_titles.pyc').exists(), 'Already installed'
    (internal / 'culture_titles.pyc').write_bytes(header + marshal.dumps(compile((repo / 'culture_titles.py').read_text('utf8'), str(host / '_internal/culture_titles.pyc'), 'exec')))
    name = 'assets/prompt_templates.json'
    a = json.loads((before / name).read_text('utf8')); b = json.loads((repo / name).read_text('utf8'))
    old_template = next(t for t in a if t['id'] == 'culture-knowledge')
    new_template = next(t for t in b if t['id'] == 'culture-knowledge')
    # Only one field of one template can change.
    check = json.loads(json.dumps(b)); next(t for t in check if t['id'] == 'culture-knowledge')['step1MetadataSystemPrompt'] = old_template['step1MetadataSystemPrompt']
    assert check == a
    live = json.loads((host / '_internal' / name).read_text('utf8'))
    selected = next(t for t in live if t['id'] == 'culture-knowledge')
    assert selected['step1MetadataSystemPrompt'] == old_template['step1MetadataSystemPrompt'], 'Installed culture template drift'
    selected['step1MetadataSystemPrompt'] = new_template['step1MetadataSystemPrompt']
    base.write(internal / name, live)
    name = 'assets/prompt_templates.provenance.json'
    live = json.loads((host / '_internal' / name).read_text('utf8'))
    addition = json.loads((repo / name).read_text('utf8'))['localCustomizations'][-1]
    live.setdefault('localCustomizations', []).append(addition); base.write(internal / name, live)
    hashes = {}
    for p in payload.rglob('*'):
        if not p.is_file() or p.name == 'backend-runtime.json': continue
        relative = p.relative_to(payload).as_posix(); original = host / relative
        hashes[relative] = base.digest(original) if original.exists() else None
        if original.exists():
            target = audit / 'before' / relative; target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(original, target)
    shutil.copyfile(host / 'backend-runtime.json', audit / 'manifest-before.json')
    manifest = json.loads((host / 'backend-runtime.json').read_text('utf8')); manifest['moduleCount'] += 1
    for relative in hashes: manifest['files'][relative] = base.digest(payload / relative)
    base.write(payload / 'backend-runtime.json', manifest)
    delta = ''
    for name in ['server.py', 'assets/prompt_templates.json', 'assets/prompt_templates.provenance.json']:
        delta += ''.join(difflib.unified_diff((before / name).read_text('utf8').splitlines(True), (repo / name).read_text('utf8').splitlines(True), fromfile='before/' + name, tofile=name, n=0))
    (audit / 'source-deltas.patch').write_text(delta, 'utf8')
    static = audit / 'static'; static.mkdir(exist_ok=True)
    shutil.copytree(host / '_internal/assets', static / 'assets', dirs_exist_ok=True)
    for name in ['assets/prompt_templates.json', 'assets/prompt_templates.provenance.json']: shutil.copyfile(internal / name, static / name)
    base.write(audit / 'prepared.json', {'baseline': baseline, 'oldHashes': hashes, 'protected': base.protected(), 'realProviderRequests': 0})
    print(json.dumps({'prepared': True, 'changedFiles': len(hashes)}))


def test():
    sys.path[:0] = [str(payload / '_internal'), str(host / '_internal')]
    stdlib = Path.home() / 'AppData/Local/Programs/Python/Python314/Lib'; sys.path.append(str(stdlib))
    import unittest
    unittest.__path__.append(str(stdlib / 'unittest'))
    import server, story1245_runtime
    server.ROOT = audit / 'static'; server.PROMPTS_DIR = host / '_internal/prompts'; story1245_runtime.install(server)
    suites = []
    for name in ['test_culture_titles', 'test_metadata_response', 'test_template_library', 'test_llm_response',
                 'test_saved_llm_failure', 'test_cover_settings1245', 'test_cover_provider_resume', 'test_cover_workflow_resume', 'test_image_auto_retry']:
        path = repo / 'tests' / (name + '.py'); assert path.exists(), name
        spec = importlib.util.spec_from_file_location(name, path); module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        suites.append(unittest.defaultTestLoader.loadTestsFromModule(module))
    result = unittest.TextTestRunner(verbosity=1).run(unittest.TestSuite(suites))
    base.write(audit / 'tested.json', {'testsRun': result.testsRun, 'success': result.wasSuccessful(), 'realProviderRequests': 0})
    raise SystemExit(not result.wasSuccessful())


def restage():
    assert not (audit / 'installed.json').exists(), 'Already installed'
    history = audit / ('attempt-' + str(__import__('time').time_ns())); history.mkdir()
    for name in ['prepared.json', 'tested.json']:
        if (audit / name).exists(): (audit / name).replace(history / name)
    prepare()


if __name__ == '__main__':
    {'prepare': prepare, 'restage': restage, 'test': test, 'apply': base.apply, 'verify': base.verify_install}[sys.argv[1]]()
