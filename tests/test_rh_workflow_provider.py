"""Formal provider integration, using only temporary data and fake HTTP."""
import io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import server
import rh_coins_experiment as experiment
import rh_coins_workflow as graph_tools
import rh_workflow_provider as provider
from image_motion import write,read
from test_rh_coins_experiment import graph


class FormalProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.addCleanup(patch.stopall)
        self.root=Path(self.temp.name);patch.object(server,'DATA_DIR',self.root).start()
        self.settings={'image':{'provider':'modelscope'},'runninghub':{'api_key':'wallet-original','base_url':'https://www.runninghub.ai','model':'rh-image-g2'}}
        patch.object(server,'load_settings',return_value=self.settings).start()
        experiment.configure(server,{'enabled':True,'api_key':'member-key-fixture','member_key_confirmed':True,'web_tested':True})
        cfg=experiment.config(server)
        write(experiment.directory(server)/'checked.json',{'valid':True,'credential':experiment.credential(cfg),'preset':cfg['preset'],
            'graph':graph(),'workflowSha256':graph_tools.digest(graph()),'summary':graph_tools.audit_graph(graph())})
        self.events=[];self.fail=False
        patch.object(server,'_rh_coins_post_json',self.post,create=True).start()

    def post(self,url,headers,body,**kwargs):
        value=json.loads(body);self.events.append((url,value))
        self.assertEqual(value['apiKey'],'member-key-fixture')
        if url.endswith('/create'):
            if self.fail:raise TimeoutError('private upstream body')
            return 200,json.dumps({'code':0,'data':{'taskId':'formal-'+str(sum(x[0].endswith('/create') for x in self.events))}})
        if url.endswith('/outputs'):return 200,json.dumps({'code':0,'data':[{'fileType':'png','fileUrl':'https://fixture.invalid/formal.png'}]})
        raise AssertionError(url)

    def test_resolver_uses_member_config_and_does_not_change_wallet_settings(self):
        cfg=server.resolve_image_config(self.settings,'runninghub_workflow')
        self.assertEqual(cfg['api_key'],'member-key-fixture');self.assertEqual(cfg['base_url'],experiment.API)
        self.assertEqual(self.settings['runninghub']['api_key'],'wallet-original')
        self.assertEqual(provider.public_config(server)['configured'],True)
        self.assertNotIn('member-key-fixture',json.dumps(provider.public_config(server)))

    def test_dispatch_keeps_complete_prompt_and_callback_precedes_polling(self):
        cfg=server.resolve_image_config(self.settings,'runninghub_workflow');callback=[]
        def remembered(tid,actual):callback.append((tid,actual['provider'],len(self.events)))
        prompt='主标题「古人十件雅事」，副标题完整保留，3:4封面；人物完全背对镜头，不露脸。'
        value=server.image_dispatcher(cfg,prompt,ratio='3:4',on_task_id=remembered)
        self.assertEqual(value['provider'],'runninghub_workflow');self.assertEqual(callback,[('formal-1','runninghub_workflow',1)])
        frozen=json.loads(self.events[0][1]['workflow']);self.assertEqual(frozen['4']['inputs']['text'],prompt)
        self.assertEqual(frozen['6']['inputs']['width'],768)
        self.assertEqual(len(list((experiment.directory(server)/'provider-jobs').glob('*/job.json'))),1)

    def test_batch_repeated_request_queries_original_and_does_not_buy_again(self):
        cfg=server.resolve_image_config(self.settings,'runninghub_workflow');folder=self.root/'tasks/fixture';folder.mkdir(parents=True)
        first=server.batch_image_result(cfg,'相同原文',1,'9:16','1k',folder)
        second=server.batch_image_result(cfg,'相同原文',1,'9:16','1k',folder)
        self.assertEqual(first,second)
        self.assertEqual(sum(url.endswith('/create') for url,_ in self.events),1)

    def test_unknown_submission_is_journaled_and_not_retried_by_batch(self):
        cfg=server.resolve_image_config(self.settings,'runninghub_workflow');folder=self.root/'tasks/fixture';folder.mkdir(parents=True)
        self.fail=True
        with self.assertRaises(RuntimeError):server.batch_image_result(cfg,'原文',1,'9:16','1k',folder)
        with self.assertRaises(RuntimeError):server.batch_image_result(cfg,'原文',1,'9:16','1k',folder)
        self.assertEqual(sum(url.endswith('/create') for url,_ in self.events),1)
        receipts=list((experiment.directory(server)/'provider-jobs').glob('*/job.json'))
        self.assertEqual(read(receipts[0],{})['status'],'unknown')
        self.assertNotIn('private upstream body',receipts[0].read_text('utf8'))

    def test_disabled_blocks_new_generation_but_original_query_remains_available(self):
        cfg=server.resolve_image_config(self.settings,'runninghub_workflow')
        experiment.configure(server,{'enabled':False})
        with self.assertRaises(server.ImageSubmissionRejected):provider.generate(server,provider.resolve(server),'原文','1:1','1k')
        self.assertEqual(provider.query(server,cfg,'old-id')['status'],'SUCCESS')
        self.assertFalse(any(url.endswith('/create') for url,_ in self.events))

    def test_unverified_candidate_explains_preflight_without_submitting(self):
        import task_cover
        cfg=provider.resolve(server)
        cfg['checked']=False
        with self.assertRaisesRegex(server.ImageSubmissionRejected,'完整图未核对') as error:
            provider.generate(server,cfg,'封面画面','9:16','1k')
        self.assertIn('未提交生成',task_cover.cover_error(error.exception)['body'])
        cfg['checked']=True;cfg['web_tested']=False
        with self.assertRaisesRegex(server.ImageSubmissionRejected,'尚未网页实测') as error:
            provider.generate(server,cfg,'封面画面','9:16','1k')
        self.assertIn('未提交生成',task_cover.cover_error(error.exception)['body'])
        self.assertEqual(self.events,[])

    def test_four_three_ratio_and_unsupported_resolution_are_bounded(self):
        cfg=provider.resolve(server)
        with self.assertRaises(server.ImageSubmissionRejected):provider.generate(server,cfg,'原文','4:3','4k')
        value=provider.generate(server,cfg,'原文','4:3','1k')
        self.assertEqual(value['provider'],'runninghub_workflow')
        self.assertEqual(json.loads(self.events[0][1]['workflow'])['6']['inputs'],{'width':1024,'height':768,'batch_size':1})

    def test_poll_pause_is_not_converted_into_failure_and_keeps_receipt(self):
        cfg=provider.resolve(server)
        def remembered(*args):raise InterruptedError('pause')
        with self.assertRaises(InterruptedError):provider.generate(server,cfg,'原文','1:1','1k',remembered)
        receipt=read(next((experiment.directory(server)/'provider-jobs').glob('*/job.json')),{})
        self.assertEqual(receipt['taskId'],'formal-1');self.assertEqual(receipt['status'],'pending')

    def test_known_rejection_retains_safe_reason_and_rejection_type(self):
        cfg=provider.resolve(server)
        patch.object(server,'_rh_coins_post_json',return_value=(200,json.dumps({'code':802,'msg':'private body'}))).start()
        with self.assertRaisesRegex(server.ImageSubmissionRejected,'失效'):provider.generate(server,cfg,'原文')

    def test_disabled_preflight_is_known_unsubmitted_and_repair_can_submit(self):
        folder=self.root/'tasks/preflight';folder.mkdir(parents=True)
        experiment.configure(server,{'enabled':False})
        with self.assertRaises(server.ImageSubmissionRejected):server.batch_image_result(provider.resolve(server),'original',1,'9:16','1k',folder)
        self.assertEqual(read(folder/'image-jobs/1.json',{})['status'],'rejected')
        self.assertEqual(self.events,[])
        experiment.configure(server,{'enabled':True})
        server.batch_image_result(provider.resolve(server),'original',1,'9:16','1k',folder)
        self.assertEqual(sum(url.endswith('/create') for url,_ in self.events),1)

    def test_creative_download_failure_reuses_original_paid_result(self):
        import creative_workflows as creative
        path=self.root/'tasks/creative/covers/1.png'
        config={'imageProvider':'runninghub_workflow','style':'realistic','ratio':'9:16'}
        with patch.object(creative,'bytes_to_file',side_effect=OSError('fixture download')):
            for _ in range(2):
                with self.assertRaises(OSError):creative.image(server,config,'scene',path)
        self.assertEqual(sum(url.endswith('/create') for url,_ in self.events),1)
        self.assertTrue(list(path.parent.glob('.rh-receipts/1.png/image-jobs/1.json')))

    def test_creative_stop_while_waiting_lock_does_not_submit_or_poison_receipt(self):
        import threading,creative_workflows as creative
        folder=self.root/'tasks/creative';folder.mkdir(parents=True);path=folder/'covers/1.png'
        ready=threading.Event();errors=[];original=graph_tools.build_graph
        def build(*args):result=original(*args);ready.set();return result
        def work():
            creative.EXECUTION.folder=folder
            try:creative.image(server,{'imageProvider':'runninghub_workflow'},'scene',path)
            except BaseException as error:errors.append(error)
        with patch.object(graph_tools,'build_graph',side_effect=build):
            with provider.LOCK:
                thread=threading.Thread(target=work);thread.start();self.assertTrue(ready.wait(3));(folder/'cancel').touch()
            thread.join(3)
        self.assertFalse(thread.is_alive());self.assertIsInstance(errors[0],InterruptedError);self.assertEqual(self.events,[])
        self.assertEqual(read(path.parent/'.rh-receipts/1.png/image-jobs/1.json',{})['status'],'rejected')

    def test_cover_poll_keeps_pause_checkpoint_and_saved_task_id(self):
        import task_cover
        folder=self.root/'tasks/cover';folder.mkdir(parents=True)
        write(folder/'client_config.json',{'cover':{'provider':provider.PROVIDER,'mode':'title'}})
        write(folder/'02-meta.json',{'title':'title'})
        original=self.post;cancelled=False
        def post(*args,**kwargs):
            nonlocal cancelled
            result=original(*args,**kwargs)
            if args[0].endswith('/create'):cancelled=True
            return result
        def check():
            if cancelled:raise InterruptedError('pause')
        with patch.object(server,'_rh_coins_post_json',side_effect=post):
            with self.assertRaises(InterruptedError):task_cover.initial(server,'cover',explicit_prompt='scene',checkpoint=check)
        self.assertEqual(sum(url.endswith('/create') for url,_ in self.events),1)
        self.assertFalse(any(url.endswith('/outputs') for url,_ in self.events))
        self.assertEqual(read(folder/'cover-job-1.json',{})['status'],'pending')

    def test_creative_receipt_preserves_task_no_face_requirement(self):
        import creative_workflows as creative
        folder=self.root/'tasks/creative';folder.mkdir(parents=True);path=folder/'covers/1.png'
        write(folder/'client_config.json',{'generate':{'extra':'不露脸'}})
        with patch.object(creative,'bytes_to_file'):
            creative.image(server,{'imageProvider':provider.PROVIDER},'人物正面，眼神坚毅，书房',path)
        prompt=json.loads(self.events[0][1]['workflow'])['4']['inputs']['text']
        self.assertIn('不露脸',prompt);self.assertNotIn('眼神坚毅',prompt)

    def test_query_805_requires_terminal_status_evidence(self):
        cfg=provider.resolve(server)
        for terminal,expected in [('RUNNING','PENDING'),('FAILED','FAILED')]:
            patch.object(server,'_rh_coins_post_json',side_effect=[(200,json.dumps({'code':805})),(200,json.dumps({'code':0,'data':terminal}))]).start()
            self.assertEqual(provider.query(server,cfg,'old-id')['status'],expected)

    def test_old_batch_id_rejects_different_member_key_without_new_request(self):
        cfg=provider.resolve(server);folder=self.root/'tasks/fixture';folder.mkdir(parents=True)
        import task_cover
        write(folder/'image-jobs/1.json',{'status':'pending','taskId':'old-id','provider':provider.PROVIDER,'prompt':'original',
            'ratio':'9:16','resolution':'1k','credential':task_cover.credential(cfg)})
        experiment.configure(server,{'api_key':'different-member-key'})
        with self.assertRaisesRegex(RuntimeError,'凭据'):server.batch_image_result(cfg,'original',1,'9:16','1k',folder)
        self.assertEqual(self.events,[])

    def test_public_settings_exposes_new_provider_without_member_key(self):
        value=server.public_settings()
        self.assertTrue(value['runninghub_workflow']['configured'])
        self.assertNotIn('member-key-fixture',json.dumps(value))


if __name__=='__main__':unittest.main()
