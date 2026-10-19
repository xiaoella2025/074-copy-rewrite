import copy
import json
from pathlib import Path
import re
import unittest
from unittest.mock import patch
import server

LEGACY = (Path(__file__).parent / 'fixtures/culture_metadata_legacy.txt').read_text('utf8')


class CultureTitleTests(unittest.TestCase):
    def system_prompt(self, template, track='culture-knowledge'):
        settings = {'_prompt_template': template}
        before = copy.deepcopy(settings)
        response = {'title': '寺庙宫观有何不同', 'subtitle': ['寺庙宫观分属不同信仰', '建筑名字各有来由'],
                    'summary': 'fixture publishing', 'tags': ['#华夏文化', '#涨知识'], 'comments': ['fixture comment']}
        with patch.object(server, 'call_llm', return_value=json.dumps(response, ensure_ascii=False)) as llm:
            result = server.step1_meta(settings, '', '寺庙宫观分属不同信仰体系，命名各有来由。', [], track)
        self.assertEqual(llm.call_count, 1, 'Title policy must not add paid optimization requests')
        self.assertEqual(settings, before, 'Saved snapshots and user configuration must remain unchanged')
        self.assertEqual(result['title'], response['title'])
        self.assertEqual(result['tags'], response['tags'])
        self.assertEqual(result['comments'], response['comments'])
        return llm.call_args.args[1]

    def test_builtin_uses_specific_questions_instead_of_rotating_generic_suffixes(self):
        items = json.loads((server.ROOT / 'assets/prompt_templates.json').read_text('utf8'))
        template = next(t for t in items if t['id'] == 'culture-knowledge')
        system = self.system_prompt(template)
        self.assertNotIn('从下列词库轮换选用', system)
        self.assertIn('正文中的具体问题', system)
        self.assertIn('不得编造', system)
        self.assertIn('只在内部比较', system)
        examples = []
        for raw in re.findall(r'```json\s*([\s\S]*?)```', template['step1MetadataSystemPrompt']):
            item = json.loads(raw)
            if not item['title'].startswith('{'):
                examples.append(item['title'])
        self.assertGreaterEqual(len(examples), 3)
        self.assertTrue(all(not re.search(r'的(?:门道|讲究|秘密|密码|玄机|哲学)$', t) for t in examples))

    def test_exact_legacy_snapshot_is_upgraded_without_rewriting_saved_config(self):
        system = self.system_prompt({'id': 'culture-knowledge', 'step1MetadataSystemPrompt': LEGACY})
        self.assertNotIn('从下列词库轮换选用', system)
        self.assertIn('正文中的具体问题', system)

    def test_user_modified_culture_template_is_preserved_verbatim(self):
        custom = LEGACY + '\n用户自定义：标题按本人固定栏目命名。'
        system = self.system_prompt({'id': 'culture-knowledge', 'step1MetadataSystemPrompt': custom})
        self.assertTrue(system.startswith(custom))

    def test_other_track_custom_template_is_not_silently_replaced(self):
        system = self.system_prompt({'id': 'custom-fixture', 'step1MetadataSystemPrompt': LEGACY}, 'general')
        self.assertTrue(system.startswith(LEGACY))

    def test_legacy_windows_line_endings_are_recognized(self):
        system = self.system_prompt({'id': 'culture-knowledge', 'step1MetadataSystemPrompt': LEGACY.replace('\n', '\r\n')})
        self.assertNotIn('从下列词库轮换选用', system)


if __name__ == '__main__':
    unittest.main()
