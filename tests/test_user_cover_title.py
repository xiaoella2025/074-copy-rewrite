import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import server
import task_cover


class UserCoverTitleTests(unittest.TestCase):
    TITLE='人这一辈子，有101个地方，去晚了就只剩后悔'

    def test_explicit_title_survives_ai_metadata_and_short_title_stays_independent(self):
        response={'title':'101地别等老了','short_title':'风景还在身体等不起','subtitle':['副标题'],'summary':'发布正文','tags':['#旅行'],'comments':['建议'],'cover_image_prompts':['山水']}
        with patch.object(server,'call_llm',return_value=json.dumps(response,ensure_ascii=False)) as call:
            result=server.step1_meta({'_cover_custom_text':{'title':self.TITLE,'subtitle':['指定副题']}},'任务名称','完整正文',[],'culture-knowledge')
        self.assertEqual(result['title'],self.TITLE)
        self.assertEqual(result['short_title'],response['short_title'])
        self.assertEqual(result['summary'],response['summary'])
        self.assertEqual(result['subtitle'],['指定副题'])
        self.assertEqual(call.call_count,1)
        self.assertIn('不得改写、缩短',call.call_args.args[1])

    def test_empty_body_does_not_truncate_the_user_title(self):
        title=self.TITLE+'，想去就别再等了'
        with patch.object(server,'call_llm') as call:
            self.assertEqual(server.step1_meta({'_cover_custom_text':{'title':title}},'任务名称','',[],'general')['title'],title)
        call.assert_not_called()

    def test_task_title_alone_still_uses_ai_cover_metadata(self):
        with patch.object(server,'call_llm',return_value='{"title":"自动题字","short_title":"发布短题"}'):
            self.assertEqual(server.step1_meta({},self.TITLE,'完整正文',[],'general')['title'],'自动题字')

    def test_explicit_cover_title_precedes_ai_metadata_but_manual_card_edit_wins(self):
        with tempfile.TemporaryDirectory() as root,patch.object(server,'DATA_DIR',Path(root)):
            folder=Path(root)/'tasks/fixture';folder.mkdir(parents=True)
            task_cover.write(folder/'client_config.json',{'generate':{'title':'任务名称'},'cover':{'title':self.TITLE}})
            task_cover.write(folder/'02-meta.json',{'title':'旧AI题字','cover_image_prompts':['山水']})
            self.assertEqual(task_cover.view(server,'fixture')['title'],self.TITLE)
            task_cover.action(server,'fixture','save',{'title':'手工另写的封面'})
            self.assertEqual(task_cover.view(server,'fixture')['title'],'手工另写的封面')
            self.assertEqual(task_cover.view(server,'fixture',2)['title'],self.TITLE)

    def test_automatic_editor_does_not_override_explicit_cover_title(self):
        with tempfile.TemporaryDirectory() as root,patch.object(server,'DATA_DIR',Path(root)):
            folder=Path(root)/'tasks/fixture';folder.mkdir(parents=True)
            task_cover.write(folder/'request.json',{'title':'任务名称'})
            task_cover.write(folder/'client_config.json',{'cover':{'title':self.TITLE}})
            task_cover.write(folder/'02-meta.json',{'title':'旧AI题字','cover_image_prompts':['山水']})
            task_cover.write(folder/'cover-editor.json',{'1':{'title':'旧AI题字','workflow_choices':True}})
            self.assertEqual(task_cover.view(server,'fixture')['title'],self.TITLE)

    def test_changing_ratio_after_automatic_snapshot_does_not_revive_ai_title(self):
        with tempfile.TemporaryDirectory() as root,patch.object(server,'DATA_DIR',Path(root)):
            folder=Path(root)/'tasks/fixture';folder.mkdir(parents=True)
            task_cover.write(folder/'request.json',{'title':'任务名称'})
            task_cover.write(folder/'client_config.json',{'cover':{'title':self.TITLE}})
            task_cover.write(folder/'02-meta.json',{'title':'旧AI题字','cover_image_prompts':['山水']})
            task_cover.write(folder/'cover-editor.json',{'1':{'title':'旧AI题字','workflow_choices':True}})
            task_cover.action(server,'fixture','save',{'ratio':'9:16'})
            self.assertEqual(task_cover.view(server,'fixture')['title'],self.TITLE)

    def test_changing_directions_after_automatic_snapshot_keeps_user_title(self):
        with tempfile.TemporaryDirectory() as root,patch.object(server,'DATA_DIR',Path(root)):
            folder=Path(root)/'tasks/fixture';folder.mkdir(parents=True)
            task_cover.write(folder/'request.json',{'title':'任务名称'})
            task_cover.write(folder/'client_config.json',{'cover':{'title':self.TITLE}})
            task_cover.write(folder/'02-meta.json',{'title':'旧AI题字','cover_image_prompts':['山水']})
            task_cover.write(folder/'cover-editor.json',{'1':{'title':'旧AI题字','workflow_choices':True}})
            (folder/'02-rewrite.txt').write_text('正文','utf8')
            with patch.object(server,'resolve_active_llm_settings',return_value={'api_key':'fixture'}),patch.object(server,'step1_meta',return_value={'cover_image_prompts':['新山水']}):
                task_cover.action(server,'fixture','directions',{})
            self.assertEqual(task_cover.view(server,'fixture')['title'],self.TITLE)

    def test_task_name_is_not_a_cover_title_override(self):
        with tempfile.TemporaryDirectory() as root,patch.object(server,'DATA_DIR',Path(root)):
            folder=Path(root)/'tasks/fixture';folder.mkdir(parents=True)
            task_cover.write(folder/'request.json',{'title':self.TITLE})
            task_cover.write(folder/'client_config.json',{'generate':{'title':self.TITLE},'cover':{'title':''}})
            task_cover.write(folder/'02-meta.json',{'title':'自动封面题字'})
            self.assertEqual(task_cover.view(server,'fixture')['title'],'自动封面题字')

    def test_explicit_subtitle_survives_automatic_snapshot_and_ratio_edit(self):
        with tempfile.TemporaryDirectory() as root,patch.object(server,'DATA_DIR',Path(root)):
            folder=Path(root)/'tasks/fixture';folder.mkdir(parents=True)
            task_cover.write(folder/'client_config.json',{'cover':{'title':self.TITLE,'subtitle':'指定第一句\n指定第二句'}})
            task_cover.write(folder/'02-meta.json',{'title':'AI题字','subtitle':['AI副题'],'cover_image_prompts':['山水']})
            task_cover.write(folder/'cover-editor.json',{'1':{'title':'AI题字','subtitle':['AI副题'],'workflow_choices':True}})
            self.assertEqual(task_cover.view(server,'fixture')['subtitle'],['指定第一句','指定第二句'])
            task_cover.action(server,'fixture','save',{'ratio':'9:16'})
            self.assertEqual(task_cover.view(server,'fixture')['subtitle'],['指定第一句','指定第二句'])
            task_cover.action(server,'fixture','save',{'subtitle':['手改副题']})
            self.assertEqual(task_cover.view(server,'fixture')['subtitle'],['手改副题'])

    def test_saved_explicit_cover_text_is_used_during_metadata_generation(self):
        with tempfile.TemporaryDirectory() as root:
            folder=Path(root)
            task_cover.write(folder/'client_config.json',{'cover':{'title':self.TITLE,'subtitle':'第一句\n第二句'}})
            with patch.object(server,'call_llm',return_value='{"title":"AI题字","subtitle":["AI副题"]}') as call:
                result=server.step1_meta({},'任务名称','正文',[],'general',response_dir=folder)
            self.assertEqual(result['title'],self.TITLE)
            self.assertEqual(result['subtitle'],['第一句','第二句'])
            self.assertEqual(call.call_count,1)


if __name__=='__main__':unittest.main()
