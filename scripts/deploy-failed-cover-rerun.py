"""Install the explicit failed-cover retry fix without supplier requests."""
import importlib.util
from pathlib import Path

repo=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('deployment',repo/'scripts/deploy-rh-live-tests.py')
deployment=importlib.util.module_from_spec(spec)
spec.loader.exec_module(deployment)
deployment.modules=('task_cover',)
deployment.assets=('assets/workflow_actions.js',)
deployment.paths=('_internal/task_cover.pyc','_internal/assets/workflow_actions.js')
deployment.audit=repo/'.desktop-tools/failed-cover-rerun-20261027/deployment'

if __name__=='__main__':deployment.install()
