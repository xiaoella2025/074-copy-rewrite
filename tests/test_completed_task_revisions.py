import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import server,task_cover,task_queue

class CompletedTaskRevisionTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
  self.root=Path(self.temp.name);self.folder=self.root/'tasks/original';self.folder.mkdir(parents=True)
  self.addCleanup(patch.stopall);patch.object(server,'DATA_DIR',self.root).start()
  self.q=task_queue.TaskQueue(server,executor=lambda *args: {'status':'completed'})
  patch.object(task_queue,'get_queue',return_value=self.q).start()
  task_cover.write(self.folder/'client_config.json',{'generate':{},'image':{},'tts':{}})
  task_cover.write(self.folder/'02-meta.json',{'title':'原成品','subtitle':[]})
  task_cover.write(self.folder/'06-draft-meta.json',{'ok':True,'draft_dir':'D:/unchanged-original-draft'})
  (self.folder/'audio').mkdir();(self.folder/'audio/seg_001.mp3').write_bytes(b'paid voice')
  task_cover.write(self.folder/'05-tts-segments.json',[{'path':str(self.folder/'audio/seg_001.mp3')}])
  (self.folder/'covers').mkdir();(self.folder/'covers/1.png').write_bytes(b'paid picture')
  task_cover.write(self.folder/'cover-meta.json',{'path':str(self.folder/'cover-poster-1.png'),'url':'/api/task_cover/original/1.png'})
  (self.folder/'cover-poster-1.png').write_bytes(b'old final cover')
 def snapshot(self):return {str(p.relative_to(self.folder)):hashlib.sha256(p.read_bytes()).hexdigest() for p in self.folder.rglob('*') if p.is_file()}
 def test_completed_cover_save_creates_new_task_and_preserves_source_bytes(self):
  before=self.snapshot();result=task_cover.action(server,'original','save',{'title':'修改后的封面字'})
  self.assertNotEqual(result.get('task_id'),'original');self.assertTrue(result.get('task_id'))
  target=self.root/'tasks'/result['task_id'];self.assertFalse((target/'06-draft-meta.json').exists())
  self.assertEqual(result['title'],'修改后的封面字');self.assertEqual(self.snapshot(),before)
  segments=task_cover.read(target/'05-tts-segments.json',[]);self.assertEqual(segments[0]['path'],str(target/'audio/seg_001.mp3'))
  (target/'covers/1.png').write_bytes(b'changed new picture');self.assertEqual((self.folder/'covers/1.png').read_bytes(),b'paid picture')
 def test_completed_enqueue_keeps_original_terminal_record_and_queues_new_id(self):
  before=self.snapshot();self.q.jobs=[{'id':'done','task_id':'original','kind':'image','status':'completed','config':{},'created_at':1,'updated_at':1}]
  result=self.q.enqueue('original',from_step='6')
  self.assertNotEqual(result['task_id'],'original');self.assertEqual(self.q.get('original')['status'],'completed');self.assertEqual(self.snapshot(),before)
 def test_unfinished_task_keeps_current_id(self):
  (self.folder/'06-draft-meta.json').unlink();result=task_cover.action(server,'original','save',{'title':'未完成编辑'})
  self.assertEqual(result['title'],'未完成编辑');self.assertIn(result.get('task_id'),(None,'original'))
  self.assertEqual(self.q.enqueue('original',from_step='6')['task_id'],'original')
 def test_batch_records_actual_new_task_id(self):
  result=self.q.enqueue_batch(['original'])
  self.assertNotEqual(result['task_ids'],['original'])
  self.assertEqual(result['task_ids'],[job['task_id'] for job in self.q.jobs if job.get('batch_id')==result['id']])
 def test_rebased_windows_paths_and_local_ids_do_not_point_back_to_original(self):
  import task_versions
  target=self.root/'tasks/new'
  doubled=str(self.folder/'audio/seg_001.mp3').replace('\\','\\\\')
  value=task_versions.rebase({'task_id':'original','path':doubled,'taskId':'supplier-remote-id','source_task_id':'original'},self.folder,target,'original','new')
  self.assertEqual(value['path'],str(target/'audio/seg_001.mp3'));self.assertEqual(value['task_id'],'new')
  self.assertEqual(value['taskId'],'supplier-remote-id');self.assertEqual(value['source_task_id'],'original')
 def test_config_http_creates_new_version_and_rebases_owned_bgm(self):
  import http.client,threading
  bgm=self.folder/'task-bgm.mp3';bgm.write_bytes(b'original bgm');before=self.snapshot()
  httpd=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);worker=threading.Thread(target=httpd.serve_forever,daemon=True);worker.start()
  try:
   c=http.client.HTTPConnection('127.0.0.1',httpd.server_port,timeout=5)
   c.request('POST','/api/task/original/config',json.dumps({'generate':{},'image':{'bgmPath':str(bgm)},'tts':{}}),{'Content-Type':'application/json'})
   response=c.getresponse();value=json.loads(response.read());c.close();self.assertEqual(response.status,200,value)
   self.assertNotEqual(value['task_id'],'original');target=self.root/'tasks'/value['task_id']
   self.assertEqual(task_cover.read(target/'client_config.json',{})['image']['bgmPath'],str(target/'task-bgm.mp3'))
   self.assertEqual(self.snapshot(),before)
  finally:httpd.shutdown();httpd.server_close();worker.join(2)
 def test_failed_new_cover_returns_its_id_for_query_without_mutating_source(self):
  before=self.snapshot()
  with patch.object(server,'resolve_image_config',return_value={'provider':'modelscope','api_key':'fixture'}),patch.object(server,'image_dispatcher',side_effect=TimeoutError('poll timeout')):
   with self.assertRaises(TimeoutError) as caught:task_cover.action(server,'original','generate',{'operation_id':'once','prompt':'新词'})
  new_id=caught.exception.task_id;self.assertNotEqual(new_id,'original');self.assertEqual(self.snapshot(),before)
  self.assertEqual(task_cover.read(self.root/'tasks'/new_id/'cover-job-1.json',{})['status'],'unknown')
 def test_pending_paid_receipt_cannot_be_cloned_to_buy_again(self):
  task_cover.write(self.folder/'cover-job-1.json',{'status':'unknown','prompt':'uncertain paid request'})
  before=self.snapshot()
  with self.assertRaises(ValueError):task_cover.action(server,'original','save',{'title':'不应另买'})
  self.assertEqual(self.snapshot(),before);self.assertEqual(len(list((self.root/'tasks').iterdir())),1)
 def test_original_enqueue_retry_reuses_one_child_and_explicit_new_intent_can_fork_again(self):
  first=self.q.enqueue('original',from_step='4',operation_id='same-request')
  second=self.q.enqueue('original',from_step='4',operation_id='same-request')
  self.assertEqual(first['task_id'],second['task_id']);self.assertEqual(len(self.q.jobs),1)
  third=self.q.enqueue('original',from_step='4',operation_id='new-request');self.assertNotEqual(third['task_id'],first['task_id'])
 def test_duplicate_original_cover_request_submits_once(self):
  import base64,io
  from PIL import Image
  buf=io.BytesIO();Image.new('RGB',(8,12),'blue').save(buf,'PNG');before=self.snapshot()
  with patch.object(server,'resolve_image_config',return_value={'provider':'modelscope','api_key':'fixture'}),patch.object(server,'image_dispatcher',return_value={'b64':base64.b64encode(buf.getvalue()).decode()}) as generate:
   first=task_cover.action(server,'original','generate',{'operation_id':'same-confirmation','prompt':'已确认的新词'})
   second=task_cover.action(server,'original','generate',{'operation_id':'same-confirmation','prompt':'已确认的新词'})
  self.assertEqual(first['task_id'],second['task_id']);generate.assert_called_once();self.assertEqual(self.snapshot(),before)
 def test_timeout_retry_points_to_same_child_without_another_purchase(self):
  with patch.object(server,'resolve_image_config',return_value={'provider':'modelscope','api_key':'fixture'}),patch.object(server,'image_dispatcher',side_effect=TimeoutError('timeout')) as generate:
   with self.assertRaises(TimeoutError) as first:task_cover.action(server,'original','generate',{'operation_id':'pending-once','prompt':'新词'})
   with self.assertRaises(ValueError) as second:task_cover.action(server,'original','generate',{'operation_id':'pending-once','prompt':'新词'})
  self.assertEqual(first.exception.task_id,second.exception.task_id);generate.assert_called_once()
 def test_direct_captions_and_repack_fork_before_first_write_and_repack_retry_reuses_result(self):
  import http.client,threading
  task_cover.write(self.folder/'03-shots.json',[]);before=self.snapshot()
  httpd=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);worker=threading.Thread(target=httpd.serve_forever,daemon=True);worker.start()
  def request(path,body):
   c=http.client.HTTPConnection('127.0.0.1',httpd.server_port,timeout=5);c.request('POST',path,json.dumps(body),{'Content-Type':'application/json'});r=c.getresponse();v=json.loads(r.read());status=r.status;c.close();self.assertEqual(status,200,v);return v
  def export(folder,*args):
   value={'ok':True,'draft_dir':str(self.root/'drafts'/folder.name)};task_cover.write(folder/'06-draft-meta.json',value);return value
  def captions(folder,*args):task_cover.write(folder/'05-captions.json',{'edited':True});return {'ok':True}
  try:
   with patch.object(server,'load_settings',return_value={'jianying':{'draft_path':str(self.root/'drafts')}}),patch.object(server,'export_jianying_draft',side_effect=export) as output,patch.object(server,'save_captions',side_effect=captions):
    sub=request('/api/task/original/captions',{'items':[],'operation_id':'caption-once'})
    self.assertNotEqual(sub['task_id'],'original');self.assertTrue((self.root/'tasks'/sub['task_id']/'05-captions.json').exists())
    one=request('/api/task/original/repack',{'operation_id':'pack-once'});two=request('/api/task/original/repack',{'operation_id':'pack-once'})
    self.assertEqual(one['task_id'],two['task_id']);output.assert_called_once()
   self.assertEqual(self.snapshot(),before)
  finally:httpd.shutdown();httpd.server_close();worker.join(2)

if __name__=='__main__':unittest.main()
