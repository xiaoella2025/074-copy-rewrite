"""Bind browser/Node fixture acceptance to the exact staged runtime manifest."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode=True
repo=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('deploy1250_node',repo/'scripts/deploy-story1250-updates.py')
deployment=importlib.util.module_from_spec(spec);spec.loader.exec_module(deployment)
audit=deployment.audit; manifest=audit/'payload/backend-runtime.json'
before=hashlib.sha256(manifest.read_bytes()).hexdigest()
node=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'
with (audit/'candidate-node-tests.log').open('w',encoding='utf8') as log:
    result=subprocess.run([str(node),'--test',*['tests/'+name for name in deployment.node_tests]],cwd=audit/'static',
                          env={**os.environ,'APP074_TEST_RESOURCES':str(audit/'static')},stdout=log,stderr=subprocess.STDOUT,timeout=240)
after=hashlib.sha256(manifest.read_bytes()).hexdigest()
success=result.returncode==0 and before==after
(audit/'candidate-node-results.json').write_text(json.dumps({'success':success,'manifestSha256':before,'exitCode':result.returncode}),'utf8')
print(json.dumps({'success':success,'manifestSha256':before}))
raise SystemExit(not success)
