import json,tempfile,unittest,base64,io
from pathlib import Path
from unittest.mock import patch
import server,visual_requirements as visual
import task_cover
from PIL import Image

EXTRA='所有图片上不要出现人物的正脸或者侧脸，如果有人，最好是背影，不要突出人物，突出场景剧情'
class VisualExtraTests(unittest.TestCase):
 def test_explicit_no_face_removes_conflicting_portrait_descriptions_and_is_idempotent(self):
  prompt='复古胶片，半身肖像，黑框眼镜，神情专注，办公室里的印刷机'
  result=visual.apply(prompt,EXTRA)
  self.assertIn(EXTRA,result);self.assertIn('完全背对镜头',result);self.assertIn('办公室里的印刷机',result)
  for term in ['半身肖像','黑框眼镜','神情专注']:self.assertNotIn(term,result)
  self.assertEqual(visual.apply(result,EXTRA),result)
 def test_other_requirements_do_not_turn_on_no_face_and_empty_preserves_prompt(self):
  self.assertEqual(visual.apply('侧脸肖像',''),'侧脸肖像')
  self.assertIn('侧脸肖像',visual.apply('侧脸肖像','用蓝色背景'))
 def test_persisted_empty_requirement_wins_over_old_request(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'request.json').write_text(json.dumps({'extra':EXTRA}),'utf8')
   self.assertEqual(visual.load(root),EXTRA)
   (root/'client_config.json').write_text(json.dumps({'generate':{'extra':''}}),'utf8')
   self.assertEqual(visual.load(root),'')
 def test_both_llm_request_and_fallback_keep_visual_requirement(self):
  with patch.object(server,'call_llm',return_value='[]') as call:
   rows=server.step3_image_prompts({'_visual_extra':EXTRA},[{'idx':1,'text':'人物来到办公室'}],'character-story','vintage-film')
  self.assertIn(EXTRA,call.call_args.args[2]);self.assertIn(EXTRA,rows[0]['desc_prompt']);self.assertNotIn('半身肖像',rows[0]['desc_prompt'])
 def test_new_provider_request_has_constraint_but_paid_cached_result_is_reused(self):
  with tempfile.TemporaryDirectory() as d:
   folder=Path(d);(folder/'client_config.json').write_text(json.dumps({'generate':{'extra':EXTRA}}),'utf8')
   cfg={'provider':'modelscope','api_key':'fake'};result={'url':'https://fixture.invalid/image.png'}
   with patch.object(server,'image_dispatcher',return_value=result) as dispatch:
    server.batch_image_result(cfg,'半身肖像，办公室里的印刷机',1,'9:16','1k',folder)
    sent=dispatch.call_args.args[1];self.assertIn(EXTRA,sent);self.assertNotIn('半身肖像',sent)
    server.batch_image_result(cfg,'半身肖像，办公室里的印刷机',1,'9:16','1k',folder)
    self.assertEqual(dispatch.call_count,1)
 def test_cover_submission_also_obeys_requirement_without_touching_user_title(self):
  with tempfile.TemporaryDirectory() as d,patch.object(server,'DATA_DIR',Path(d)):
   folder=Path(d)/'tasks/fixture';folder.mkdir(parents=True)
   (folder/'client_config.json').write_text(json.dumps({'generate':{'extra':EXTRA}}),'utf8')
   (folder/'02-meta.json').write_text(json.dumps({'title':'用户标题','cover_image_prompts':['半身肖像，黑框眼镜，办公室里的印刷机']}),'utf8')
   image=io.BytesIO();Image.new('RGB',(8,8),'blue').save(image,'PNG')
   with patch.object(server,'load_settings',return_value={}),patch.object(server,'resolve_image_config',return_value={'provider':'runninghub','api_key':'fake'}),patch.object(server,'image_dispatcher',return_value={'b64':base64.b64encode(image.getvalue()).decode()}) as dispatch:
    result=task_cover.action(server,'fixture','generate',{'operation_id':'fixture-op'})
    prompt=dispatch.call_args.args[1];self.assertIn(EXTRA,prompt);self.assertNotIn('半身肖像',prompt);self.assertIn('用户标题',prompt)

if __name__=='__main__':unittest.main()
