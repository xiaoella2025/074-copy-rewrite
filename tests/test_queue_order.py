"""Durable queue ordering and per-task deferral, with fake stage execution."""
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
import task_queue


class QueueOrderTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.backend=SimpleNamespace(DATA_DIR=Path(self.tmp.name),TASK_OPERATION_LOCK=threading.RLock(),TASK_OPERATIONS=set(),
            _prepare_task_rerun=Mock(),get_task_detail=lambda _: {})
        self.performed=[]
        self.q=task_queue.TaskQueue(self.backend,executor=lambda job,q:self.performed.append(job['task_id']))
        self.addCleanup(self.q.stop)
        for tid in ('a','b','c'):
            folder=self.backend.DATA_DIR/'tasks'/tid;folder.mkdir(parents=True)
            (folder/'client_config.json').write_text(json.dumps({'generate':{},'tts':{},'image':{}}),'utf8')
            (folder/'saved.png').write_bytes(b'already generated')

    def control(self,tid,action):
        import queue_order
        return queue_order.control(self.q,{'task_id':tid,'action':action})

    def test_priority_releases_earlier_manual_pause_instead_of_accepting_a_stuck_queue(self):
        self.q.enqueue('a');self.q.enqueue('b');self.q.request_pause('a')
        self.control('b','first')
        self.assertTrue(self.q.run_next())
        self.assertEqual(self.performed,['b'])
        self.assertTrue(self.q.get('a')['deferred'])

    def test_individual_start_resumes_a_deferred_task_at_the_front_without_resetting_artifacts(self):
        self.q.enqueue('a');self.q.enqueue('b');self.control('a','defer')
        self.control('a','start')
        self.assertEqual(self.q.get('a')['position'],1)
        self.q.run_next();self.assertEqual(self.performed,['a'])
        self.backend._prepare_task_rerun.assert_not_called()

    def test_explicit_priority_temporarily_sets_aside_an_earlier_failure_hold(self):
        self.q.enqueue('a');self.q.enqueue('b')
        self.q._find('a').update(status='failed',failure_hold=True,error='fixture error')
        self.control('b','first');self.assertTrue(self.q.run_next())
        self.assertEqual(self.performed,['b'])
        self.assertEqual(self.q.get('a')['error'],'fixture error')
        self.assertEqual(self.q.get('a')['status'],'failed')

    def test_move_up_down_first_persists_and_changes_execution_not_outputs(self):
        for tid in ('a','b','c'):self.q.enqueue(tid)
        ids={j['task_id']:j['id'] for j in self.q.jobs}
        self.control('c','up');self.assertEqual(self.q.get('c')['position'],2)
        self.control('a','down');self.assertEqual(self.q.get('c')['position'],1)
        self.control('b','first');self.assertEqual(self.q.get('b')['position'],1)
        loaded=task_queue.TaskQueue(self.backend,executor=lambda job,q:self.performed.append(job['task_id']))
        self.addCleanup(loaded.stop)
        self.assertEqual({j['task_id']:j['id'] for j in loaded.jobs},ids)
        while loaded.run_next():pass
        self.assertEqual(self.performed,['b','c','a'])
        self.assertTrue(all((self.backend.DATA_DIR/'tasks'/tid/'saved.png').read_bytes()==b'already generated' for tid in ids))
        self.backend._prepare_task_rerun.assert_not_called()

    def test_prioritize_inflight_saves_current_result_before_switch_and_resume_at_tail(self):
        entered,release=threading.Event(),threading.Event()
        def execute(job,q):
            if job['task_id']=='a':
                entered.set();release.wait(3)
                (self.backend.DATA_DIR/'tasks/a/result.txt').write_text('saved','utf8')
                q.checkpoint(job)
            self.performed.append(job['task_id'])
        self.q.executor=execute
        for tid in ('a','b','c'):self.q.enqueue(tid)
        worker=threading.Thread(target=self.q.run_next);worker.start();self.assertTrue(entered.wait(3))
        try:
            self.control('c','first')
            self.assertEqual(self.q.get('a')['status'],'pausing')
            self.assertFalse(self.q.run_next())
        finally:release.set();worker.join(3)
        self.assertEqual((self.backend.DATA_DIR/'tasks/a/result.txt').read_text('utf8'),'saved')
        self.assertTrue(self.q.get('a')['deferred']);self.assertEqual(self.q.get('a')['status'],'paused')
        self.q.run_next();self.assertEqual(self.performed,['c'])
        self.control('a','resume');self.assertEqual(self.q.get('a')['position'],2)
        self.q.run_next();self.assertEqual(self.performed,['c','b'])

    def test_deferred_queued_and_manual_pause_survive_restart_without_blocking_others(self):
        self.q.enqueue('a');self.q.enqueue('b');self.q.request_pause('a')
        self.control('a','defer')
        loaded=task_queue.TaskQueue(self.backend,executor=lambda job,q:self.performed.append(job['task_id']))
        self.addCleanup(loaded.stop);self.assertTrue(loaded.run_next())
        self.assertEqual(self.performed,['b']);self.assertEqual(loaded.get('a')['status'],'paused')

    def test_defer_batch_current_does_not_pause_other_members_or_auto_resume_it(self):
        batch=self.q.enqueue_batch(['a','b','c'])
        self.q.request_pause('a');self.control('a','defer')
        self.assertEqual(self.q.batch(batch['id'])['status'],'running')
        self.q.run_next();self.assertEqual(self.performed,['b'])
        self.q.batch_action(batch['id'],'pause');self.q.batch_action(batch['id'],'resume')
        self.assertTrue(self.q.get('a')['deferred']);self.assertEqual(self.q.get('a')['status'],'paused')
        self.q.run_next();self.assertEqual(self.performed,['b','c'])
        self.control('a','resume');self.q.run_next();self.assertEqual(self.performed,['b','c','a'])

    def test_restart_during_deferral_retains_pause_and_does_not_add_failure_hold(self):
        self.q.enqueue('a');self.q.enqueue('b');self.q._find('a')['status']='running'
        self.control('a','defer')
        loaded=task_queue.TaskQueue(self.backend,executor=lambda job,q:self.performed.append(job['task_id']))
        self.addCleanup(loaded.stop);self.assertEqual(loaded.get('a')['status'],'paused')
        self.assertFalse(loaded.get('a').get('failure_hold'));self.assertTrue(loaded.run_next())
        self.assertEqual(self.performed,['b'])

    def test_reordering_cannot_clear_failure_hold_or_start_scheduled_batch_early(self):
        import time
        self.q.enqueue('a');self.q._find('a').update(status='failed',failure_hold=True)
        batch=self.q.enqueue_batch(['b','c'],schedule_at=time.time()+3600)
        self.control('c','first');self.assertFalse(self.q.run_next())
        self.assertEqual(self.q.batch(batch['id'])['status'],'scheduled')
        for action in ('up','down','first'):
            with self.assertRaises(ValueError):self.control('a',action)
        self.assertTrue(self.q.get('a')['failure_hold'])

    def test_deferred_review_still_requires_confirmation_when_restored(self):
        self.q.enqueue('a');self.q.enqueue('b');job=self.q._find('a');job.update(status='paused',pause_stage='generate')
        self.control('a','defer');self.control('a','resume')
        self.assertEqual(self.q.get('a')['status'],'paused');self.assertEqual(self.q.get('a')['approved_stages'],[])
        self.q.confirm('a');self.assertEqual(self.q.get('a')['position'],2)

    def test_deferring_an_unstarted_explicit_rerun_retains_the_selected_step(self):
        self.q.enqueue('a',from_step='4');self.control('a','defer');self.control('a','resume')
        self.assertEqual(self.q.get('a')['from_step'],'4')
        self.q.run_next();self.backend._prepare_task_rerun.assert_called_once_with('a','4')

    def test_completed_invalidation_is_not_repeated_after_deferring_an_active_rerun(self):
        self.q.enqueue('a',from_step='4');job=self.q._find('a');job.update(status='running',rerun_prepared=True)
        self.control('a','defer');job['status']='paused';self.control('a','resume')
        self.q.run_next();self.backend._prepare_task_rerun.assert_not_called()

    def test_review_checkpoint_reached_during_drain_is_preserved(self):
        self.q.enqueue('a');job=self.q._find('a');job['status']='running';self.control('a','defer')
        with self.assertRaises(InterruptedError):self.q.pause(job,'generate')
        job['status']='paused';self.control('a','resume')
        self.assertEqual(self.q.get('a')['pause_stage'],'generate')
        self.assertEqual(self.q.get('a')['status'],'paused')

    def test_order_http_changes_real_queue_and_rejects_invalid_action(self):
        import server,http.client
        host=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        thread=threading.Thread(target=host.serve_forever,daemon=True);thread.start()
        self.addCleanup(host.server_close);self.addCleanup(host.shutdown)
        self.q.enqueue('a');self.q.enqueue('b')
        def post(body):
            c=http.client.HTTPConnection('127.0.0.1',host.server_port,timeout=5)
            c.request('POST','/api/task-queue/order',json.dumps(body),{'Content-Type':'application/json'})
            r=c.getresponse();result=r.status,json.loads(r.read());c.close();return result
        with patch.object(server,'DATA_DIR',self.backend.DATA_DIR),patch.object(server,'TASK_QUEUE',self.q,create=True):
            status,value=post({'task_id':'b','action':'first'})
            self.assertEqual(status,200);self.assertEqual(value['position'],1)
            self.assertEqual(post({'task_id':'a','action':'erase'})[0],409)
            self.assertEqual(post({'task_id':'missing','action':'defer'})[0],409)


