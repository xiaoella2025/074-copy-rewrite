"""Cover library and per-slot choices; no real provider requests."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import server
import task_cover
from template_store import TemplateStore


class CoverSettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.folder = self.root/'tasks'/'fixture'
        self.folder.mkdir(parents=True); self.addCleanup(patch.stopall)
        patch.object(server, 'DATA_DIR', self.root).start()
        patch.object(server, 'load_profiles', return_value=[
            {'id':'task-model','name':'任务模型','model':'model-a','enabled':True,'apiKey':'secret'},
            {'id':'cover-model','name':'封面模型','model':'model-b','apiKey':'secret'}]).start()
        patch.object(server, 'call_llm', side_effect=AssertionError('no paid calls')).start()
        patch.object(server, 'image_dispatcher', side_effect=AssertionError('no paid images')).start()
        task_cover.write(self.folder/'02-meta.json', {'title':'原题','subtitle':['原副题'],'cover_image_prompts':['原构图']})
        task_cover.write(self.folder/'client_config.json', {'generate':{'profile_id':'task-model'}})
        (self.folder/'02-rewrite.txt').write_text('完整原文', 'utf8')
        self.store = TemplateStore(self.root, server.ROOT)

    def action(self, name, slot=1, **data):
        return task_cover.action(server, 'fixture', name, {'slot':slot, **data})

    def test_historical_cover_profile_is_ignored_and_never_exposes_credentials(self):
        before = (self.folder/'client_config.json').read_bytes()
        self.action('save', profile_id='cover-model')
        self.assertEqual(task_cover.view(server,'fixture',1)['profile_id'], 'task-model')
        self.assertEqual(task_cover.view(server,'fixture',2)['profile_id'], 'task-model')
        self.assertNotIn('secret', str(task_cover.view(server,'fixture')))
        self.action('save', profile_id='')
        self.assertEqual(task_cover.view(server,'fixture')['profile_id'], 'task-model')
        self.assertEqual(before,(self.folder/'client_config.json').read_bytes())
        with self.assertRaises(ValueError): self.action('save', profile_id='deleted-model')

    def test_direction_generation_uses_system_model_and_only_updates_its_slot(self):
        self.action('save', slot=2, profile_id='cover-model', title='第二张标题')
        with patch.object(server,'resolve_active_llm_settings', return_value={'api_key':'fixture'}) as resolve, \
             patch.object(server,'step1_meta', return_value={'cover_image_prompts':['第二张构图']}) as generate:
            self.action('directions', slot=2)
        resolve.assert_called_once_with(); generate.assert_called_once()
        self.assertEqual(task_cover.view(server,'fixture',1)['directions'], ['原构图'])
        self.assertEqual(task_cover.view(server,'fixture',1)['title'], '原题')
        self.assertEqual(task_cover.view(server,'fixture',2)['directions'], ['第二张构图'])
        self.assertEqual(task_cover.view(server,'fixture',2)['title'], '第二张标题')

    def test_library_snapshot_survives_edit_delete_and_applies_to_prompt(self):
        item = copy.deepcopy(server.story_workflow_reference()['coverTemplates'][0])
        item.update(name='自定义封面', compositionRule='独特构图', titleLayout='顶端「{{TITLE}}」')
        saved = self.store.save('covers', item)
        self.action('save', template=saved['id'])
        self.assertIn('顶端',task_cover.view(server,'fixture')['prompt'])
        self.store.save('covers', {**saved,'titleLayout':'其他排版'}, saved['id'])
        self.store.delete('covers', saved['id'])
        self.action('save', ratio='1:1')
        result = task_cover.view(server,'fixture')
        self.assertIn('顶端',result['prompt'])
        self.assertEqual(task_cover.view(server,'fixture',2)['template'], 'cinematic-poster')
        self.assertEqual(next(t for t in result['templates'] if t['id']==saved['id'])['compositionRule'],'独特构图')

    def test_save_custom_template_selects_only_this_slot_and_reuses_library(self):
        template = {**server.story_workflow_reference()['coverTemplates'][0], 'name':'我的模板','compositionRule':'自定义构图'}
        result = self.action('save-template', slot=2, template=template)
        self.assertTrue(result['template'].startswith('custom-'))
        self.assertEqual(len(self.store.list('covers')),7)
        self.assertEqual(task_cover.view(server,'fixture',1)['template'],'cinematic-poster')
        with patch.object(server,'resolve_active_llm_settings',return_value={'api_key':'fixture'}), \
             patch.object(server,'step1_meta', return_value={'cover_image_prompts':['新方向']}) as llm:
            self.action('directions',slot=2)
        self.assertIn('自定义构图',llm.call_args.args[0]['_prompt_template']['step1MetadataSystemPrompt'])

    def test_invalid_custom_template_cannot_write_library_or_editor(self):
        for delta in ({'compositionRule':[]}, {'directions':[{'label':'a','hint':None}]}, {'titleLayout':123}):
            item = {**server.story_workflow_reference()['coverTemplates'][0],**delta}
            with self.assertRaises(ValueError): self.action('save-template', template=item)
        self.assertFalse(self.store.path.exists())
        self.assertFalse((self.folder/'cover-editor.json').exists())

    def test_new_template_without_visuals_cannot_reuse_old_jobs_full_prompt(self):
        task_cover.write(self.folder/'02-meta.json',{'title':'原题'})
        task_cover.write(self.folder/'cover-job-1.json',{'status':'ok','prompt':'旧模板完整提示词'})
        result=self.action('save',template='minimal-clean')
        self.assertEqual(result['prompt'],'')

    def test_legacy_template_alias_saves_remain_readable_and_keep_snapshot(self):
        for alias in ('movie','custom:旧版构图说明'):
            with self.subTest(alias=alias):
                (self.folder/'cover-editor.json').unlink(missing_ok=True)
                task_cover.write(self.folder/'client_config.json',{'cover':{'template':alias}})
                self.action('save',ratio='1:1',profile_id='cover-model')
                result=task_cover.view(server,'fixture')
                self.assertEqual(result['template'],'cinematic-poster')
                self.assertEqual(result['ratio'],'1:1')
                if alias.startswith('custom:'):self.assertEqual(result['template_snapshot']['compositionRule'],'旧版构图说明')

    def test_initial_resume_uses_system_model_and_keeps_custom_template_over_queued_options(self):
        import base64,io
        from PIL import Image
        task_cover.write(self.folder/'02-meta.json',{'title':'原题'})
        template={**server.story_workflow_reference()['coverTemplates'][0],'name':'自有模板','compositionRule':'专属构图'}
        saved=self.action('save-template',template=template)
        self.action('save',profile_id='cover-model',title='封面专属题',subtitle=['封面专属副题'])
        image=io.BytesIO();Image.new('RGB',(32,48)).save(image,'PNG')
        with patch.object(server,'resolve_active_llm_settings',return_value={'api_key':'fixture'}) as resolve, \
             patch.object(server,'call_llm',return_value='自有视觉') as llm, \
             patch.object(server,'resolve_image_config',return_value={'provider':'runninghub','api_key':'fixture'}), \
             patch.object(server,'image_dispatcher',return_value={'b64':base64.b64encode(image.getvalue()).decode()}):
            task_cover.initial(server,'fixture',options={'template':'cinematic-poster','title':'旧队列标题','subtitle':['旧队列副题']},prompt_factory=lambda:self.fail('stale task model factory'))
        resolve.assert_called_once_with()
        self.assertIn('专属构图',llm.call_args.args[1]);self.assertIn('封面专属题',llm.call_args.args[2])
        self.assertEqual(task_cover.view(server,'fixture')['template'],saved['template'])
        self.assertEqual(task_cover.view(server,'fixture')['title'],'封面专属题')
        self.assertEqual(task_cover.view(server,'fixture')['subtitle'],['封面专属副题'])


if __name__ == '__main__': unittest.main()
