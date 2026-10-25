import copy,json,unittest
from pathlib import Path
import rh_workflow_graphs as graphs
import rh_coins_workflow as workflow
FIXTURES=Path(__file__).parent/'fixtures/rh-workflows'
def fixture(family):return json.loads(next(FIXTURES.glob(family+'-*.json')).read_text('utf8'))
class GraphTests(unittest.TestCase):
 def test_popular_qwen_chinese_graph_keeps_its_model_and_uses_full_prompt(self):
  raw=fixture('qwen-chinese');prepared=graphs.prepare(raw);info=prepared['summary']
  self.assertEqual(info['kind'],'qwen');self.assertGreater(info['removedNodes'],0)
  built=workflow.build_graph(prepared['graph'],'古人十件雅事，不露脸','9:16',777)
  self.assertEqual(built[info['promptNode']]['inputs']['text'],'古人十件雅事，不露脸')
 def test_real_flux_is_single_local_graph_without_prompt_api_branches(self):
  value=fixture('flux');original=copy.deepcopy(value);prepared=graphs.prepare(value);g=prepared['graph'];info=prepared['summary']
  self.assertEqual(info['kind'],'flux');self.assertEqual(value,original)
  self.assertFalse(any(n['class_type'].startswith('RH_') for n in g.values()))
  built=workflow.build_graph(g,'完整标题，不露脸','3:4',123)
  self.assertEqual(built[info['promptNode']]['inputs']['text'],'完整标题，不露脸')
  self.assertEqual(built[info['sizeNode']]['inputs'],{'width':768,'height':1024,'batch_size':1})
  self.assertEqual(built[info['seedNode']]['inputs']['noise_seed'],123)
 def test_real_sdxl_retains_checkpoint_and_negative_prompt(self):
  raw=fixture('sdxl');prepared=graphs.prepare(raw);g=prepared['graph'];info=prepared['summary']
  self.assertEqual(info['kind'],'sdxl');self.assertEqual(g['10'],raw['10'])
  self.assertIsInstance(g['23']['inputs']['text'],str)
  built=workflow.build_graph(g,'古人十件雅事','16:9',42)
  self.assertEqual(built['14']['inputs']['text'],'古人十件雅事');self.assertEqual(built['35']['inputs']['seed'],42)
 def test_connected_api_unknown_node_multi_output_and_reference_rejected(self):
  variants=[]
  g=fixture('flux');g['12']['class_type']='RH_GPT_Image';variants.append(g)
  g=fixture('sdxl');g['47']=copy.deepcopy(g['46']);variants.append(g)
  g=fixture('sdxl');g['689']['class_type']='LoadImage';variants.append(g)
  for g in variants:
   with self.subTest(g=g):
    with self.assertRaises(ValueError):graphs.prepare(g)
 def test_malformed_cycle_remote_model_and_batch_are_rejected(self):
  changes=[lambda g:g['10']['inputs'].update(ckpt_name='https://evil/a.safetensors'),lambda g:g['35']['inputs'].update(model=['35',0]),lambda g:g['689']['inputs'].update(batch_size=3)]
  for change in changes:
   g=fixture('sdxl');change(g)
   with self.assertRaises(ValueError):graphs.prepare(g)
 def test_negative_unrecognized_text_operator_is_not_silently_dropped(self):
  g=fixture('sdxl');g['673']['class_type']='RH_Prompter'
  with self.assertRaises(ValueError):graphs.prepare(g)
if __name__=='__main__':unittest.main()
