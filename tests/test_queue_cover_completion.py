"""Regression: complete a normal task before moving to the next one."""
import base64
import io
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
from PIL import Image

import server
import task_cover
import task_queue


class QueueCompletionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.backend=SimpleNamespace(DATA_DIR=Path(self.temp.name),TASK_OPERATION_LOCK=threading.RLock(),TASK_OPERATIONS=set())
        for tid in ['first','next']:
            folder=self.backend.DATA_DIR/'tasks'/tid;folder.mkdir(parents=True)
            (folder/'client_config.json').write_text(json.dumps({'generate':{},'tts':{},'image':{}}))
        self.q=task_queue.TaskQueue(self.backend,Mock(return_value=None));self.addCleanup(self.q.stop)
    def test_cover_failure_holds_normal_queue_and_resume_has_priority(self):
        def fail(job,q):q.stage(job,'cover','failed');raise ValueError('cover direction failure')
        self.q.executor=fail;self.q.enqueue('first');self.q.enqueue('next');self.q.run_next()
        self.assertEqual(self.q.get('first')['status'],'failed');self.assertFalse(self.q.run_next())
        self.assertTrue(self.q.get('first')['failure_hold'])
        self.q.executor=Mock(return_value=None);self.q.enqueue('first');self.q.run_next()
        self.assertEqual(self.q.executor.call_args.args[0]['task_id'],'first')
        self.assertEqual(self.q.get('next')['status'],'queued')
    def test_user_can_explicitly_skip_a_held_failure(self):
        self.q.executor=Mock(side_effect=ValueError('draft failure'))
        self.q.enqueue('first');self.q.enqueue('next');self.q.run_next()
        self.q.cancel('first');self.q.executor=Mock(return_value=None);self.assertTrue(self.q.run_next())
        self.assertEqual(self.q.executor.call_args.args[0]['task_id'],'next')
    def test_restart_never_runs_next_before_interrupted_current_is_addressed(self):
        self.q.enqueue('first');self.q.enqueue('next');self.q._find('first')['status']='running';self.q._save()
        recovered=task_queue.TaskQueue(self.backend,Mock());self.addCleanup(recovered.stop)
        self.assertEqual(recovered.get('first')['status'],'interrupted');self.assertFalse(recovered.run_next())
        recovered.executor.assert_not_called()


class CoverDirectionTests(unittest.TestCase):
    def test_template_preset_two_with_one_generated_visual_is_valid_and_keeps_its_hint(self):
        with tempfile.TemporaryDirectory() as temp:
            data=Path(temp);tid='fixture';folder=data/'tasks'/tid;folder.mkdir(parents=True)
            task_cover.write(folder/'02-meta.json',{'title':'fixture','cover_image_prompts':['fixture visual']})
            task_cover.write(folder/'client_config.json',{'cover':{'mode':'title','template':'chinese','direction':1}})
            image=io.BytesIO();Image.new('RGB',(32,48)).save(image,'PNG')
            with patch.object(server,'DATA_DIR',data),patch.object(server,'load_settings',return_value={}),patch.object(server,'resolve_image_config',return_value={'provider':'runninghub','api_key':'fixture'}),patch.object(server,'image_dispatcher',return_value={'b64':base64.b64encode(image.getvalue()).decode()}) as generate,patch.object(server,'call_llm',side_effect=AssertionError('no extra LLM')):
                result=task_cover.initial(server,tid,prompt_factory=Mock(side_effect=AssertionError('reuse metadata')),options={'template':server.story_cover_template('chinese')['id'],'direction':1,'provider':'runninghub'})
                self.assertTrue(result['url']);self.assertEqual(generate.call_count,1)
                job=task_cover.read(folder/'cover-job-1.json',{})
                self.assertIn(server.story_cover_template('chinese')['directions'][1]['hint'],job['prompt'])
                self.assertEqual(task_cover.initial(server,tid)['url'],result['url']);self.assertEqual(generate.call_count,1)
    def test_direct_editor_still_rejects_out_of_range_generated_direction(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(server,'DATA_DIR',Path(temp)):
            folder=Path(temp)/'tasks/fixture';folder.mkdir(parents=True)
            task_cover.write(folder/'02-meta.json',{'cover_image_prompts':['one visual']})
            with self.assertRaisesRegex(ValueError,'构图方向不存在'):
                task_cover.action(server,'fixture','save',{'direction':1})
