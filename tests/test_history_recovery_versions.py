import importlib.util,json,tempfile,threading,unittest
from pathlib import Path
from types import SimpleNamespace
from image_motion import write,read

spec=importlib.util.spec_from_file_location('recover_history',Path(__file__).resolve().parents[1]/'scripts/recover-completed-history.py')
recovery=importlib.util.module_from_spec(spec);spec.loader.exec_module(recovery)

class HistoryRecoveryVersions(unittest.TestCase):
 def run_case(self,completed):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);data=root/'data';folder=data/'tasks/original';archive=folder/'.reruns/known';archive.mkdir(parents=True)
   old=root/'old-draft.json';new=root/'new-draft.json';write(old,{'tracks':['old']});write(new,{'tracks':['new']})
   write(archive/'06-draft-meta.json',{'ok':True,'draft_dir':str(root/'old'),'draft_content_path':str(old)})
   (archive/'02-rewrite.txt').write_text('original complete','utf8');(folder/'02-rewrite.txt').write_text('latest edits','utf8')
   write(folder/'client_config.json',{'generate':{},'image':{},'tts':{}});write(folder/'progress.json',{'step':'6','status':'done' if completed else 'paused'})
   if completed:write(folder/'06-draft-meta.json',{'ok':True,'draft_dir':str(root/'new'),'draft_content_path':str(new)})
   write(data/'task-queue.json',{'jobs':[{'id':'existing','task_id':'original','status':'completed' if completed else 'paused','config':{}}],'batches':[]})
   backend=SimpleNamespace(DATA_DIR=data,TASK_OPERATION_LOCK=threading.RLock())
   result=recovery.recover(backend,'original','known',root/'backup');child=data/'tasks'/result['working_task_id']
   self.assertEqual((folder/'02-rewrite.txt').read_text('utf8'),'original complete');self.assertEqual((child/'02-rewrite.txt').read_text('utf8'),'latest edits')
   self.assertEqual(result['workingCompleted'],completed);self.assertEqual(result['workingPaused'],not completed)
   self.assertEqual((child/'06-draft-meta.json').exists(),completed)
   jobs=read(data/'task-queue.json',{})['jobs'];self.assertEqual(jobs[0]['status'],'completed' if completed else 'paused');self.assertEqual(jobs[1]['status'],'completed')
   self.assertEqual(json.loads(old.read_text('utf8')),{'tracks':['old']});self.assertEqual(json.loads(new.read_text('utf8')),{'tracks':['new']})
 def test_preserve_latest_completed_version_as_completed(self):self.run_case(True)
 def test_preserve_unfinished_working_version_as_paused(self):self.run_case(False)

if __name__=='__main__':unittest.main()
