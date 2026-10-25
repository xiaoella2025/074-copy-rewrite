"""Second cover-gallery iteration: scene-style cards and cover-owned video adapters."""
import importlib.util,re,shutil,subprocess,sys
from pathlib import Path
repo=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('cover_tiles_base',repo/'scripts/deploy-completed-task-revisions.py')
prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
audit=repo/'.desktop-tools/cover-gallery-tiles-20261025';payload=audit/'payload'
prior.audit=audit;prior.payload=payload;prior.base.audit=audit;prior.base.payload=payload
prior.assets=['assets/task_cover.js','assets/task_cover.css','assets/workflow_view.js','assets/video_prompt.js']
prior.new_modules=['cover_motion'];prior.full_modules=['cover_images']
prior.targets={'server':[('Handler','do_GET'),('Handler','_handle_json_post')]}
prior.python_tests+=['test_cover_gallery','test_cover_motion','test_scene_images','test_scene_reference']
prior.node_tests+=['cover_gallery.test.cjs','video_prompt.test.js']

def prepare():
 before=audit/'source-before';before.mkdir(parents=True,exist_ok=True)
 if not (before/'server.py').exists():
  text=(repo/'server.py').read_text('utf8')
  text=re.sub(r"        if self.path.startswith\('/api/cover-motion/'\):.*?(?=        if self.path.startswith\('/api/cover-image/'\):)",'',text,flags=re.S)
  (before/'server.py').write_text(text,'utf8')
 if not (before/'cover_images.py').exists():
  value=subprocess.check_output(['git','show','cd14d50:cover_images.py'],cwd=repo)
  (before/'cover_images.py').write_bytes(value)
 for name in prior.assets:
  dest=before/name
  if not dest.exists():dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(prior.host/'_internal'/name,dest)
 prior.prepare()

if __name__=='__main__':{'prepare':prepare,'test':prior.test,'node-test':prior.node_test,'apply':prior.apply,'verify':prior.base.verify_install}[sys.argv[1]]()
