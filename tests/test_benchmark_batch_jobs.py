import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import benchmark
import benchmark_ai_receipts as receipts
from benchmark_batch_jobs import BatchJobs, BatchConflict
from benchmark_batch_actions import execute_item


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.backend=SimpleNamespace(DATA_DIR=Path(self.temp.name),ROOT=Path(__file__).resolve().parents[1])
        self.items=[{'accountId':'v2_one','feedId':'same'},{'accountId':'v2_two','feedId':'same'}]
        benchmark._write(self.backend,{'version':1,'accounts':[],'feeds':[{**x,'transcript':'cached','title':'fixture'} for x in self.items]})
        self.request={'id':'a'*32,'kind':'extract','items':self.items}
    def wait(self,manager):
        thread=manager.thread
        if thread:thread.join(5);self.assertFalse(thread.is_alive())
        return manager.list()[0]
    def test_identity_idempotency_conflict_and_list_never_executes(self):
        executor=Mock(return_value={'reused':True});m=BatchJobs(self.backend,executor)
        m.submit(self.request);self.wait(m)
        m.submit(self.request);m.list();m.list()
        self.assertEqual(executor.call_count,2)
        self.assertEqual([x.args[2]['accountId'] for x in executor.call_args_list],['v2_one','v2_two'])
        with self.assertRaises(BatchConflict):m.submit({**self.request,'items':self.items[:1]})
    def test_one_active_stop_waits_and_resume_skips_success(self):
        entered=threading.Event();release=threading.Event();calls=[]
        def execute(backend,kind,row,mark=None):
            calls.append(row['accountId']);entered.set();release.wait(5);return {}
        m=BatchJobs(self.backend,execute);m.submit(self.request);self.assertTrue(entered.wait(2))
        with self.assertRaises(BatchConflict):m.submit({**self.request,'id':'b'*32})
        self.assertEqual(m.control('a'*32,'stop')['status'],'stopping')
        release.set();self.assertEqual(self.wait(m)['status'],'stopped')
        m.control('a'*32,'resume');job=self.wait(m)
        self.assertEqual(job['status'],'completed');self.assertEqual(calls,['v2_one','v2_two'])
    def test_restart_interrupts_without_execution_and_preserves_completed(self):
        folder=self.backend.DATA_DIR/'benchmark/batch-jobs';folder.mkdir(parents=True)
        rows=[{**x,'status':s,'error':'','result':{}} for x,s in zip(self.items,['succeeded','running'])]
        (folder/('a'*32+'.json')).write_text(json.dumps({**self.request,'version':1,'rows':rows,'status':'running'}))
        executor=Mock(return_value={});m=BatchJobs(self.backend,executor)
        self.assertEqual(m.list()[0]['status'],'interrupted');executor.assert_not_called()
        m.control('a'*32,'resume');self.wait(m);self.assertEqual(executor.call_count,1)
    def test_unknown_receipt_is_not_retried(self):
        executor=Mock(side_effect=receipts.UnconfirmedReceiptError('unknown'))
        m=BatchJobs(self.backend,executor);m.submit(self.request);self.wait(m)
        m.control('a'*32,'resume');job=self.wait(m)
        self.assertEqual(executor.call_count,2)
        self.assertEqual([x['status'] for x in job['rows']],['unconfirmed','unconfirmed'])
    def test_empty_list_does_not_create_directory_and_corrupt_record_survives(self):
        m=BatchJobs(self.backend);self.assertEqual(m.list(),[])
        folder=self.backend.DATA_DIR/'benchmark/batch-jobs';self.assertFalse(folder.exists())
        folder.mkdir(parents=True);path=folder/('a'*32+'.json');path.write_bytes(b'bad')
        with self.assertRaises(ValueError):BatchJobs(self.backend)
        self.assertEqual(path.read_bytes(),b'bad')
    def test_invalid_payload_does_not_write(self):
        m=BatchJobs(self.backend)
        for change in [{'id':'../bad'},{'kind':'other'},{'items':[]},{'items':self.items*2},{'items':[{'accountId':'v2_one','feedId':'missing'}]},{'kind':'mark','mark':'yes'}]:
            with self.subTest(change=change),self.assertRaises(ValueError):m.submit({**self.request,**change})
        self.assertEqual(m.list(),[])
    def test_resume_save_failure_keeps_job_retryable_without_phantom_worker(self):
        m=BatchJobs(self.backend,Mock(side_effect=ValueError('fixture validation')))
        m.submit(self.request);self.wait(m)
        with patch.object(m,'_save',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):m.control('a'*32,'resume')
        self.assertEqual(m.list()[0]['status'],'completed')
        m.executor=Mock(return_value={});m.control('a'*32,'resume')
        self.assertEqual(self.wait(m)['succeeded'],2);self.assertEqual(m.executor.call_count,2)
    def test_claim_save_failure_does_not_skip_an_unexecuted_row(self):
        m=BatchJobs(self.backend,Mock(return_value={}));save=m._save;failed=False
        def fail_claim(job):
            nonlocal failed
            if not failed and any(x['status']=='running' for x in job['rows']):
                failed=True;raise OSError('disk full')
            save(job)
        with patch.object(m,'_save',side_effect=fail_claim):
            m.submit(self.request);self.assertEqual(self.wait(m)['status'],'interrupted')
        m.control('a'*32,'resume');job=self.wait(m)
        self.assertEqual(job['done'],2);self.assertEqual(job['succeeded'],2);self.assertEqual(m.executor.call_count,2)
    def test_thread_start_failure_keeps_a_saved_batch_recoverable(self):
        m=BatchJobs(self.backend,Mock(return_value={}))
        with patch('benchmark_batch_jobs.threading.Thread.start',side_effect=RuntimeError('resources')):
            job=m.submit(self.request)
        self.assertEqual(job['status'],'interrupted')
        m.control('a'*32,'resume');self.assertEqual(self.wait(m)['succeeded'],2)
    def test_cached_text_no_asr_fixed_mark_and_existing_export(self):
        with patch.object(benchmark,'transcribe') as asr:
            self.assertTrue(execute_item(self.backend,'extract',self.items[0])['reused'])
            result=execute_item(self.backend,'download',self.items[0]);self.assertTrue(Path(result['path']).is_file())
            asr.assert_not_called()
        execute_item(self.backend,'mark',self.items[0],True)
        self.assertTrue(benchmark.state(self.backend)['feeds'][0]['createdTask'])
        self.assertTrue(Path(result['path']).is_file())
    def test_promo_source_change_blocks_request_and_completed_receipt_reused(self):
        item=benchmark.state(self.backend)['feeds'][0];row={**self.items[0],'source_fingerprint':receipts.fingerprint(item)}
        reserve=receipts.reserve(self.backend,item);receipts.complete(self.backend,reserve,json.dumps({'isPromo':False,'evidence':''}))
        self.backend.call_llm=Mock(side_effect=AssertionError('external call'))
        execute_item(self.backend,'promo',row)
        self.assertFalse(benchmark.state(self.backend)['feeds'][0]['promo']['isPromo'])
        benchmark.edit(self.backend,{**self.items[0],'changes':{'transcript':'manual'}})
        with patch.object(benchmark,'ai_action') as action,self.assertRaisesRegex(ValueError,'变化|修改'):
            execute_item(self.backend,'promo',row)
        action.assert_not_called();self.backend.call_llm.assert_not_called()
    def test_promo_change_between_dispatch_and_inference_blocks_new_request(self):
        item=benchmark.state(self.backend)['feeds'][0];row={**self.items[0],'source_fingerprint':receipts.fingerprint(item)}
        original=benchmark.ai_action
        def racing(backend,data):
            benchmark.edit(backend,{**self.items[0],'changes':{'transcript':'new manual'}})
            return original(backend,data)
        with patch.object(benchmark,'ai_action',side_effect=racing),self.assertRaisesRegex(ValueError,'变化'):
            execute_item(self.backend,'promo',row)
        self.assertFalse((self.backend.DATA_DIR/'benchmark/ai-promo-receipts.sqlite').exists())
    def test_real_executor_receipt_unknown_never_calls_llm_twice(self):
        item=benchmark.state(self.backend)['feeds'][0];receipts.reserve(self.backend,item)
        self.backend.call_llm=Mock(side_effect=AssertionError('external call'))
        row={**self.items[0],'source_fingerprint':receipts.fingerprint(item)}
        for _ in range(2):
            with self.assertRaises(receipts.UnconfirmedReceiptError):execute_item(self.backend,'promo',row)
        self.backend.call_llm.assert_not_called()
