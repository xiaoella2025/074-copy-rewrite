"""Regression evidence for existing short-title retention; all task data is fake."""
from contextlib import nullcontext
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import task_cover


class CoverTitleRetention1250Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / 'tasks' / 'isolated-title'
        self.folder.mkdir(parents=True)
        self.meta = {'title': '封面原标题', 'subtitle': ['副标题'], 'short_title': '原视频号短标题',
                     'summary': '原发布文案', 'tags': ['#原标签'], 'comments': ['原评论'],
                     'cover_image_prompts': ['原画面方向']}
        task_cover.write(self.folder / '02-meta.json', self.meta)
        (self.folder / '02-rewrite.txt').write_text('隔离测试文案', 'utf8')
        selected = {'id': 'fixture-template', 'compositionRule': '隔离构图要求'}
        self.info = {'job': {}, 'template': selected['id'], 'template_snapshot': selected,
                     'directions': ['原画面方向'], 'profile_id': 'fixture-profile', 'title': self.meta['title']}
        self.backend = SimpleNamespace(DATA_DIR=self.root, ROOT=self.root, task_operation=lambda _: nullcontext(),
                                       resolve_active_llm_settings=Mock(return_value={'api_key': 'fixture-only'}),
                                       load_prompt_module=Mock(return_value='隔离提示词'),
                                       step1_meta=Mock(return_value={'title': '模型新标题', 'short_title': '',
                                                                    'cover_image_prompts': ['新方向一', '新方向二']}))
        self.addCleanup(patch.stopall)
        patch.object(task_cover, 'view', return_value=self.info).start()
        patch.object(task_cover, 'cover_template', return_value=selected).start()
        patch.object(task_cover, 'TemplateStore', return_value=SimpleNamespace(list=lambda _: [selected])).start()

    def saved_meta(self):
        return json.loads((self.folder / '02-meta.json').read_text('utf8'))

    def test_editing_primary_cover_text_retains_short_title_and_publish_materials(self):
        task_cover.action(self.backend, 'isolated-title', 'save', {'title': '新主标题', 'subtitle': ['新副标题']})
        self.assertEqual(self.saved_meta(), {**self.meta, 'title': '新主标题', 'subtitle': ['新副标题']})
        self.backend.step1_meta.assert_not_called()

    def test_regenerating_cover_directions_never_replaces_existing_short_title(self):
        before = (self.folder / '02-meta.json').read_bytes()
        task_cover.action(self.backend, 'isolated-title', 'directions', {})
        self.assertEqual((self.folder / '02-meta.json').read_bytes(), before)
        editor = json.loads((self.folder / 'cover-editor.json').read_text('utf8'))['1']
        self.assertEqual(editor['directions'], ['新方向一', '新方向二'])
        self.backend.step1_meta.assert_called_once()

    def test_secondary_cover_edit_keeps_primary_publish_metadata_intact(self):
        before = (self.folder / '02-meta.json').read_bytes()
        task_cover.action(self.backend, 'isolated-title', 'save', {'slot': 2, 'title': '第二张主标题'})
        self.assertEqual((self.folder / '02-meta.json').read_bytes(), before)
        self.backend.step1_meta.assert_not_called()


if __name__ == '__main__':
    unittest.main()
