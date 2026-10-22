"""Independent opt-in reference experiments. Every provider transport is fake."""
import base64
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import server
import modelscope_reference_experiment as experiment


class ReferenceExperimentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.addCleanup(patch.stopall)
        patch.object(server,'DATA_DIR',self.root).start()
        self.original={'image':{'provider':'modelscope'},'modelscope':{'tokens':['fixture-token'],'model':'ordinary-model','auto_fallback_gpt':True}}
        patch.object(server,'load_settings',return_value=self.original).start()
        self.post=patch.object(server,'_http_post_json',return_value=(200,json.dumps({'task_id':'supplier-original'}))).start()
        self.get=patch.object(server,'_http_get_json',return_value=(200,json.dumps({'task_status':'RUNNING'}))).start()
        buffer=io.BytesIO();Image.new('RGB',(32,48),'blue').save(buffer,'PNG');self.png=buffer.getvalue()
        self.body={'operation_id':'a'*32,'prompt':'保持产品外观，把背景换成木桌','reference':'data:image/png;base64,'+base64.b64encode(self.png).decode()}

    def enable(self):return experiment.configure(server,{'enabled':True})

    def test_disabled_by_default_and_toggle_does_not_modify_existing_providers(self):
        self.assertFalse(experiment.state(server)['enabled'])
        with self.assertRaisesRegex(ValueError,'启用'):experiment.submit(server,self.body)
        self.enable();self.assertTrue(experiment.state(server)['enabled'])
        self.assertEqual(self.original['modelscope']['model'],'ordinary-model')
        self.assertTrue(self.original['modelscope']['auto_fallback_gpt'])
        self.post.assert_not_called();self.get.assert_not_called()
        with self.assertRaises(ValueError):experiment.configure(server,{'enabled':'true'})

    def test_single_reference_uses_edit_model_and_preserves_receipt_on_repeat(self):
        self.enable();first=experiment.submit(server,self.body);second=experiment.submit(server,self.body)
        self.assertEqual(first['taskId'],'supplier-original');self.assertEqual(second['taskId'],first['taskId'])
        self.post.assert_called_once();self.get.assert_not_called()
        args=self.post.call_args.args;payload=json.loads(args[2])
        self.assertEqual(args[0],'https://api-inference.modelscope.cn/v1/images/generations')
        self.assertEqual(payload['model'],'Qwen/Qwen-Image-Edit-2511')
        self.assertEqual(payload['image_url'],[self.body['reference']]);self.assertEqual(payload['prompt'],self.body['prompt'])
        self.assertEqual(self.original['modelscope']['model'],'ordinary-model')
        self.assertNotIn('fixture-token',json.dumps(experiment.state(server)))

    def test_unknown_submission_cannot_be_resubmitted_with_another_id(self):
        self.enable();self.post.side_effect=TimeoutError('private-token timeout')
        result=experiment.submit(server,self.body);self.assertEqual(result['status'],'unknown')
        same=experiment.submit(server,self.body);self.assertEqual(same['status'],'unknown')
        with self.assertRaisesRegex(ValueError,'在途|不明'):experiment.submit(server,{**self.body,'operation_id':'b'*32})
        self.post.assert_called_once();self.assertNotIn('private-token',json.dumps(result))

    def test_explicit_rate_rejection_does_not_lock_future_deliberate_tests(self):
        self.enable();self.post.side_effect=RuntimeError('HTTP 429: private rate limit body')
        result=experiment.submit(server,self.body);self.assertEqual(result['status'],'rejected')
        self.post.side_effect=None
        next_result=experiment.submit(server,{**self.body,'operation_id':'b'*32})
        self.assertEqual(next_result['status'],'pending');self.assertEqual(self.post.call_count,2)
        self.assertNotIn('private rate',str(result))

    def test_disable_blocks_new_submissions_but_keeps_existing_query_and_cached_image(self):
        self.enable();experiment.submit(server,self.body);experiment.configure(server,{'enabled':False})
        with self.assertRaisesRegex(ValueError,'启用'):experiment.submit(server,{**self.body,'operation_id':'b'*32})
        self.get.return_value=(200,json.dumps({'task_status':'SUCCEED','output_images':['https://fixture.invalid/result.png']}))
        with patch('task_cover.image_bytes',return_value=self.png):
            result=experiment.query(server,self.body['operation_id'])
        self.assertEqual(result['status'],'ok');self.assertTrue(experiment.media(server,self.body['operation_id']).is_file())
        self.assertEqual(experiment.query(server,self.body['operation_id'])['status'],'ok')
        self.get.assert_called_once();self.post.assert_called_once()

    def test_changed_operation_content_and_invalid_image_reject_before_transport(self):
        self.enable();experiment.submit(server,self.body)
        with self.assertRaises(ValueError):experiment.submit(server,{**self.body,'prompt':'different'})
        with self.assertRaises(ValueError):experiment.submit(server,{**self.body,'operation_id':'../../unsafe'})
        self.post.assert_called_once()

    def test_running_query_never_submits_again_and_account_change_does_not_query_wrong_account(self):
        self.enable();experiment.submit(server,self.body)
        self.assertEqual(experiment.query(server,self.body['operation_id'])['status'],'pending')
        self.original['modelscope']['tokens']=['different-fixture-token']
        with self.assertRaisesRegex(ValueError,'凭据|Token'):experiment.query(server,self.body['operation_id'])
        self.get.assert_called_once();self.post.assert_called_once()

    def test_original_modelscope_dispatcher_behavior_is_unchanged(self):
        self.enable()
        cfg=server.resolve_image_config(self.original,'modelscope')
        self.assertEqual(cfg['model'],'ordinary-model')
        with patch.object(server,'_call_modelscope',return_value={'url':'https://fixture.invalid/ordinary.png'}) as original:
            result=server.image_dispatcher(cfg,'normal')
        original.assert_called_once();self.assertEqual(result['provider'],'modelscope')
        with self.assertRaisesRegex(ValueError,'不支持参考图'):server.image_dispatcher(cfg,'normal',reference_data_url=self.body['reference'])


if __name__=='__main__':unittest.main()
