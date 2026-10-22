"""Single missing scene retry never discards successful scenes or resubmits unknown work."""
import base64,io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import server,task_queue

class RecoveryTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name);self.folder=self.root/'tasks'/'fixture';(self.folder/'covers').mkdir(parents=True)
  self.addCleanup(patch.stopall);patch.object(server,'DATA_DIR',self.root).start()
  patch.object(server,'load_settings',return_value={'image':{'provider':'runninghub'},'runninghub':{'api_key':'fixture'}}).start()
  out=io.BytesIO();Image.new('RGB',(24,32),'blue').save(out,'PNG');self.png=out.getvalue()
  (self.folder/'covers/1.png').write_bytes(self.png)
  self.write('03-shots.json',[{'idx':1,'text':'saved'},{'idx':6,'text':'missing'}])
  self.write('04-prompts.json',[{'idx':1,'desc_prompt':'saved'},{'idx':6,'desc_prompt':'missing visual'}])
  self.write('client_config.json',{'image':{'provider':'runninghub','ratio':'9:16','resolution':'1k'}})
  self.job={'status':'failed','provider':'runninghub','taskId':'old-fixture-id','prompt':'missing visual','ratio':'9:16','resolution':'1k'}
  self.write('image-jobs/6.json',self.job)
 def write(self,name,value):task_queue.atomic_json(self.folder/name,value)
 def retry(self,operation='fixture-operation'):
  import scene_image_recovery
  return scene_image_recovery.retry(server,'fixture',{'index':6,'operation_id':operation})
 def query(self):
  import scene_image_recovery
  return scene_image_recovery.retry(server,'fixture',{'index':6,'operation_id':'query-existing','query_only':True})
 def test_pending_success_is_downloaded_using_original_id_without_new_generation(self):
  job={**self.job,'status':'pending','credential':__import__('task_cover').credential(server.resolve_image_config(server.load_settings(),'runninghub'))}
  self.write('image-jobs/6.json',job)
  with patch('task_cover.query_provider',return_value={'status':'SUCCESS','results':[{'url':'https://fixture.invalid/image'}]}) as query,patch('task_cover.image_bytes',return_value=self.png),patch.object(server,'image_dispatcher',side_effect=AssertionError('no generation')):
   self.assertTrue(self.query()['ok']);self.assertTrue(self.query()['cached'])
  query.assert_called_once();self.assertEqual(query.call_args.args[2],'old-fixture-id')
  self.assertEqual((self.folder/'covers/6.png').read_bytes(),self.png)
  self.assertEqual(json.loads((self.folder/'image-jobs/6.json').read_text('utf8'))['status'],'ok')
 def test_query_confirmed_failure_updates_receipt_without_buying(self):
  job={**self.job,'status':'pending','credential':__import__('task_cover').credential(server.resolve_image_config(server.load_settings(),'runninghub'))}
  self.write('image-jobs/6.json',job)
  with patch('task_cover.query_provider',return_value={'status':'FAILED','failReason':'worker failed'}),patch.object(server,'image_dispatcher',side_effect=AssertionError('no generation')):
   self.assertTrue(self.query()['needs_retry'])
  self.assertEqual(json.loads((self.folder/'image-jobs/6.json').read_text('utf8'))['status'],'failed')
 def test_queued_query_releases_lease_and_preserves_queue_order(self):
  self.write('client_config.json',{'generate':{},'tts':{},'image':{'provider':'runninghub'}})
  queue=task_queue.get_queue(server);queue.enqueue('fixture')
  before=queue.get('fixture')['id']
  with patch.object(server,'image_dispatcher',side_effect=AssertionError('no generation')):self.assertTrue(self.query()['needs_retry'])
  self.assertEqual(queue.get('fixture')['id'],before);self.assertEqual(queue.get('fixture')['status'],'queued')
  self.assertNotIn('fixture',server.TASK_OPERATIONS)
 def test_download_failure_keeps_success_url_and_next_query_downloads_without_polling_or_purchase(self):
  self.write('image-jobs/6.json',{**self.job,'status':'download_pending','result':{'url':'https://fixture.invalid/saved'}})
  with patch('task_cover.query_provider',side_effect=AssertionError('no polling')),patch.object(server,'image_dispatcher',side_effect=AssertionError('no generation')),patch('task_cover.image_bytes',side_effect=[OSError('download interrupted'),self.png]):
   with self.assertRaises(OSError):self.query()
   self.assertTrue(self.query()['ok'])
 def test_query_replaces_an_empty_placeholder_without_overwriting_a_successful_image(self):
  (self.folder/'covers/6.png').write_bytes(b'')
  self.write('image-jobs/6.json',{**self.job,'status':'download_pending','result':{'url':'https://fixture.invalid/saved'}})
  with patch('task_cover.image_bytes',return_value=self.png),patch.object(server,'image_dispatcher',side_effect=AssertionError('no generation')):
   self.assertTrue(self.query()['ok'])
  self.assertEqual((self.folder/'covers/6.png').read_bytes(),self.png)
 def test_only_failed_index_is_retried_and_duplicate_operation_reuses_completed_file(self):
  before=(self.folder/'covers/1.png').read_bytes()
  with patch.object(server,'image_dispatcher',return_value={'b64':base64.b64encode(self.png).decode()}) as generate:
   result=self.retry();self.assertTrue(result['ok']);self.retry();self.retry('another-click')
  generate.assert_called_once();self.assertEqual(generate.call_args.args[1],'missing visual')
  self.assertEqual((self.folder/'covers/1.png').read_bytes(),before)
  archives=list((self.folder/'.image-retries').glob('*.receipt.json'));self.assertEqual(len(archives),1)
  self.assertEqual(json.loads(archives[0].read_text('utf8')),self.job)
 def test_unknown_or_pending_work_is_never_discarded(self):
  for status in ('unknown','pending','submitting','download_pending'):
   self.write('image-jobs/6.json',{**self.job,'status':status})
   with patch.object(server,'image_dispatcher',side_effect=AssertionError('must not buy')):
    with self.assertRaisesRegex(ValueError,'查图|状态不明|在途'):self.retry()
   self.assertEqual(json.loads((self.folder/'image-jobs/6.json').read_text('utf8'))['status'],status)
 def test_lost_response_unknown_receipt_and_same_operation_never_repurchase(self):
  with patch.object(server,'image_dispatcher',side_effect=TimeoutError('response lost')) as generate:
   with self.assertRaises(RuntimeError):self.retry()
   with self.assertRaises(RuntimeError):self.retry()
   with self.assertRaises(ValueError):self.retry('second-operation')
  self.assertEqual(generate.call_count,1)
  self.assertEqual(json.loads((self.folder/'image-jobs/6.json').read_text('utf8'))['status'],'unknown')
 def test_invalid_index_and_failed_durable_claim_do_not_touch_original_receipt(self):
  import scene_image_recovery
  with patch.object(server,'image_dispatcher',side_effect=AssertionError('must not buy')):
   with self.assertRaises(ValueError):scene_image_recovery.retry(server,'fixture',{'index':99,'operation_id':'fixture'})
   with patch.object(scene_image_recovery,'write',side_effect=OSError('disk failure')):
    with self.assertRaises(OSError):self.retry()
  self.assertEqual(json.loads((self.folder/'image-jobs/6.json').read_text('utf8')),self.job)
 def test_explicit_retry_uses_task_saved_engine_not_current_global_engine(self):
  with patch.object(server,'resolve_image_config',wraps=server.resolve_image_config) as resolve,patch.object(server,'image_dispatcher',return_value={'b64':base64.b64encode(self.png).decode()}):self.retry()
  self.assertTrue(any(c.args[1]=='runninghub' for c in resolve.call_args_list))
 def test_synchronous_provider_timeout_is_also_durable_and_cannot_restore_failed_record(self):
  self.write('client_config.json',{'image':{'provider':'gpt_image'}})
  with patch.object(server,'resolve_image_config',return_value={'provider':'gpt_image','api_key':'fixture','base_url':'https://fixture.invalid'}),patch.object(server,'image_dispatcher',side_effect=TimeoutError('lost sync response')) as generate:
   with self.assertRaises(RuntimeError):self.retry()
   self.assertEqual(json.loads((self.folder/'image-jobs/6.json').read_text('utf8'))['status'],'unknown')
   with self.assertRaises(ValueError):self.retry('second-operation')
  generate.assert_called_once()
 def test_confirmed_rejection_allows_a_new_explicit_operation_but_never_replays_old_one(self):
  with patch.object(server,'image_dispatcher',side_effect=[server.ImageSubmissionRejected('rejected'),{'b64':base64.b64encode(self.png).decode()}]) as generate:
   with self.assertRaises(RuntimeError) as caught:self.retry()
   self.assertTrue(caught.exception.retryable)
   with self.assertRaises(RuntimeError) as duplicate:self.retry()
   self.assertTrue(duplicate.exception.retryable);self.assertEqual(generate.call_count,1)
   self.assertTrue(self.retry('new-explicit-operation')['ok'])
  self.assertEqual(generate.call_count,2)
 def test_http_requires_session_origin_bounded_body_and_never_calls_supplier_for_cached_image(self):
  import http.client,os,threading,scene_image_recovery
  from http.server import ThreadingHTTPServer
  scene_image_recovery.install(server)
  with patch.dict(os.environ,{'APP074_SESSION_TOKEN':'fixture-session'}):
   httpd=ThreadingHTTPServer(('127.0.0.1',0),server.Handler);thread=threading.Thread(target=httpd.serve_forever,daemon=True);thread.start()
   try:
    def request(data,auth=True,origin=None,raw=None):
     c=http.client.HTTPConnection('127.0.0.1',httpd.server_port,timeout=5);headers={'Content-Type':'application/json'}
     if auth:headers['Cookie']='app074_session=fixture-session'
     if origin:headers['Origin']=origin
     c.request('POST','/api/task/fixture/retry-image',json.dumps(data) if raw is None else raw,headers)
     response=c.getresponse();status=response.status;response.read();c.close();return status
    body={'index':1,'operation_id':'cached-request'}
    with patch.object(server,'image_dispatcher',side_effect=AssertionError('no paid request')):
     self.assertEqual(request(body,auth=False),403)
     self.assertEqual(request(body,origin='https://foreign.invalid'),403)
     self.assertEqual(request(body),200)
     self.assertEqual(request([],raw='['),409)
     self.assertEqual(request({},raw='x'*4097),413)
   finally:httpd.shutdown();httpd.server_close();thread.join(5)

if __name__=='__main__':unittest.main()