class CreativeDeferralTests(unittest.TestCase):
    def test_defer_while_loading_creative_state_cannot_be_erased_by_startup(self):
        import creative_workflows as creative
        import queue_order
        with tempfile.TemporaryDirectory() as root:
            tid='html_'+'a'*32
            folder=Path(root)/'tasks'/tid;folder.mkdir(parents=True)
            state={'task_id':tid,'kind':'html','title':'fixture','config':{},'completed':[],'timings':{},'status':'queued'}
            creative.write(folder/'creative.json',state)
            backend=SimpleNamespace(DATA_DIR=Path(root),TASK_OPERATION_LOCK=threading.RLock(),TASK_OPERATIONS=set())
            q=task_queue.TaskQueue(backend);self.addCleanup(q.stop);q.enqueue(tid,kind='html',config={})
            called=[]
            def loading(*_):queue_order.control(q,{'task_id':tid,'action':'defer'});return state
            def flow(_backend,path,value):
                for step in [x[0] for x in creative.STAGES['html']][:2]:
                    creative.checkpoint(path,value,step,lambda:called.append(step))
            with patch.object(creative,'get',side_effect=loading),patch.object(creative,'html_flow',side_effect=flow):q.run_next()
            self.assertEqual(called,[]);self.assertEqual(q.get(tid)['status'],'paused')

    def test_deferral_stops_after_stage_is_saved_without_cancelling_inflight_action(self):
        import creative_workflows as creative
        with tempfile.TemporaryDirectory() as root:
            folder=Path(root);state={'kind':'html','task_id':'fixture','completed':[],'timings':{},'config':{}}
            step=creative.STAGES['html'][0][0]
            def action():
                (folder/'defer').touch();(folder/'result.png').write_bytes(b'saved provider output')
            with self.assertRaises(creative.Paused):creative.checkpoint(folder,state,step,action)
            self.assertIn(step,state['completed']);self.assertEqual(state['status'],'paused')
            self.assertFalse((folder/'cancel').exists());self.assertTrue((folder/'result.png').is_file())


if __name__=='__main__':unittest.main()
