"""Guarded cumulative candidate: completed originals + cover gallery, no generation."""
import importlib.util,sys,shutil
from pathlib import Path
repo=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('completed_deploy',repo/'scripts/deploy-completed-task-revisions.py')
previous=importlib.util.module_from_spec(spec);spec.loader.exec_module(previous)
old_audit=previous.audit
audit=repo/'.desktop-tools/cover-gallery-20261025';payload=audit/'payload'
previous.audit=audit;previous.payload=payload;previous.base.audit=audit;previous.base.payload=payload
previous.assets+=['assets/task_cover.css']
previous.new_modules+=['cover_images']
previous.targets['task_cover']+=[('commit',),('require_idle',),('initial',)]
previous.targets['server']+=[('task_operation',),('Handler','do_GET')]
previous.targets['task_queue']+=[('TaskQueue','run_next')]
previous.python_tests+=['test_cover_gallery','test_scene_images','test_scene_reference']
previous.node_tests+=['cover_gallery.test.cjs']

def prepare():
 # Earlier pending changes and this feature are installed as one checked unit.
 # Keep exact pre-feature snapshots separate from the installed-source baseline.
 if not (audit/'gallery-source-before').exists():shutil.copytree(audit/'source-before',audit/'gallery-source-before')
 shutil.copytree(old_audit/'source-before',audit/'source-before',dirs_exist_ok=True)
 previous.prepare()

if __name__=='__main__':
 {'prepare':prepare,'test':previous.test,'node-test':previous.node_test,'apply':previous.apply,'verify':previous.base.verify_install}[sys.argv[1]]()
