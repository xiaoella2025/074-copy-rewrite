import base64,io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import server,task_cover


class CoverMultilineTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.root=Path(self.temp.name);self.folder=self.root/'tasks/multiline';self.folder.mkdir(parents=True)
  self.addCleanup(patch.stopall);patch.object(server,'DATA_DIR',self.root).start()
  patch.object(server,'load_settings',return_value={}).start()
  patch.object(server,'resolve_image_config',return_value={'provider':'modelscope','api_key':'fixture','model':'fixture'}).start()
  patch.object(server,'_http_post_json',side_effect=AssertionError('real network forbidden')).start()
  self.title='为什么放着\n反而容易坏';self.subs=['生活里的老道理','越不用越容易坏','看完就明白']
  task_cover.write(self.folder/'02-meta.json',{'title':'旧题','subtitle':[],'cover_image_prompts':['厨房静物']})
 def test_save_accepts_more_than_two_lines_and_round_trip_preserves_all_text(self):
  result=task_cover.action(server,'multiline','save',{'title':self.title,'subtitle':self.subs})
  self.assertEqual(result['title'],self.title);self.assertEqual(result['subtitle'],self.subs)
  self.assertEqual(task_cover.read(self.folder/'02-meta.json',{})['subtitle'],self.subs)
  self.assertEqual(task_cover.view(server,'multiline')['title'],self.title)
 def test_initial_cover_accepts_three_lines_and_submits_exact_multiline_text_once(self):
  buf=io.BytesIO();Image.new('RGB',(8,12),'blue').save(buf,'PNG')
  (self.folder/'scene.png').write_bytes(b'existing-scene');(self.folder/'voice.mp3').write_bytes(b'existing-voice')
  with patch.object(server,'image_dispatcher',return_value={'b64':base64.b64encode(buf.getvalue()).decode()}) as generate:
   options={'title':self.title,'subtitle':self.subs,'withTitle':True}
   task_cover.initial(server,'multiline',options=options)
   task_cover.initial(server,'multiline',options=options)
  generate.assert_called_once();prompt=generate.call_args.args[1]
  self.assertIn(self.title,prompt)
  for line in self.subs:self.assertIn(line,prompt)
  self.assertNotIn('所有字必须在同一水平行',prompt)
  self.assertEqual((self.folder/'scene.png').read_bytes(),b'existing-scene')
  self.assertEqual((self.folder/'voice.mp3').read_bytes(),b'existing-voice')
 def test_metadata_keeps_every_explicit_line_instead_of_slicing_after_two(self):
  custom={'title':self.title,'subtitle':'\n'.join(self.subs)}
  with patch.object(server,'call_llm',return_value='{"title":"AI题字","short_title":"发布短题"}'):
   result=server.step1_meta({'_cover_custom_text':custom},'独立任务名','正文',[],'general')
  self.assertEqual(result['title'],self.title);self.assertEqual(result['subtitle'],self.subs)
  self.assertEqual(result['short_title'],'发布短题')
 def test_multiline_layout_overrides_one_line_template_only_when_needed(self):
  template=server.story_cover_template('cinematic-poster')
  single=server.compose_story_cover_prompt('静物','单行',[],True,None,template)
  self.assertIn('所有字必须在同一水平行',single)
  multi=server.compose_story_cover_prompt('静物',self.title,self.subs,True,None,template)
  self.assertNotIn('所有字必须在同一水平行',multi);self.assertIn('按用户换行',multi)
  minimal=server.compose_story_cover_prompt('静物',self.title,self.subs,True,None,server.story_cover_template('minimal-clean'))
  self.assertNotIn('一行排副标题',minimal)
 def test_length_and_type_errors_remain_specific(self):
  for data in ({'title':'字'*201},{'subtitle':['字'*301]},{'subtitle':[3]},{'subtitle':'非数组'}):
   with self.assertRaises(ValueError):task_cover.validate_options(server,data)

if __name__=='__main__':unittest.main()
