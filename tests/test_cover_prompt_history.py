import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import server,task_cover

class CoverPromptHistoryTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.root=Path(self.temp.name);self.folder=self.root/'tasks/history';self.folder.mkdir(parents=True)
  self.addCleanup(patch.stopall);patch.object(server,'DATA_DIR',self.root).start()
  patch.object(server,'call_llm',side_effect=AssertionError('preview cannot call LLM')).start()
  patch.object(server,'image_dispatcher',side_effect=AssertionError('preview cannot generate')).start()
  task_cover.write(self.folder/'02-meta.json',{'title':'原题','subtitle':['原副题']})
 def test_invalid_cache_remains_visible_as_history_and_is_not_current_prompt(self):
  task_cover.write(self.folder/'cover-prompt-1.json',{'key':'outdated','prompt':'上次保存的完整提示词'})
  before=(self.folder/'cover-prompt-1.json').read_bytes()
  info=task_cover.view(server,'history')
  self.assertEqual(info['prompt'],'');self.assertEqual(info.get('lastPrompt'),'上次保存的完整提示词')
  task_cover.action(server,'history','save',{'title':'新题'})
  info=task_cover.view(server,'history')
  self.assertEqual(info['prompt'],'');self.assertEqual(info['lastPrompt'],'上次保存的完整提示词')
  self.assertEqual((self.folder/'cover-prompt-1.json').read_bytes(),before)
 def test_valid_cache_remains_current(self):
  info=task_cover.view(server,'history')
  task_cover.write(self.folder/'cover-prompt-1.json',{'key':task_cover.prompt_key(info),'prompt':'当前提示词'})
  info=task_cover.view(server,'history');self.assertEqual(info['prompt'],'当前提示词');self.assertEqual(info.get('lastPrompt'),'当前提示词')
 def test_job_prompt_is_historical_when_parameters_have_changed(self):
  task_cover.write(self.folder/'cover-job-1.json',{'status':'pending','taskId':'preserve','template':'cinematic-poster','prompt':'旧文字的已提交提示词'})
  task_cover.write(self.folder/'cover-editor.json',{'1':{'title':'新题','template':'cinematic-poster'}})
  info=task_cover.view(server,'history')
  self.assertEqual(info['prompt'],'');self.assertEqual(info.get('lastPrompt'),'旧文字的已提交提示词')
  self.assertEqual(info['job']['taskId'],'preserve')
 def test_completed_cover_prompt_can_be_read_when_job_and_cache_are_missing(self):
  task_cover.write(self.folder/'cover-meta.json',{'prompt':'图片保存时的提示词'})
  info=task_cover.view(server,'history');self.assertEqual(info.get('lastPrompt'),'图片保存时的提示词')

if __name__=='__main__':unittest.main()
