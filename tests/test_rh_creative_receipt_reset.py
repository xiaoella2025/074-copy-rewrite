"""Explicit asset redraws archive RH receipts; resume keeps paid work recoverable."""
import io
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

from PIL import Image
import creative_workflows as creative
import server
import task_queue


class CreativeReceiptResetTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.addCleanup(patch.stopall)
        self.root = Path(temporary.name)
        patch.object(server, 'DATA_DIR', self.root).start()
        patch.object(task_queue, 'get_queue', return_value=types.SimpleNamespace(owns=lambda _: False, get=lambda _: None)).start()
        patch.object(creative, 'start', return_value={'queued': True}).start()
        patch.object(server, '_http_post_json', side_effect=AssertionError('network forbidden')).start()
        patch.object(server, '_http_get_json', side_effect=AssertionError('network forbidden')).start()
        patch.object(server, 'image_dispatcher', side_effect=AssertionError('supplier forbidden')).start()
        self.tid = 'html_' + 'c' * 32
        self.folder = creative.directory(server, self.tid)
        self.folder.mkdir(parents=True)
        creative.write(self.folder / 'creative.json', {
            'task_id': self.tid, 'kind': 'html', 'status': 'completed', 'title': 'fixture',
            'config': {'imageProvider': 'runninghub_workflow'}, 'timings': {},
            'completed': ['plan', 'assets', 'voice', 'preview', 'cover', 'output'],
            'shots': [{'idx': 1, 'text': 'narration', 'scene': 'old scene', 'prompt': 'old scene',
                       'elements': [{'slot': 0, 'prompt': 'old foreground'}]}]})
        output = io.BytesIO()
        Image.new('RGB', (8, 8), 'blue').save(output, 'PNG')
        self.image = output.getvalue()
        for name in ('1.png', 'fg_1_0.png', '2.png'):
            path = self.folder / 'covers' / name
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(self.image)

    def receipt(self, name, status='ok', result=True):
        directory = self.folder / 'covers' / '.rh-receipts' / name
        job = {'provider': 'runninghub_workflow', 'status': status, 'taskId': 'original-paid-id'}
        if result:
            job['result'] = {'url': 'https://fixture.invalid/original.png'}
        path = directory / 'image-jobs' / '1.json'
        creative.write(path, job)
        (directory / 'evidence.txt').write_bytes(b'keep receipt evidence')
        return directory, path.read_bytes()

    def redraw(self, foreground=False):
        data = {'index': 1, 'regenerate': 'image', 'changes': {'prompt': 'new scene'}}
        if foreground:
            data = {'index': 1, 'element': {'slot': 0, 'action': 'regenerate', 'prompt': 'new foreground'}}
        return creative.action(server, self.tid, 'scene', data)

    def assert_archived(self, name, raw):
        directory = self.folder / 'covers' / '.rh-receipts' / name
        self.assertFalse(directory.exists())
        self.assertFalse((self.folder / 'covers' / name).exists())
        archived = list((self.folder / 'rerun-archive').glob('*/covers/.rh-receipts/' + name))
        self.assertEqual(len(archived), 1)
        self.assertEqual((archived[0] / 'image-jobs' / '1.json').read_bytes(), raw)
        self.assertEqual((archived[0] / 'evidence.txt').read_bytes(), b'keep receipt evidence')
        archive_root = archived[0].parents[2]
        self.assertEqual((archive_root / 'covers' / name).read_bytes(), self.image)

    def test_background_redraw_archives_paid_result_and_leaves_other_assets(self):
        _, raw = self.receipt('1.png')
        other, other_raw = self.receipt('fg_1_0.png')
        self.redraw()
        self.assert_archived('1.png', raw)
        self.assertEqual((other / 'image-jobs' / '1.json').read_bytes(), other_raw)
        self.assertEqual((self.folder / 'covers' / 'fg_1_0.png').read_bytes(), self.image)

    def test_foreground_redraw_archives_terminal_receipt_and_only_selected_asset(self):
        _, raw = self.receipt('fg_1_0.png', 'failed', False)
        other, other_raw = self.receipt('1.png')
        self.redraw(True)
        self.assert_archived('fg_1_0.png', raw)
        self.assertEqual((other / 'image-jobs' / '1.json').read_bytes(), other_raw)
        self.assertEqual((self.folder / 'covers' / '1.png').read_bytes(), self.image)

    def test_inflight_or_unknown_receipt_blocks_redraw_before_any_file_changes(self):
        original = (self.folder / 'creative.json').read_bytes()
        for foreground, name in ((False, '1.png'), (True, 'fg_1_0.png')):
            for status in ('pending', 'unknown', 'submitting', 'download_pending'):
                with self.subTest(foreground=foreground, status=status):
                    directory, raw = self.receipt(name, status, False)
                    with self.assertRaisesRegex(ValueError, '原任务|在途|不明'):
                        self.redraw(foreground)
                    self.assertEqual((directory / 'image-jobs' / '1.json').read_bytes(), raw)
                    self.assertEqual((self.folder / 'covers' / name).read_bytes(), self.image)
                    self.assertEqual((self.folder / 'creative.json').read_bytes(), original)
                    self.assertFalse((self.folder / 'rerun-archive').exists())

    def test_download_pending_with_saved_result_can_be_explicitly_redrawn(self):
        _, raw = self.receipt('1.png', 'download_pending')
        self.redraw()
        self.assert_archived('1.png', raw)

    def test_prompt_save_keeps_receipt_and_image_for_ordinary_resume(self):
        directory, raw = self.receipt('1.png', 'pending', False)
        creative.action(server, self.tid, 'scene', {'index': 1, 'changes': {'prompt': 'new scene'}})
        self.assertEqual((directory / 'image-jobs' / '1.json').read_bytes(), raw)
        self.assertEqual((self.folder / 'covers' / '1.png').read_bytes(), self.image)
        self.assertFalse((self.folder / 'rerun-archive').exists())

    def test_corrupt_receipt_blocks_redraw_without_discarding_evidence(self):
        directory, _ = self.receipt('1.png')
        path = directory / 'image-jobs' / '1.json'
        path.write_bytes(b'{corrupt')
        with self.assertRaisesRegex(RuntimeError, '损坏|核对'):
            self.redraw()
        self.assertEqual(path.read_bytes(), b'{corrupt')
        self.assertEqual((self.folder / 'covers' / '1.png').read_bytes(), self.image)


if __name__ == '__main__':
    unittest.main()
