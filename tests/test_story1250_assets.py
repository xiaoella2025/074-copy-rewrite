import base64
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import server
import music_library


class Asset1250Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.backend = SimpleNamespace(DATA_DIR=self.root, ROOT=self.root, load_settings=lambda: {})
        self.ident = 'a' * 64
        self.music = self.root / 'music'; self.music.mkdir()
        (self.music / (self.ident + '.mp3')).write_bytes(b'fixture audio')
        record = {'id': self.ident, 'name': 'fixture', 'ext': 'mp3', 'number': 1, 'category': '未分类',
                  'duration': 1, 'size': 13, 'created': 1}
        (self.music / (self.ident + '.json')).write_text(json.dumps(record), 'utf8')

    def test_delete_removes_library_entry_without_touching_owned_task_audio(self):
        task = self.root / 'tasks/fixture'; task.mkdir(parents=True)
        owned = task / 'task-bgm.mp3'; owned.write_bytes(b'owned audio')
        result = music_library.remove_track(self.backend, self.ident)
        self.assertTrue(result['ok'])
        self.assertFalse((self.music / (self.ident + '.mp3')).exists())
        self.assertEqual(music_library.list_tracks(self.backend)['tracks'], [])
        self.assertEqual(owned.read_bytes(), b'owned audio')

    def test_legacy_reference_retains_file_and_saved_configuration(self):
        task = self.root / 'tasks/fixture'; task.mkdir(parents=True)
        config = task / 'client_config.json'
        config.write_text(json.dumps({'image': {'bgmPath': str(self.music / (self.ident + '.mp3'))}}), 'utf8')
        before = config.read_bytes()
        result = music_library.remove_track(self.backend, self.ident)
        self.assertTrue(result['retainedFile'])
        self.assertTrue((self.music / (self.ident + '.mp3')).exists())
        self.assertEqual(music_library.list_tracks(self.backend)['tracks'], [])
        self.assertEqual(before, config.read_bytes())

    def test_invalid_or_builtin_deletion_never_removes_files(self):
        for ident in ['builtin', '../outside', '', None]:
            with self.subTest(ident=ident), self.assertRaises(ValueError):
                music_library.remove_track(self.backend, ident)
        self.assertTrue((self.music / (self.ident + '.mp3')).exists())

    def test_completed_legacy_repack_metadata_keeps_library_audio(self):
        task = self.root / 'tasks/legacy'; task.mkdir(parents=True)
        (task / '06-draft-meta.json').write_text(json.dumps({'bgm_path': str(self.music / (self.ident + '.mp3'))}), 'utf8')
        self.assertTrue(music_library.remove_track(self.backend, self.ident)['retainedFile'])
        self.assertTrue((self.music / (self.ident + '.mp3')).is_file())

    def test_material_open_checks_links_before_creating_folder(self):
        import story1250_assets
        with patch.object(story1250_assets.material_groups, 'safe', side_effect=ValueError('unsafe')), patch.object(Path, 'mkdir') as mkdir:
            with self.assertRaises(ValueError): story1250_assets.open_material_folder(self.backend, {})
        mkdir.assert_not_called()

    def test_sound_paths_must_come_from_owned_uploads(self):
        from template_store import TemplateStore
        item = json.loads((Path(__file__).resolve().parents[1] / 'assets/draft_templates.json').read_text('utf8'))[0]
        external = self.root / 'external.wav'; external.write_bytes(b'fixture')
        item['config']['audio']['soundEffects'] = [{'name':'fixture', 'path':str(external)}]
        store = TemplateStore(self.root, Path(__file__).resolve().parents[1])
        with self.assertRaisesRegex(ValueError, '重新上传'): store.save('drafts', item)
        folder = self.root / 'template-sounds'; folder.mkdir()
        owned = folder / 'fixture.wav'; owned.write_bytes(b'fixture')
        item['config']['audio']['soundEffects'][0]['path'] = str(owned)
        self.assertTrue(store.save('drafts', item)['id'])

    def test_sound_upload_is_owned_deduplicated_and_validates_audio(self):
        import story1250_assets
        body = {'name': '../../effect.mp3', 'data_url': 'data:audio/mpeg;base64,' + base64.b64encode(b'fixture audio').decode()}
        with patch.object(music_library, '_inspect_audio', return_value=('mp3', 1, '')) as probe:
            first = story1250_assets.upload_sound(self.backend, body)
            second = story1250_assets.upload_sound(self.backend, body)
        self.assertEqual(first['path'], second['path'])
        self.assertTrue(Path(first['path']).resolve().is_relative_to((self.root / 'template-sounds').resolve()))
        self.assertEqual(first['duration'], 1)
        with patch.object(music_library, '_inspect_audio', side_effect=ValueError('not audio')):
            with self.assertRaises(ValueError): story1250_assets.upload_sound(self.backend, {**body, 'data_url': 'data:audio/mpeg;base64,YmFk'})


if __name__ == '__main__': unittest.main()
