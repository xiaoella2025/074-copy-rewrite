import base64,hashlib,io,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import server,task_cover,cover_images

def png(color='red'):
 out=io.BytesIO();Image.new('RGB',(80,100),color).save(out,'PNG');return out.getvalue()
def uri(color='blue'):return 'data:image/png;base64,'+base64.b64encode(png(color)).decode()
def hashes(folder):return {str(p.relative_to(folder)):hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*') if p.is_file()}

class CoverGalleryTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.addCleanup(patch.stopall)
  self.root=Path(self.tmp.name);patch.object(server,'DATA_DIR',self.root).start()
  self.folder=self.root/'tasks/test';self.folder.mkdir(parents=True)
  task_cover.write(self.folder/'02-meta.json',{'title':'测试'})
  patch.object(server,'load_settings',return_value={}).start()
  patch.object(server,'resolve_image_config',return_value={'provider':'gpt_image','api_key':'fixture','base_url':'https://fixture.invalid'}).start()
  self.dispatch=patch.object(server,'image_dispatcher',return_value={'b64':base64.b64encode(png('green')).decode()}).start()
  task_cover.commit(server,'test',1,png(),{'prompt':'原图片实际提示词','provider':'runninghub_workflow'})
 def test_view_is_read_only_and_keeps_actual_prompt(self):
  before=hashes(self.folder);info=cover_images.view(server,'test',1)
  self.assertEqual(info['actualPrompt'],'原图片实际提示词');self.assertTrue(info['current']);self.assertEqual(before,hashes(self.folder))
  self.assertFalse(info['history']);self.dispatch.assert_not_called()
 def test_replace_and_restore_recover_pixels_and_prompt(self):
  old=cover_images.view(server,'test',1)
  info=cover_images.action(server,'test',1,'replace',{'data_url':uri(),'expectedRevision':old['revision']})
  self.assertEqual(info['provider'],'upload');self.assertEqual(len(info['history']),1)
  info=cover_images.action(server,'test',1,'restore',{'id':info['history'][0]['id'],'expectedRevision':info['revision']})
  self.assertEqual(info['actualPrompt'],'原图片实际提示词');self.assertEqual(info['provider'],'runninghub_workflow')
  self.assertEqual(task_cover.paths(self.folder,1)[1].read_bytes(),png())
 def test_crop_preserves_original_and_conflicts_do_not_write(self):
  original=cover_images.view(server,'test',1)
  info=cover_images.action(server,'test',1,'crop',{'rect':{'x':0,'y':0,'w':.5,'h':1},'aspect':None,'expectedRevision':original['revision']})
  with Image.open(task_cover.paths(self.folder,1)[1]) as im:self.assertEqual(im.size,(40,100))
  self.assertEqual(cover_images.media(server,'test',1,'original').read_bytes(),png())
  before=hashes(self.folder)
  with self.assertRaisesRegex(ValueError,'更新'):cover_images.action(server,'test',1,'replace',{'data_url':uri(),'expectedRevision':original['revision']})
  self.assertEqual(before,hashes(self.folder))
 def test_slots_independent_and_history_keeps_five(self):
  task_cover.commit(server,'test',2,png('white'),{'prompt':'第二张'})
  other=task_cover.paths(self.folder,2)[1].read_bytes()
  for _ in range(7):task_cover.commit(server,'test',1,png('blue'),{'prompt':'新提示词'})
  self.assertEqual(len(cover_images.view(server,'test',1)['history']),5)
  self.assertEqual(task_cover.paths(self.folder,2)[1].read_bytes(),other)
 def test_completed_mutation_forks_without_touching_source(self):
  task_cover.write(self.folder/'06-draft-meta.json',{'ok':True,'draft_dir':'finished'})
  before=hashes(self.folder)
  value=cover_images.action(server,'test',1,'replace',{'data_url':uri(),'expectedRevision':cover_images.view(server,'test',1)['revision']})
  self.assertNotEqual(value['task_id'],'test');self.assertEqual(hashes(self.folder),before)
 def test_reference_reuses_successful_operation_and_retains_source_prompt(self):
  data={'action':'generate','operation_id':'same-operation','prompt':'只把字改成正确的字','references':[uri()],'expectedRevision':cover_images.view(server,'test',1)['revision']}
  first=cover_images.action(server,'test',1,'reference',data);second=cover_images.action(server,'test',1,'reference',data)
  self.assertEqual(first['revision'],second['revision']);self.dispatch.assert_called_once()
  self.assertEqual(first['referenceJob']['status'],'ok');self.assertIn('只把字',first['actualPrompt'])
 def test_unsupported_reference_engine_never_submits(self):
  patch.object(server,'resolve_image_config',return_value={'provider':'modelscope','api_key':'fixture'}).start()
  before=hashes(self.folder)
  with self.assertRaisesRegex(ValueError,'不支持'):cover_images.action(server,'test',1,'reference',{'action':'generate','operation_id':'unsupported','prompt':'修改文字','references':[uri()]})
  self.assertEqual(hashes(self.folder),before);self.dispatch.assert_not_called()
 def test_pending_reference_blocks_replace_and_can_query_without_resubmission(self):
  task_cover.write(self.folder/'cover-reference-1.json',{'status':'pending','taskId':'paid-id','provider':'runninghub','credential':'fixture','prompt':'edit'})
  with self.assertRaisesRegex(ValueError,'在途'):cover_images.action(server,'test',1,'replace',{'data_url':uri()})
  self.assertTrue(cover_images.view(server,'test',1)['current']);self.dispatch.assert_not_called()

 def test_legacy_owned_cover_is_visible_and_enters_history_before_replacement(self):
  task_cover.paths(self.folder,1)[1].unlink();(self.folder/'cover-images.json').unlink()
  legacy=self.folder/'covers/poster.png';legacy.parent.mkdir();legacy.write_bytes(png('white'))
  task_cover.write(self.folder/'cover-meta.json',{'path':str(legacy),'provider':'old','prompt':'老封面的准确提示词'})
  before=hashes(self.folder);info=cover_images.view(server,'test',1)
  self.assertEqual(info['actualPrompt'],'老封面的准确提示词');self.assertTrue(info['current']);self.assertEqual(before,hashes(self.folder))
  new=cover_images.action(server,'test',1,'replace',{'data_url':uri()})
  self.assertEqual(new['history'][0]['prompt'],'老封面的准确提示词')
  self.assertEqual(cover_images.media(server,'test',1,new['history'][0]['id']).read_bytes(),png('white'))
 def test_creative_engine_and_ratio_match_edit_dialog(self):
  task_cover.write(self.folder/'creative.json',{'config':{'coverProvider':'runninghub','coverRatio':'16:9'}})
  task_cover.write(self.folder/'client_config.json',{'cover':{'provider':'gpt_image','ratio':'3:4'}})
  info=cover_images.view(server,'test',1)
  self.assertEqual(info['editProviderLabel'],'runninghub');self.assertEqual(info['ratio'],'16:9')
 def test_interrupted_transaction_has_read_only_recovery_entry_and_recovers_locally(self):
  original=cover_images.recover;calls=[]
  def fail_after_journal(folder):
   if (folder/'cover-image-transaction.json').exists():raise OSError('simulated interrupted save')
   return original(folder)
  with patch.object(cover_images,'recover',side_effect=fail_after_journal):
   with self.assertRaises(OSError):cover_images.commit(server,'test',1,png('blue'),{'prompt':'new pixels'})
  before=hashes(self.folder);self.assertTrue(task_cover.view(server,'test')['imageInfo']['recoveryNeeded']);self.assertEqual(before,hashes(self.folder))
  result=task_cover.action(server,'test','recover',{})
  self.assertEqual(result['imageInfo']['actualPrompt'],'new pixels');self.dispatch.assert_not_called()
 def test_pending_reference_blocks_generic_pack_lease_and_queue(self):
  import task_queue
  task_cover.write(self.folder/'cover-reference-1.json',{'status':'pending'})
  with self.assertRaisesRegex(ValueError,'在途'):
   with server.task_operation('test'):pass
  called=[];q=task_queue.TaskQueue(server,executor=lambda *args:called.append(True));q.enqueue('test',from_step='6',config={'generate':{},'image':{},'tts':{}});q.run_next()
  self.assertFalse(called)
 def test_reference_failed_download_reuses_saved_result_without_new_submission(self):
  data={'action':'generate','operation_id':'download-once','prompt':'correct text','references':[uri()]}
  original=task_cover.image_bytes
  with patch.object(task_cover,'image_bytes',side_effect=lambda value:(_ for _ in ()).throw(OSError('download')) if value.get('b64')==base64.b64encode(png('green')).decode() else original(value)):
   with self.assertRaises(OSError):cover_images.action(server,'test',1,'reference',data)
  result=cover_images.action(server,'test',1,'reference',{'action':'query'})
  self.assertEqual(result['referenceJob']['status'],'ok');self.dispatch.assert_called_once()
 def test_completed_reference_timeout_attaches_child_identity(self):
  task_cover.write(self.folder/'06-draft-meta.json',{'ok':True,'draft_dir':'finished'})
  before=hashes(self.folder);self.dispatch.side_effect=TimeoutError('unknown submission')
  with self.assertRaises(TimeoutError) as failure:cover_images.action(server,'test',1,'reference',{'action':'generate','operation_id':'unknown-once','prompt':'correct text','references':[uri()]})
  self.assertNotEqual(failure.exception.task_id,'test');self.assertEqual(failure.exception.source_task_id,'test');self.assertEqual(before,hashes(self.folder))
  self.assertEqual(task_cover.read(self.root/'tasks'/failure.exception.task_id/'cover-reference-1.json',{})['status'],'unknown')
 def test_second_slot_is_not_enabled_by_first_slot_directions(self):
  task_cover.write(self.folder/'02-meta.json',{'title':'one','cover_image_prompts':['first scene']})
  self.assertFalse(task_cover.view(server,'test',2)['available'])

 def test_invalid_reference_pixels_become_terminal_and_can_be_replaced(self):
  self.dispatch.return_value={'b64':base64.b64encode(b'not an image').decode()}
  with self.assertRaises(ValueError):cover_images.action(server,'test',1,'reference',{'action':'generate','operation_id':'invalid-pixels','prompt':'correct text','references':[uri()]})
  self.assertEqual(task_cover.read(self.folder/'cover-reference-1.json',{})['status'],'failed')
  result=cover_images.action(server,'test',1,'replace',{'data_url':uri()})
  self.assertEqual(result['provider'],'upload');self.dispatch.assert_called_once()

 def test_completed_reference_query_restores_current_pixels_without_rewinding_newer_edit(self):
  data={'action':'generate','operation_id':'restore-cache','prompt':'correct text','references':[uri()]}
  cover_images.action(server,'test',1,'reference',data);target=task_cover.paths(self.folder,1)[1];target.unlink()
  recovered=cover_images.action(server,'test',1,'reference',{'action':'query'})
  self.assertTrue(recovered['current']);self.assertEqual(target.read_bytes(),png('green'))
  cover_images.action(server,'test',1,'replace',{'data_url':uri('white')});target.unlink()
  cover_images.action(server,'test',1,'reference',{'action':'query'})
  self.assertEqual(target.read_bytes(),png('white'));self.dispatch.assert_called_once()

 def test_reference_result_cache_restores_after_png_normalization(self):
  stream=io.BytesIO();Image.new('RGB',(80,100),'green').save(stream,'PNG',compress_level=0)
  self.dispatch.return_value={'b64':base64.b64encode(stream.getvalue()).decode()}
  cover_images.action(server,'test',1,'reference',{'action':'generate','operation_id':'different-encoding','prompt':'correct text','references':[uri()]})
  item=cover_images.manifest(self.folder)['items']['1'];job=task_cover.read(self.folder/'cover-reference-1.json',{})
  self.assertEqual(job['appliedRevision'],item['revision'])
  task_cover.paths(self.folder,1)[1].unlink();(self.folder/item['file']).unlink()
  result=cover_images.action(server,'test',1,'reference',{'action':'query'})
  self.assertTrue(result['current']);self.dispatch.assert_called_once()

 def test_reference_supplier_failure_does_not_expose_private_payload(self):
  self.dispatch.side_effect=RuntimeError('SENTINEL_PRIVATE_KEY')
  with self.assertRaises(RuntimeError) as failure:cover_images.action(server,'test',1,'reference',{'action':'generate','operation_id':'private-error','prompt':'correct text','references':[uri()]})
  self.assertNotIn('SENTINEL_PRIVATE_KEY',str(failure.exception));self.assertNotIn('SENTINEL_PRIVATE_KEY',(self.folder/'cover-reference-1.json').read_text('utf8'))

 def test_plain_cover_reference_keeps_existing_no_text_mode(self):
  task_cover.write(self.folder/'client_config.json',{'cover':{'mode':'plain'}})
  result=cover_images.action(server,'test',1,'reference',{'action':'generate','operation_id':'plain','prompt':'修改风景','references':[uri()]})
  state=task_cover.view(server,'test',1);self.assertEqual(state['mode'],'plain');self.assertFalse(state['withTitle'])
 def test_plain_cover_history_restore_keeps_no_text_mode(self):
  task_cover.write(self.folder/'client_config.json',{'cover':{'mode':'plain'}})
  task_cover.commit(server,'test',1,png('white'),{'prompt':'无字底图'})
  result=cover_images.action(server,'test',1,'replace',{'data_url':uri()})
  cover_images.action(server,'test',1,'restore',{'id':result['history'][0]['id']})
  state=task_cover.view(server,'test',1);self.assertEqual(state['mode'],'plain');self.assertFalse(state['withTitle'])

if __name__=='__main__':unittest.main()
