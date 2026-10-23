import json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from contextlib import nullcontext
import prompt_format_repair as repair

class RepairTests(unittest.TestCase):
 def test_quotes_and_literal_newlines_preserve_text(self):
  value=repair.parse('[{"id":1,"cap":"他说"你好"。\n下一行","desc_prompt":"老人站在庭院里看向远方"}]')
  self.assertEqual(value[0]['cap'],'他说"你好"。\n下一行')
 def test_valid_json_is_unchanged(self):
  value=[{'id':1,'cap':'他说"你好"，[]{}','desc_prompt':'老人站在庭院里看向远方'}]
  self.assertEqual(repair.parse(json.dumps(value)),value)
 def test_truncated_or_ambiguous_data_is_not_invented(self):
  for text in ['[{"id":1,"desc_prompt":"一段未完成', '{"a":"one" "b":"two"}', '[{"id":1}', 'no JSON']:
   with self.subTest(text=text),self.assertRaises(ValueError):repair.parse(text)
 def test_saved_repair_preserves_images_other_prompts_and_never_calls_provider(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);folder=root/'tasks/fixture';folder.mkdir(parents=True)
   shots=[{'idx':1,'text':'他说"你好"。'}]
   (folder/'03-shots.json').write_text(json.dumps(shots),'utf8')
   (folder/'covers').mkdir();(folder/'covers/1.png').write_bytes(b'keep')
   identity=repair.save_source(folder,shots,['[{"id":1,"cap":"他说"你好"。","desc_prompt":"老人站在庭院里看向远方"}]'],'character-story','',True,None)
   prompts=[{'idx':1,'text':shots[0]['text'],'desc_prompt':'backup','diagnostic':{'fellBackToSkeleton':True,'repairId':identity,'fallbackPrompt':'backup'}}, {'idx':2,'desc_prompt':'manual'}]
   path=folder/'04-prompts.json';path.write_text(json.dumps(prompts),'utf8')
   backend=SimpleNamespace(DATA_DIR=root,task_operation=lambda _:nullcontext(),story_workflow_reference=lambda:{'tracks':{'character-story':{}}})
   result=repair.apply(backend,'fixture',{'repair_id':identity})
   self.assertEqual(result['repaired'],1)
   updated=json.loads(path.read_text('utf8'));self.assertEqual(updated[1],prompts[1]);self.assertEqual(updated[0]['desc_prompt'],'老人站在庭院里看向远方');self.assertTrue(updated[0]['diagnostic']['formatRepaired'])
   self.assertEqual((folder/'covers/1.png').read_bytes(),b'keep')
   self.assertEqual(repair.apply(backend,'fixture',{'repair_id':identity})['repaired'],0)
 def test_manual_prompt_and_incomplete_response_never_get_overwritten(self):
  for raw,manual in [('[{"id":1,"desc_prompt":"truncated',False),('[{"id":1,"desc_prompt":"老人站在庭院里看向远方"}]',True)]:
   with self.subTest(manual=manual),tempfile.TemporaryDirectory() as d:
    root=Path(d);folder=root/'tasks/fixture';folder.mkdir(parents=True);shots=[{'idx':1,'text':'fixture'}]
    (folder/'03-shots.json').write_text(json.dumps(shots),'utf8')
    identity=repair.save_source(folder,shots,[raw],'character-story','',True,None)
    prompts=[{'idx':1,'text':'fixture','desc_prompt':'manual' if manual else 'backup','diagnostic':{'fellBackToSkeleton':True,'repairId':identity,'fallbackPrompt':'backup'}}]
    path=folder/'04-prompts.json';path.write_text(json.dumps(prompts),'utf8');before=path.read_bytes()
    backend=SimpleNamespace(DATA_DIR=root,task_operation=lambda _:nullcontext(),story_workflow_reference=lambda:{'tracks':{}})
    with self.assertRaises(ValueError):repair.apply(backend,'fixture',{'repair_id':identity})
    self.assertEqual(path.read_bytes(),before)
 def test_missing_full_response_explains_no_paid_retry(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);(root/'tasks/fixture').mkdir(parents=True)
   backend=SimpleNamespace(DATA_DIR=root,task_operation=lambda _:nullcontext())
   with self.assertRaisesRegex(ValueError,'完整.*不会'):repair.apply(backend,'fixture',{'repair_id':'a'*32})

if __name__=='__main__':unittest.main()
