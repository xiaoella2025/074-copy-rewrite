"""Register four real, single-submit RH task receipts without changing defaults."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from image_motion import read, write
import rh_coins_experiment as experiment
import rh_workflow_catalog as catalog
import rh_workflow_provider as provider

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / '.desktop-tools/rh-four-live-tests-20261027'
BACKEND = SimpleNamespace(DATA_DIR=Path.home() / 'AppData/Local/com.app074.desktop/data')
KEYS = ('qwen-native', 'flux-native', 'qwen-chinese', 'sdxl-native')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def register():
    done = AUDIT / 'registration.json'
    assert not done.exists(), 'These task receipts are already registered'
    cfg = experiment.config(BACKEND)
    config_path = experiment.directory(BACKEND) / 'config.json'
    config_sha = sha(config_path)
    first = next((read(p, {}) for p in (experiment.directory(BACKEND) / 'jobs').glob('*/job.json') if read(p, {}).get('status') == 'ok'), {})
    assert experiment.credential(cfg) == first.get('credential'), 'Current Key differs from first successful task'
    info = experiment.account(BACKEND, cfg)
    assert info.get('remainCoins') == '879' and info.get('currentTaskCounts') == '0', 'Account changed since four tests'
    records = []
    balance = 949
    for key in KEYS:
        entry = catalog.entries(BACKEND)[key]
        row = read(AUDIT / (key + '.json'), {})
        image = AUDIT / (key + '.png')
        assert row.get('status') == 'ok' and row.get('responseCode') == 0
        assert row.get('workflowId') == entry['id'] and row.get('balanceBefore') == balance
        assert image.is_file() and row.get('imageBytes') == image.stat().st_size
        assert isinstance(row.get('taskId'), str) and row.get('spentCoins', 0) > 0
        balance = row['balanceAfter']
        records.append((key, entry, row, image))
    assert balance == 879 and sum(row['spentCoins'] for _, _, row, _ in records) == 70
    backup = AUDIT / 'cache-before'
    backup.mkdir(exist_ok=False)
    for key, _, _, _ in records:
        path = catalog.cache_path(BACKEND, key)
        if path.exists():
            shutil.copy2(path, backup / (key + '.json'))
    written = []
    try:
        for key, entry, row, image in records:
            saved = catalog.inspect_entry(BACKEND, cfg, key, entry, info)
            old = read(backup / (key + '.json'), {})
            if old:
                assert old.get('sourceSha256') == saved['sourceSha256'], 'Source graph changed since preflight: ' + key
            proof = {'status': 'ok', 'workflowId': entry['id'], 'sourceSha256': saved['sourceSha256'],
                     'credential': saved['credential'], 'taskId': row['taskId'],
                     'imageSha256': sha(image), 'imageBytes': row['imageBytes'],
                     'spentCoins': row['spentCoins'], 'balanceBefore': row['balanceBefore'],
                     'balanceAfter': row['balanceAfter'], 'testedAt': row['createdAt']}
            path = catalog.cache_path(BACKEND, key)
            write(path, {**saved, 'api_test': proof})
            written.append(path)
            resolved = provider.resolve(BACKEND, key)
            assert resolved['checked'] and resolved['api_tested'] and resolved['live_tested']
        assert sha(config_path) == config_sha, 'Default or Key configuration changed'
    except BaseException:
        for path in written:
            previous = backup / path.name
            if previous.exists():
                shutil.copy2(previous, path)
            else:
                path.unlink(missing_ok=True)
        raise
    summary = {'registered': [key for key, _, _, _ in records], 'costs': {key: row['spentCoins'] for key, _, row, _ in records},
               'balanceBefore': 949, 'balanceAfter': 879, 'totalSpent': 70,
               'taskIds': {key: row['taskId'] for key, _, row, _ in records}, 'configUnchanged': True}
    write(done, summary)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    register()
