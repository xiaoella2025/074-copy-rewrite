"""Isolated 1.25 safety contracts: no providers, installed files or settings reads."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

import story1250_safety as safety


class PathSafetyTests(unittest.TestCase):
    def setUp(self):
        # Lexical fixture drives/UNC shares must never access a real machine.
        actual = Path.resolve

        def fixture_resolve(path, *args, **kwargs):
            value = str(path).lower()
            if value.startswith(('c:', 'd:', '\\\\host\\', '\\\\?\\')):
                return path
            return actual(path, *args, **kwargs)

        self.addCleanup(patch.stopall)
        patch.object(Path, 'resolve', fixture_resolve).start()

    def test_same_or_nested_windows_paths_are_rejected(self):
        data = r'C:\App074\data'
        for draft in (r'c:/APP074/data/', r'C:\App074', r'C:\App074\data\drafts',
                      r'C:\App074\drafts\..\data', r'\\?\C:\App074\data',
                      r'C:\App074\data. '):
            with self.subTest(draft=draft), self.assertRaisesRegex(ValueError, '重叠'):
                safety.validate_draft_path(draft, data)

    def test_siblings_and_different_drives_are_disjoint(self):
        for draft in (r'C:\App074\data-other', r'C:\App074\drafts', r'D:\data'):
            safety.validate_draft_path(draft, r'C:\App074\data')
        safety.validate_draft_path('', r'C:\App074\data')

    def test_unc_share_paths_compare_by_components(self):
        with self.assertRaisesRegex(ValueError, '重叠'):
            safety.validate_draft_path(r'\\?\UNC\HOST\share\data\drafts', r'\\host\share\data')
        safety.validate_draft_path(r'\\host\share2\data', r'\\host\share\data')

    def test_space_suffixed_parent_segment_still_rejects_alias(self):
        with self.assertRaisesRegex(ValueError, '重叠'):
            safety.validate_draft_path(r'C:\App074\drafts\.. \data', r'C:\App074\data')

    def test_relative_or_malformed_draft_path_is_rejected(self):
        for draft in ('data/drafts', 'C:relative', 'C:\\bad\x00name', 42):
            with self.subTest(draft=draft), self.assertRaises(ValueError):
                safety.validate_draft_path(draft, r'C:\App074\data')

    def test_junction_resolution_includes_existing_ancestor_for_new_children(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            alias, data = root / 'alias', root / 'data'
            real_resolve = Path.resolve

            def resolve(path, *args, **kwargs):
                if path == alias / 'new-drafts':
                    return real_resolve(data / 'new-drafts')
                return real_resolve(path, *args, **kwargs)

            with patch.object(Path, 'resolve', resolve), self.assertRaisesRegex(ValueError, '重叠'):
                safety.validate_draft_path(str(alias / 'new-drafts'), data)

    def test_unresolvable_junction_reports_validation_error(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(Path, 'resolve', side_effect=RuntimeError('junction loop')):
                with self.assertRaisesRegex(ValueError, '无法核对'):
                    safety.validate_draft_path(str(Path(directory) / 'drafts'), Path(directory) / 'data')


class RuntimeHealthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / '_internal'
        self.root.mkdir()
        self.backend = SimpleNamespace(ROOT=self.root, DATA_DIR=Path(self.temp.name) / 'data',
                                       load_settings=Mock(side_effect=AssertionError('must not read settings')))

    def manifest(self, content=b'MZfixture-generator'):
        executable = self.root / 'draft-generator.exe'
        executable.write_bytes(content)
        (self.root.parent / 'backend-runtime.json').write_text(json.dumps({
            'files': {'_internal/draft-generator.exe': hashlib.sha256(content).hexdigest()}
        }), 'utf8')
        return executable

    def test_health_verifies_manifest_and_never_executes_or_reads_settings(self):
        self.manifest()
        ffmpeg = self.root / 'ffmpeg.exe'
        ffmpeg.write_bytes(b'MZfixture-ffmpeg')
        with patch.object(safety.shutil, 'which', return_value=None), \
             patch('subprocess.run') as run, patch('subprocess.Popen') as spawn:
            result = safety.health(self.backend)
        run.assert_not_called()
        spawn.assert_not_called()
        self.assertEqual(set(result), {'ok', 'draft_generator', 'ffmpeg'})
        self.assertTrue(result['ok'])
        self.assertEqual(result['draft_generator']['status'], 'ready')
        self.backend.load_settings.assert_not_called()
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_missing_and_unregistered_generator_produce_actionable_warning(self):
        with patch.object(safety.shutil, 'which', return_value=None):
            missing = safety.health(self.backend)
            self.assertEqual(missing['draft_generator']['status'], 'missing')
            self.assertEqual(missing['ffmpeg']['status'], 'missing')
            (self.root / 'draft-generator.exe').write_bytes(b'MZfixture')
            unregistered = safety.health(self.backend)
        self.assertFalse(unregistered['ok'])
        self.assertEqual(unregistered['draft_generator']['status'], 'unverified')
        self.assertIn('重新安装', unregistered['draft_generator']['message'])

    def test_digest_or_mz_mismatch_never_claims_ready(self):
        executable = self.manifest()
        executable.write_bytes(b'MZchanged')
        with patch.object(safety.shutil, 'which', return_value=None):
            self.assertEqual(safety.health(self.backend)['draft_generator']['status'], 'invalid')
            self.manifest(b'not-a-windows-executable')
            self.assertEqual(safety.health(self.backend)['draft_generator']['status'], 'invalid')

    def test_invalid_manifest_and_io_failure_are_safe_statuses(self):
        self.manifest()
        (self.root.parent / 'backend-runtime.json').write_text('[]', 'utf8')
        with patch.object(safety.shutil, 'which', return_value=None):
            self.assertEqual(safety.health(self.backend)['draft_generator']['status'], 'unverified')
            with patch.object(Path, 'open', side_effect=PermissionError('sensitive path')):
                result = safety.health(self.backend)
        self.assertFalse(result['ok'])
        self.assertNotIn('sensitive path', json.dumps(result))


class InstallationTests(unittest.TestCase):
    def setUp(self):
        class Handler:
            def do_GET(handler):
                return 'existing:' + handler.path

        self.original = Handler.do_GET
        self.backend = SimpleNamespace(Handler=Handler, DATA_DIR=r'C:\App074\data',
                                       ROOT=Path('unused-root'),
                                       _merged=lambda values: {'jianying': {'draft_path': values.get('jianying_draft_path', '')},
                                                               'other': 'preserved'})
        safety.install(self.backend)

    def handler(self, path, authorized=True):
        handler = self.backend.Handler()
        handler.path = path
        handler._desktop_authorized = Mock(return_value=authorized)
        handler._json = Mock()
        return handler

    def test_merged_rejects_conflicts_before_caller_can_save(self):
        with self.assertRaisesRegex(ValueError, '重叠'):
            self.backend._merged({'jianying_draft_path': r'C:\App074'})
        self.assertEqual(self.backend._merged({'jianying_draft_path': r'D:\Drafts'})['other'], 'preserved')

    def test_install_is_idempotent_and_other_routes_delegate(self):
        once = self.backend.Handler.do_GET
        safety.install(self.backend)
        self.assertIs(self.backend.Handler.do_GET, once)
        handler = self.handler('/index.html?resume=fake')
        self.assertEqual(handler.do_GET(), 'existing:/index.html?resume=fake')
        handler._desktop_authorized.assert_not_called()

    def test_health_requires_auth_and_matches_url_path(self):
        with patch.object(safety, 'health', return_value={'ok': True}) as inspect:
            denied = self.handler('/api/runtime/health?refresh=1', False)
            denied.do_GET()
            inspect.assert_not_called()
            denied._json.assert_not_called()
            allowed = self.handler('/api/runtime/health?refresh=1')
            allowed.do_GET()
            inspect.assert_called_once_with(self.backend)
            allowed._json.assert_called_once_with(200, {'ok': True})

    def test_draft_path_check_uses_fixed_backend_data_and_auth(self):
        handler = self.handler('/api/runtime/draft-path-check?path=C%3A%2FApp074%2Fdata%2Fdrafts&data_dir=D%3A%2Felsewhere')
        handler.do_GET()
        code, response = handler._json.call_args.args
        self.assertEqual(code, 200)
        self.assertFalse(response['valid'])
        self.assertIn('重叠', response['error'])
        denied = self.handler('/api/runtime/draft-path-check?path=D%3A%2Fdrafts', False)
        denied.do_GET()
        denied._json.assert_not_called()


if __name__ == '__main__':
    unittest.main()
