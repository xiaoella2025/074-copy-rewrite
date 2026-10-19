"""Deploy bounded scene recovery, preserving all unrelated installed code/data."""
import difflib
import importlib.util
import json
import marshal
import shutil
import struct
import sys
import types
from pathlib import Path
sys.dont_write_bytecode = True
repo = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('deployment_guard', repo / 'scripts/deploy-image-completion-repair.py')
prior = importlib.util.module_from_spec(spec); spec.loader.exec_module(prior)
base = prior.base
base.audit = repo / '.desktop-tools/image-auto-retry-20261019'
base.payload = base.audit / 'payload'
audit, payload, host = base.audit, base.payload, base.host
assets = ['index.html', 'assets/image_pipeline.js', 'assets/workflow_actions.js', 'assets/task_reuse.js', 'assets/workflow_view.js']


def nested(code, path):
    for name in path:
        code = next(c for c in code.co_consts if isinstance(c, types.CodeType) and c.co_name == name)
    return code


def replace(code, path, replacement):
    name, *rest = path
    return code.replace(co_consts=tuple(
        (replace(c, rest, replacement) if rest else replacement)
        if isinstance(c, types.CodeType) and c.co_name == name else c for c in code.co_consts))


def prepare():
    assert not (audit / 'prepared.json').exists(), 'Already prepared'
    before = audit / 'source-before'
    baseline = base.verify(host)
    internal = payload / '_internal'; internal.mkdir(parents=True, exist_ok=True)
    header = importlib.util.MAGIC_NUMBER + struct.pack('<III', 0, 0, 0)
    old = compile((before / 'server.py').read_text('utf8'), '<before>', 'exec')
    installed = marshal.loads((host / '_internal/server.pyc').read_bytes()[16:])
    new = compile((repo / 'server.py').read_text('utf8'), str(host / '_internal/server.pyc'), 'exec')
    # Replace exactly two code objects. Other installed functions stay byte-for-byte.
    for path in [('get_task_detail',), ('Handler', '_handle_json_post')]:
        assert base.signature(nested(old, path)) == base.signature(nested(installed, path)), 'Server baseline drift: ' + str(path)
        assert nested(new, path).co_freevars == nested(installed, path).co_freevars
        installed = replace(installed, path, nested(new, path))
    (internal / 'server.pyc').write_bytes(header + marshal.dumps(installed))
    for name in ['scene_image_recovery', 'image_auto_retry']:
        source = repo / (name + '.py')
        if name == 'scene_image_recovery':
            original = marshal.loads((host / '_internal' / (name + '.pyc')).read_bytes()[16:])
            assert base.signature(compile((before / (name + '.py')).read_text('utf8'), '<before>', 'exec')) == base.signature(original)
        else:
            assert not (host / '_internal' / (name + '.pyc')).exists(), 'Already installed'
        (internal / (name + '.pyc')).write_bytes(header + marshal.dumps(compile(source.read_text('utf8'), str(host / '_internal' / (name + '.pyc')), 'exec')))
    delta = ''
    for name in ['server.py', 'scene_image_recovery.py', *assets]:
        a = (before / name).read_text('utf8').splitlines(True)
        b = (repo / name).read_text('utf8').splitlines(True)
        delta += ''.join(difflib.unified_diff(a, b, fromfile='before/' + name, tofile=name))
        if name not in assets:
            continue
        value = (host / '_internal' / name).read_text('utf8')
        for group in difflib.SequenceMatcher(a=a, b=b).get_grouped_opcodes(3):
            previous = ''.join(a[group[0][1]:group[-1][2]])
            current = ''.join(b[group[0][3]:group[-1][4]])
            assert value.count(previous) == 1, 'Installed asset drift: ' + name
            value = value.replace(previous, current, 1)
        target = internal / name; target.parent.mkdir(parents=True, exist_ok=True); target.write_text(value, 'utf8')
    (audit / 'source-deltas.patch').write_text(delta, 'utf8')
    hashes = {}
    for path in payload.rglob('*'):
        if not path.is_file() or path.name == 'backend-runtime.json':
            continue
        relative = path.relative_to(payload).as_posix(); original = host / relative
        hashes[relative] = base.digest(original) if original.exists() else None
        if original.exists():
            target = audit / 'before' / relative; target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(original, target)
    shutil.copyfile(host / 'backend-runtime.json', audit / 'manifest-before.json')
    manifest = json.loads((host / 'backend-runtime.json').read_text('utf8'))
    manifest['moduleCount'] += 1
    for relative in hashes:
        manifest['files'][relative] = base.digest(payload / relative)
    base.write(payload / 'backend-runtime.json', manifest)
    node = audit / 'node'; (node / 'tests').mkdir(parents=True, exist_ok=True)
    shutil.copytree(host / '_internal/assets', node / 'assets', dirs_exist_ok=True)
    for name in assets:
        target = node / name; target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(internal / name, target)
    shutil.copyfile(host / '_internal/result.html', node / 'result.html')
    for name in ['image_auto_retry.test.js', 'image_completion_repair.test.js', 'image_pipeline.test.js', 'task_reuse.test.js', 'task_params.test.js', 'workflow_failure.test.js', 'step_editor_priorities.test.js']:
        shutil.copyfile(repo / 'tests' / name, node / 'tests' / name)
    base.write(audit / 'prepared.json', {'baseline': baseline, 'oldHashes': hashes, 'protected': base.protected(), 'realProviderRequests': 0})
    print(json.dumps({'prepared': True, 'changedFiles': len(hashes)}))


def test():
    sys.path[:0] = [str(payload / '_internal'), str(host / '_internal')]
    stdlib = Path.home() / 'AppData/Local/Programs/Python/Python314/Lib'; sys.path.append(str(stdlib))
    import unittest
    unittest.__path__.append(str(stdlib / 'unittest'))
    import server, story1245_runtime
    server.ROOT = host / '_internal'; server.PROMPTS_DIR = server.ROOT / 'prompts'; story1245_runtime.install(server)
    suites = []
    for name in ['test_image_auto_retry', 'test_scene_image_recovery', 'test_batch_image_receipts', 'test_batch_image_http', 'test_task_queue', 'test_task_pause', 'test_queue_cover_completion', 'test_task_revision']:
        spec = importlib.util.spec_from_file_location(name, repo / 'tests' / (name + '.py'))
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        suites.append(unittest.defaultTestLoader.loadTestsFromModule(module))
    result = unittest.TextTestRunner(verbosity=1).run(unittest.TestSuite(suites))
    base.write(audit / 'tested.json', {'testsRun': result.testsRun, 'success': result.wasSuccessful(), 'realProviderRequests': 0})
    raise SystemExit(not result.wasSuccessful())


def restage():
    assert not (audit / 'installed.json').exists(), 'Already installed'
    history = audit / ('attempt-' + str(__import__('time').time_ns())); history.mkdir()
    for name in ['prepared.json', 'tested.json']:
        if (audit / name).exists():
            (audit / name).replace(history / name)
    prepare()


if __name__ == '__main__':
    {'prepare': prepare, 'restage': restage, 'test': test, 'apply': base.apply, 'verify': base.verify_install}[sys.argv[1]]()
