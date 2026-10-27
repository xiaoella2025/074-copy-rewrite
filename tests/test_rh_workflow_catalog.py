import json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import rh_coins_experiment as exp
import rh_workflow_catalog as catalog
import rh_workflow_provider as provider
from test_rh_workflow_graphs import fixture
from image_motion import read,write
class CatalogTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.addCleanup(patch.stopall)
  self.root=Path(self.temp.name);self.calls=[]
  self.backend=SimpleNamespace(DATA_DIR=self.root,_rh_coins_post_json=self.post)
  exp.configure(self.backend,{'api_key':'fixture-member-key','enabled':True,'member_key_confirmed':True,'web_tested':True})
 def post(self,url,headers,body,**kw):
  data=json.loads(body);self.calls.append(url)
  if url.endswith('/accountStatus'):return 200,json.dumps({'code':0,'data':{'remainCoins':'100'}})
  if url.endswith('/getJsonApiFormat'):
   family='sdxl' if data['workflowId']=='1912776705101234178' else 'flux'
   return 200,json.dumps({'code':0,'data':{'prompt':json.dumps(fixture(family))}})
  raise AssertionError('No submit allowed '+url)
 def test_builtin_families_exist_and_save_does_not_generate(self):
  self.assertTrue({'qwen-simple','qwen-native','flux-native','sdxl-native'}<=catalog.entries(self.backend).keys())
  exp.configure(self.backend,{'preset':'flux-native','web_tested':True});exp.check(self.backend)
  cfg=provider.resolve(self.backend);self.assertEqual(cfg['workflow_id'],'1819583592967110658');self.assertTrue(cfg['checked'])
  self.assertFalse(any(url.endswith('/create') for url in self.calls))
 def test_custom_link_add_is_persistent_without_changing_default_or_key(self):
  before=exp.config(self.backend).copy()
  result=catalog.add(self.backend,{'name':'我的SDXL','url':'https://www.runninghub.cn/post/1912776705101234178'})
  self.assertEqual(exp.config(self.backend),before);self.assertIn('custom-1912776705101234178',catalog.entries(self.backend))
  self.assertIn('我的SDXL',json.dumps(result,ensure_ascii=False));self.assertNotIn('fixture-member-key',json.dumps(result))
 def test_explicit_cover_and_scene_workflows_can_differ(self):
  for key in ['flux-native','sdxl-native']:
   exp.configure(self.backend,{'preset':key,'web_tested':True});exp.check(self.backend)
  first=provider.resolve(self.backend,'flux-native');second=provider.resolve(self.backend,'sdxl-native')
  self.assertNotEqual(first['workflow_id'],second['workflow_id']);self.assertEqual(first['preset'],'flux-native')
  self.assertTrue(first['checked']);self.assertTrue(second['checked'])
 def test_cover_and_creative_keep_their_explicit_workflow_selection(self):
  import server,task_cover,creative_workflows as creative
  for key in ['flux-native','sdxl-native']:
   exp.configure(self.backend,{'preset':key,'web_tested':True});exp.check(self.backend)
  with patch.object(server,'DATA_DIR',self.root),patch.object(server,'load_settings',return_value={}),patch.object(server,'resolve_image_config',side_effect=lambda settings,selected=None:provider.resolve(server)):
   folder=self.root/'tasks/catalog-cover';folder.mkdir(parents=True)
   write(folder/'client_config.json',{'cover':{'mode':'title','provider':'runninghub_workflow','workflow':'flux-native'}})
   write(folder/'02-meta.json',{'title':'title'})
   self.assertEqual(task_cover.view(server,'catalog-cover')['workflow'],'flux-native')
   self.assertEqual(creative.image_config(server,{}, {'imageProvider':'runninghub_workflow','imageWorkflow':'flux-native'})['preset'],'flux-native')
   task_cover.action(server,'catalog-cover','save',{'slot':1,'workflow':'sdxl-native'})
   self.assertEqual(task_cover.view(server,'catalog-cover')['workflow'],'sdxl-native')
   self.assertEqual(read(folder/'client_config.json',{})['cover']['workflow'],'sdxl-native')

 def test_confirming_after_check_survives_later_default_workflow_change(self):
  exp.configure(self.backend,{'preset':'flux-native','web_tested':False});exp.check(self.backend)
  exp.configure(self.backend,{'web_tested':True})
  exp.configure(self.backend,{'preset':'sdxl-native','web_tested':True});exp.check(self.backend)
  self.assertTrue(provider.resolve(self.backend,'flux-native')['web_tested'])
 def test_verified_api_output_unlocks_only_matching_graph_and_key(self):
  exp.configure(self.backend,{'preset':'flux-native','web_tested':False});exp.check(self.backend)
  saved=catalog.cached(self.backend,'flux-native')
  proof={'status':'ok','workflowId':saved['workflowId'],'sourceSha256':saved['sourceSha256'],
         'credential':saved['credential'],'taskId':'real-task-123','imageSha256':'a'*64,'spentCoins':6,
         'costObservations':[{'taskId':'second-task','consumeCoins':21}]}
  write(catalog.cache_path(self.backend,'flux-native'),{**saved,'api_test':proof})
  cfg=provider.resolve(self.backend,'flux-native')
  self.assertFalse(cfg['web_tested']);self.assertTrue(cfg['api_tested']);self.assertTrue(cfg['live_tested'])
  self.assertTrue(provider.public_config(self.backend)['configured'])
  self.assertTrue(exp.state(self.backend)['live_tested'])
  self.assertEqual(catalog.public_entries(self.backend)[2]['api_test_cost'],6)
  self.assertEqual(catalog.public_entries(self.backend)[2]['api_test_cost_range'],[6,21])
  exp.check(self.backend)
  self.assertTrue(provider.resolve(self.backend,'flux-native')['api_tested'])
  changed=read(catalog.cache_path(self.backend,'flux-native'),{})
  write(catalog.cache_path(self.backend,'flux-native'),{**changed,'sourceSha256':'different'})
  self.assertFalse(provider.resolve(self.backend,'flux-native')['live_tested'])
  exp.configure(self.backend,{'api_key':'different-key'})
  self.assertFalse(provider.resolve(self.backend,'flux-native')['checked'])
 def test_invalid_url_unknown_nodes_and_wrong_credentials_do_not_replace_config(self):
  before=exp.config(self.backend).copy()
  for url in ['https://evil.invalid/post/123','../123','https://www.runninghub.cn/post/1912776705101234178?apiKey=secret']:
   with self.assertRaises(ValueError):catalog.add(self.backend,{'name':'custom','url':url})
  self.assertEqual(exp.config(self.backend),before);self.assertEqual(self.calls,[])
  exp.configure(self.backend,{'preset':'sdxl-native','web_tested':True});exp.check(self.backend)
  exp.configure(self.backend,{'api_key':'different-key'})
  self.assertFalse(provider.resolve(self.backend,'sdxl-native')['checked'])
if __name__=='__main__':unittest.main()
