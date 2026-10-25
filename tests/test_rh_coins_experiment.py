"""RH coin experiment acceptance: fake transport and temporary data only."""
import copy
import io
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
import urllib.error
from unittest.mock import patch
from PIL import Image
import rh_coins_experiment as experiment
import rh_coins_workflow as workflow


def graph():
    return {
        '1':{'class_type':'UNETLoader','inputs':{'unet_name':'qwen_image_fp8.safetensors','weight_dtype':'default'}},
        '2':{'class_type':'CLIPLoader','inputs':{'clip_name':'qwen_2.5_vl_7b.safetensors','type':'qwen_image','device':'default'}},
        '3':{'class_type':'VAELoader','inputs':{'vae_name':'qwen_image_vae.safetensors'}},
        '4':{'class_type':'CLIPTextEncode','inputs':{'text':'original','clip':['2',0]}},
        '5':{'class_type':'CLIPTextEncode','inputs':{'text':'','clip':['2',0]}},
        '6':{'class_type':'EmptySD3LatentImage','inputs':{'width':1024,'height':1024,'batch_size':1}},
        '7':{'class_type':'KSampler','inputs':{'model':['1',0],'positive':['4',0],'negative':['5',0],'latent_image':['6',0],
            'seed':42,'steps':20,'cfg':4,'sampler_name':'euler','scheduler':'simple','denoise':1}},
        '8':{'class_type':'VAEDecode','inputs':{'samples':['7',0],'vae':['3',0]}},
        '9':{'class_type':'SaveImage','inputs':{'images':['8',0],'filename_prefix':'ComfyUI'}}}


class WorkflowTests(unittest.TestCase):
    def test_build_fixes_one_image_prompt_dimensions_and_seed_without_changing_snapshot(self):
        original=graph();before=copy.deepcopy(original)
        built=workflow.build_graph(original,'只拍背影，不露人脸','9:16',123)
        self.assertEqual(built['4']['inputs']['text'],'只拍背影，不露人脸')
        self.assertEqual(built['6']['inputs'],{'width':576,'height':1024,'batch_size':1})
        self.assertEqual(built['7']['inputs']['seed'],123)
        self.assertEqual(original,before)

    def test_unknown_nodes_extra_outputs_batch_and_cycles_rejected(self):
        changes=[lambda g:g.update({'10':{'class_type':'RH_GPT_Image','inputs':{}}}),
                 lambda g:g.update({'10':copy.deepcopy(g['9'])}),
                 lambda g:g['6']['inputs'].update(batch_size=3),
                 lambda g:g['7']['inputs'].update(model=['7',0]),
                 lambda g:g['1']['inputs'].update(unet_name='https://evil.invalid/a'),
                 lambda g:g['1'].update(class_type='SomeEncryptedNode')]
        for change in changes:
            with self.subTest(change=change):
                value=graph();change(value)
                with self.assertRaises(ValueError):workflow.audit_graph(value)

    def test_unknown_fields_and_disconnected_branches_rejected(self):
        value=graph();value['7']['inputs']['api_key']='fixture'
        with self.assertRaises(ValueError):workflow.audit_graph(value)
        value=graph();value['10']=copy.deepcopy(value['3'])
        with self.assertRaises(ValueError):workflow.audit_graph(value)

    def test_malformed_types_are_reported_as_invalid_graph(self):
        for change in (lambda g:g['1'].update(class_type={}),lambda g:g['7']['inputs'].update(model=[{},0])):
            value=graph();change(value)
            with self.assertRaises(ValueError):workflow.audit_graph(value)


class ExperimentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.calls=[];self.mode='ok';self.queried=False
        self.backend=SimpleNamespace(DATA_DIR=self.root,_rh_coins_post_json=self.transport)
        self.body={'operation_id':'a'*32,'prompt':'书房里的旧报纸，只拍背影','ratio':'9:16'}
        buffer=io.BytesIO();Image.new('RGB',(32,48),'blue').save(buffer,'PNG');self.png=buffer.getvalue()
        self.original=self.root/'settings.json';self.original.write_text('{"image":{"provider":"runninghub","api_key":"existing-g2"}}')

    def transport(self,url,headers,body,**kwargs):
        payload=json.loads(body);self.calls.append((url,payload))
        if url.endswith('/accountStatus'):
            self.assertEqual(payload,{'apikey':'fixture-member-key'})
            return 200,json.dumps({'code':0,'data':{'remainCoins':'73100','remainMoney':'0.001','apiType':'NORMAL'}})
        if url.endswith('/getJsonApiFormat'):
            if self.mode=='bad-check':return 200,json.dumps({'code':0,'data':{'prompt':'{}'}})
            return 200,json.dumps({'code':0,'data':{'prompt':json.dumps(graph())}})
        if url.endswith('/create'):
            saved=json.loads((experiment.directory(self.backend)/'jobs'/self.body['operation_id']/'job.json').read_text('utf8'))
            self.assertEqual(saved['status'],'submitting')
            if self.mode=='timeout':raise TimeoutError('private-key must never be exposed')
            if self.mode=='reject':return 200,json.dumps({'code':416,'msg':'private platform body'})
            if self.mode=='id-error':return 200,json.dumps({'code':999,'data':{'taskId':'original-rh-task'}})
            return 200,json.dumps({'code':0,'data':{'taskId':'original-rh-task','taskStatus':'QUEUED'}})
        if url.endswith('/outputs'):
            if not self.queried:self.queried=True;return 200,json.dumps({'code':804,'msg':'RUNNING'})
            return 200,json.dumps({'code':0,'data':[{'fileUrl':'https://fixture.invalid/image.png','fileType':'png','nodeId':'9'}]})
        raise AssertionError('Unexpected endpoint '+url)

    def ready(self):
        experiment.configure(self.backend,{'enabled':True,'api_key':'fixture-member-key','member_key_confirmed':True,'web_tested':True})
        return experiment.check(self.backend)

    def test_default_off_and_key_never_in_public_state_or_existing_settings(self):
        before=self.original.read_bytes();self.assertFalse(experiment.state(self.backend)['enabled'])
        with self.assertRaises(ValueError):experiment.submit(self.backend,self.body)
        self.assertEqual(self.calls,[]);value=self.ready()
        self.assertTrue(value['checked']);self.assertEqual(value['account']['remainCoins'],'73100')
        self.assertNotIn('fixture-member-key',json.dumps(value));self.assertEqual(before,self.original.read_bytes())
        self.assertTrue(all(not url.endswith('/create') for url,_ in self.calls))

    def test_create_uses_pinned_full_graph_one_image_and_is_idempotent(self):
        self.ready();first=experiment.submit(self.backend,self.body);second=experiment.submit(self.backend,self.body)
        self.assertEqual(first['taskId'],'original-rh-task');self.assertEqual(first,second)
        payload=next(data for url,data in self.calls if url.endswith('/create'))
        self.assertEqual(payload['nodeInfoList'],[])
        sent=json.loads(payload['workflow']);self.assertEqual(sent['4']['inputs']['text'],self.body['prompt'])
        self.assertEqual(sent['6']['inputs']['batch_size'],1)
        self.assertEqual(sum(url.endswith('/create') for url,_ in self.calls),1)
        with self.assertRaises(ValueError):experiment.submit(self.backend,{**self.body,'prompt':'changed'})

    def test_unknown_submit_is_durable_and_blocks_another_operation(self):
        self.ready();self.mode='timeout';value=experiment.submit(self.backend,self.body)
        self.assertEqual(value['status'],'unknown');self.assertNotIn('private-key',json.dumps(value))
        self.assertEqual(experiment.submit(self.backend,self.body)['status'],'unknown')
        with self.assertRaisesRegex(ValueError,'不明|在途'):experiment.submit(self.backend,{**self.body,'operation_id':'b'*32})
        self.assertEqual(sum(url.endswith('/create') for url,_ in self.calls),1)

    def test_response_with_id_is_saved_even_if_code_is_error(self):
        self.ready();self.mode='id-error';value=experiment.submit(self.backend,self.body)
        self.assertEqual(value['taskId'],'original-rh-task')
        self.assertIn(value['status'],('pending','unknown'))

    def test_platform_rejection_is_clear_and_has_no_secret(self):
        self.ready();self.mode='reject';value=experiment.submit(self.backend,self.body)
        self.assertEqual(value['status'],'rejected');self.assertIn('钱包',value['error'])
        self.assertNotIn('private platform body',json.dumps(value))

    def test_key_change_and_failed_recheck_invalidate_old_audit(self):
        self.ready();self.mode='bad-check'
        with self.assertRaises(ValueError):experiment.check(self.backend)
        self.assertFalse(experiment.state(self.backend)['checked'])
        with self.assertRaises(ValueError):experiment.submit(self.backend,self.body)
        self.mode='ok';self.ready()
        experiment.configure(self.backend,{'api_key':'another-key'})
        self.assertFalse(experiment.state(self.backend)['checked'])

    def test_disabled_can_query_download_and_export_original_without_regeneration(self):
        self.ready();experiment.submit(self.backend,self.body)
        experiment.configure(self.backend,{'enabled':False})
        self.assertEqual(experiment.query(self.backend,self.body['operation_id'])['status'],'running')
        with patch.object(experiment.task_cover,'image_bytes',return_value=self.png):
            value=experiment.query(self.backend,self.body['operation_id'])
        self.assertEqual(value['status'],'ok')
        self.assertEqual(experiment.media(self.backend,self.body['operation_id']).read_bytes(),self.png)
        first=experiment.export_image(self.backend,{'operation_id':self.body['operation_id'],'directory':str(self.root)})
        second=experiment.export_image(self.backend,{'operation_id':self.body['operation_id'],'directory':str(self.root)})
        self.assertNotEqual(first['path'],second['path']);self.assertEqual(Path(first['path']).read_bytes(),self.png)
        self.assertEqual(sum(url.endswith('/create') for url,_ in self.calls),1)

    def test_download_failure_keeps_original_result_and_recovers(self):
        self.ready();experiment.submit(self.backend,self.body);self.queried=True
        with patch.object(experiment.task_cover,'image_bytes',side_effect=OSError('download')):
            with self.assertRaises(RuntimeError):experiment.query(self.backend,self.body['operation_id'])
        self.assertEqual(experiment.state(self.backend)['jobs'][0]['status'],'download_pending')
        before=len(self.calls)
        with patch.object(experiment.task_cover,'image_bytes',return_value=self.png):
            self.assertEqual(experiment.query(self.backend,self.body['operation_id'])['status'],'ok')
        self.assertEqual(len(self.calls),before)

    def test_bad_input_no_submit_and_no_account_change(self):
        self.ready()
        for body in [{**self.body,'ratio':'all'},{**self.body,'operation_id':'../bad'},{**self.body,'prompt':''}]:
            with self.assertRaises(ValueError):experiment.submit(self.backend,body)
        self.assertFalse(any(url.endswith('/create') for url,_ in self.calls))

    def test_status_error_is_not_proof_of_terminal_failure(self):
        self.ready();experiment.submit(self.backend,self.body)
        self.backend._rh_coins_post_json=lambda *args,**kwargs:(200,json.dumps({'code':805}))
        value=experiment.query(self.backend,self.body['operation_id'])
        self.assertEqual(value['status'],'unknown')
        self.assertEqual(value['taskId'],'original-rh-task')
        with self.assertRaises(ValueError):experiment.submit(self.backend,{**self.body,'operation_id':'b'*32})

    def test_http_error_body_task_id_is_retained_before_classifying_failure(self):
        self.ready();original=self.backend._rh_coins_post_json
        def transport(url,headers,body,**kwargs):
            if url.endswith('/create'):
                return experiment.http_post_json(url,headers,body,**kwargs)
            return original(url,headers,body,**kwargs)
        self.backend._rh_coins_post_json=transport
        response=json.dumps({'code':999,'msg':'private credential details','data':{'taskId':'accepted-before-error'}}).encode()
        error=urllib.error.HTTPError('https://www.runninghub.cn/task/openapi/create',500,'error',{},io.BytesIO(response))
        with patch('urllib.request.urlopen',side_effect=error):value=experiment.submit(self.backend,self.body)
        self.assertEqual(value.get('taskId'),'accepted-before-error')
        self.assertNotIn('private credential',json.dumps(experiment.state(self.backend)))

    def test_terminal_failure_requires_separate_status_confirmation(self):
        self.ready();experiment.submit(self.backend,self.body)
        def transport(url,*args,**kwargs):
            return 200,json.dumps({'code':0,'data':'FAILED'} if url.endswith('/status') else {'code':805})
        self.backend._rh_coins_post_json=transport
        self.assertEqual(experiment.query(self.backend,self.body['operation_id'])['status'],'failed')

    def test_account_preflight_network_failure_is_known_not_submitted(self):
        self.ready()
        self.backend._rh_coins_post_json=lambda *args,**kwargs:(_ for _ in ()).throw(TimeoutError('private connection'))
        with self.assertRaisesRegex(ValueError,'未提交'):experiment.submit(self.backend,self.body)
        self.assertEqual(experiment.state(self.backend)['jobs'],[])


if __name__=='__main__':unittest.main()
