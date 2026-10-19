"""Cover publication metadata reuses its existing, isolated planning request."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import image_lab


class CoverMetadata1250Tests(unittest.TestCase):
    def test_existing_request_adds_five_grounded_comments_and_persists_metadata(self):
        metadata = {'title': '修桥的人', 'short_title': '村民修旧桥', 'summary': '村民修复旧桥的故事', 'tags': ['#旧桥'],
                    'comments': ['桥面用旧木料，雨天防滑怎么处理？'] * 5}
        with tempfile.TemporaryDirectory() as directory:
            backend = SimpleNamespace(
                ROOT=Path(__file__).resolve().parents[1], DATA_DIR=Path(directory),
                load_settings=lambda: {}, resolve_image_config=lambda *_: {'provider': 'gpt_image', 'api_key': 'fake'},
                story_workflow_reference=lambda: {'styles': []}, image_job_options=lambda *_: ('3:4', '1k'),
                resolve_active_llm_settings=lambda *_: {'api_key': 'fake'},
                parse_llm_json=json.loads, call_llm=Mock(return_value=json.dumps(metadata)),
                build_cover_prompt=Mock(return_value='保持原有封面构图'),
                image_dispatcher=Mock(return_value={'b64': 'fake'}),
                save_cover_image=lambda *_: '/covers/fake.png', image_job_concurrency=lambda *_: 1)
            result = image_lab.generate(backend, {'mode': 'cover', 'prompt': '村民用旧木料修桥', 'count': 2})
            backend.call_llm.assert_called_once()
            prompt = backend.call_llm.call_args.args[1]
            self.assertIn('悬念 + 反差 + 钩子', prompt)
            self.assertIn('comments', prompt)
            self.assertIn('short_title', prompt)
            self.assertIn('5', prompt)
            self.assertIn('具体内容', prompt)
            self.assertIn('不要编造', prompt)
            self.assertEqual(result['items'][0]['metadata'], metadata)
            self.assertEqual(len(image_lab.history(Path(directory))), 2)
            self.assertEqual(image_lab.history(Path(directory))[0]['metadata']['comments'], metadata['comments'])

    def test_delete_failed_history_only_preserves_successful_assets_and_rejects_paths(self):
        self.assertTrue(callable(getattr(image_lab,'delete_history',None)),'failed records need a bounded delete action')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);folder=root/'image-lab';folder.mkdir()
            failed_id='a'*32;success_id='b'*32
            failed=folder/(failed_id+'.json');success=folder/(success_id+'.json')
            failed.write_text(json.dumps({'id':failed_id,'ok':False,'error':'下载失败'}),'utf8')
            success.write_text(json.dumps({'id':success_id,'ok':True,'url':'/covers/keep.png'}),'utf8')
            image=root/'covers'/'keep.png';image.parent.mkdir();image.write_bytes(b'preserve')
            for identity in [success_id,'../covers/keep.png','not-an-id']:
                with self.subTest(identity=identity),self.assertRaises(ValueError):
                    image_lab.delete_history(root,identity)
            self.assertTrue(failed.exists());self.assertTrue(success.exists())
            self.assertEqual(image_lab.delete_history(root,failed_id),{'ok':True})
            self.assertFalse(failed.exists());self.assertTrue(success.exists());self.assertEqual(image.read_bytes(),b'preserve')


if __name__ == '__main__':
    unittest.main()
