"""Real offline acceptance of the extracted 1.25 sidecar, in disposable roots.

No installed executable, user draft index, provider, or API key is used.
Set APP074_EXPORT1250_EVIDENCE to an existing private directory to retain a
sanitized structural report (fixture names and paths are synthetic).
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import wave

from PIL import Image

import jianying_export

ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / '.desktop-tools/story1250-audit/installer/draft-generator.exe'


@unittest.skipUnless(os.name == 'nt' and CANDIDATE.is_file(),
                     'extracted Windows Story 1.25 offline generator candidate absent')
class Draft1250ExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which('ffmpeg'):
            raise unittest.SkipTest('local ffmpeg fixture generator unavailable')
        cls.temporary = tempfile.TemporaryDirectory(prefix='app074-export1250-')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        if not str(cls.root).isascii():
            raise unittest.SkipTest('isolated sidecar acceptance needs an ASCII temporary root')
        cls.app = cls.root / 'app'
        (cls.app / 'assets').mkdir(parents=True)
        shutil.copy2(CANDIDATE, cls.app / 'draft-generator.exe')
        shutil.copy2(ROOT / 'assets/draft_templates.json', cls.app / 'assets/draft_templates.json')
        cls.candidate_hash = hashlib.sha256(CANDIDATE.read_bytes()).hexdigest()
        cls.data = cls.root / 'data'
        cls.task = cls.data / 'tasks/task_1792368000000_offline1250'
        (cls.task / 'covers').mkdir(parents=True)
        (cls.task / 'audio').mkdir()
        for idx in range(1, 6):
            Image.new('RGB', (180, 320), (20 + idx * 25, 65, 100)).save(cls.task / f'covers/{idx}.png')
        audio = cls.task / 'audio/seg_001.mp3'
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi',
                        '-i', 'sine=frequency=300:duration=1.2', '-y', str(audio)],
                       capture_output=True, check=True, timeout=30,
                       creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        for idx in range(2, 6):
            shutil.copy2(audio, cls.task / f'audio/seg_{idx:03}.mp3')
        (cls.data / 'template-sounds').mkdir()
        cls.local_sound = cls.data / 'template-sounds/local-sfx.wav'
        with wave.open(str(cls.local_sound), 'wb') as output:
            output.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
            output.writeframes(b'\0\0' * 4000)
        cls._write(cls.task / '03-shots.json', [{'idx': idx, 'text': f'离线字幕{idx}。'} for idx in range(1, 6)])
        # Use saved manual cue lines: font/export acceptance does not require
        # installing or substituting the optional Chinese segmentation package.
        cls._write(cls.task / '05-captions.json', {'source': 'manual', 'max_chars': 12,
                   'items': [{'id': idx, 'lines': [f'离线字幕{idx}']} for idx in range(1, 6)]})
        cls._write(cls.task / '05-tts-segments.json', [{'index': idx, 'duration': 1.2} for idx in range(1, 6)])
        cls._write(cls.task / '02-meta.json', {'title': '离线主标题', 'subtitle': ['副标题第一行', '副标题第二行']})
        cls.drafts = cls.root / 'drafts'
        cls.drafts.mkdir()
        cls.index = cls.root / 'root_meta_info.json'
        cls._write(cls.index, {'all_draft_store': []})
        cls.snapshot = copy.deepcopy(json.loads((cls.app / 'assets/draft_templates.json').read_text('utf-8'))[0])
        cls.fonts = {'title': '得意黑', 'subtitle': '抖音美好体', 'caption': 'MiSans-Regular', 'disclaimer': '思源中宋'}
        for key, font in cls.fonts.items():
            cls.snapshot['config'][key]['font'] = font
        cls.snapshot['config']['image']['effects'] = [
            {'name': '飘雪', 'mode': 'head', 'seconds': .75},
            {'name': '暗角', 'mode': 'full'},
            {'name': '丁达尔光线', 'mode': 'full'},
        ]
        water = {'path': '', 'name': '一滴水滴声', 'jianyingId': '6974688834588036388',
                 'duration': 1, 'vip': False, 'volume': 1}
        local = {'path': str(cls.local_sound), 'name': 'local fixture', 'volume': .5}
        cls.snapshot['config']['audio']['soundEffects'] = [
            {**water, 'placement': 'start', 'atSeconds': .4},
            {**water, 'placement': 'every_scene', 'everyN': 2},
            {**local, 'placement': 'end'},
            {**local, 'placement': 'start', 'atSeconds': 1.4},
        ]
        cls.result = jianying_export.export_draft(
            cls.task, cls.drafts, cls.app,
            {'template_id': cls.snapshot['id'], 'template_snapshot': cls.snapshot, 'bgm_path': ''},
            index_path=cls.index)
        cls.folder = Path(cls.result['draft_dir'])
        cls.content = json.loads(Path(cls.result['draft_content_path']).read_text('utf-8'))
        cls.materials = cls.content['materials']
        evidence = os.environ.get('APP074_EXPORT1250_EVIDENCE')
        if evidence:
            destination = Path(evidence).resolve()
            if not destination.is_dir():
                raise ValueError('APP074_EXPORT1250_EVIDENCE must be an existing private directory')
            cls._write(destination / 'offline-generator1250-structure.json', {
                'candidate_sha256': cls.candidate_hash,
                'duration': cls.content.get('duration'),
                'tracks': cls.content.get('tracks'),
                'materials': {key: cls.materials.get(key) for key in ('texts', 'video_effects', 'audios')},
                'key_values': cls.content.get('key_values'),
                'key_value_file': json.loads((cls.folder / 'key_value.json').read_text('utf-8')),
                'draft_files': [str(p.relative_to(cls.folder)) for p in cls.folder.rglob('*') if p.is_file()],
            })

    @staticmethod
    def _write(path, value):
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), 'utf-8')

    def text_tracks(self):
        materials = {m['id']: m for m in self.materials['texts']}
        return {t['name']: (t, materials[t['segments'][0]['material_id']])
                for t in self.content['tracks'] if t['type'] == 'text' and t['segments']}

    def test_all_paths_and_registration_are_inside_temporary_roots(self):
        self.assertTrue(self.folder.is_relative_to(self.drafts))
        self.assertEqual(Path(self.result['registered_index']), self.index)
        self.assertEqual(len(json.loads(self.index.read_text('utf-8'))['all_draft_store']), 1)
        self.assertEqual(hashlib.sha256(CANDIDATE.read_bytes()).hexdigest(), self.candidate_hash)

    def test_four_font_resources_survive_subtitle_rebuild(self):
        tracks = self.text_tracks()
        for name in ('cover_title', 'cover_subtitle', 'subtitle', 'cover_disclaimer'):
            with self.subTest(track=name):
                material = tracks[name][1]
                content = json.loads(material['content'])
                font = content['styles'][0].get('font', {})
                self.assertTrue(font.get('id'), f'{name} has no font resourceID: {font}')
        expected = {'cover_title': '7399865900821647935', 'cover_subtitle': '7244518590332801592',
                    'subtitle': '7265596106581479991', 'cover_disclaimer': '6807743192671195655'}
        for name, identifier in expected.items():
            material = tracks[name][1]
            self.assertEqual(json.loads(material['content'])['styles'][0]['font']['id'], identifier)
        # Native Story stores these IDs inside rich text styles; its blank
        # legacy material-level font fields are not evidence of an absent font.

    def test_three_effect_tracks_keep_independent_durations_below_text(self):
        effects = [t for t in self.content['tracks'] if t['type'] == 'effect']
        self.assertEqual(len(effects), 3)
        durations = sorted(t['segments'][0]['target_timerange']['duration'] for t in effects)
        self.assertEqual(durations, [750000, self.content['duration'], self.content['duration']])
        texts = [segment['render_index'] for track in self.content['tracks'] if track['type'] == 'text' for segment in track['segments']]
        effect_indices = [segment['render_index'] for track in effects for segment in track['segments']]
        self.assertLess(max(effect_indices), min(texts))

    def test_sound_placements_and_repeated_source_keep_independent_segments(self):
        audio = [t for t in self.content['tracks'] if t['type'] == 'audio']
        sfx = [t for t in audio if t.get('name', '').startswith('sfx_')]
        self.assertEqual(len(sfx), 4, f'audio track names: {[t.get("name") for t in audio]}')
        self.assertEqual([s['target_timerange']['start'] for s in sfx[0]['segments']], [400000])
        # everyN=2 means every second transition: scenes 3 and 5 for five scenes.
        self.assertEqual([s['target_timerange']['start'] for s in sfx[1]['segments']], [2400000, 4800000])
        self.assertEqual(sfx[2]['segments'][0]['target_timerange']['start'], self.content['duration'] - 250000)
        self.assertEqual(sfx[3]['segments'][0]['target_timerange']['start'], 1400000)

    def test_local_sound_assets_are_copied_and_selfcontained_key_values(self):
        local_materials = [m for m in self.materials['audios'] if Path(m.get('path', '')).name.endswith(self.local_sound.name)]
        self.assertEqual(len(local_materials), 2, 'both local fixture placements need self-contained material files')
        for material in local_materials:
            target = Path(material['path'])
            self.assertTrue(target.is_file())
            self.assertTrue(target.resolve().is_relative_to(self.folder), f'nonportable local audio: {target}')
            self.assertEqual(target.read_bytes(), self.local_sound.read_bytes())
        key_values = json.loads((self.folder / 'key_value.json').read_text('utf-8'))
        self.assertTrue(key_values, 'portable draft key_value.json missing')
        self.assertEqual(key_values['6974688834588036388']['is_vip'], '0')
        self.assertEqual(key_values['6974688834588036388']['materialCategory'], 'audio')
        remote_ids = {m['id'] for m in self.materials['audios'] if m.get('resource_id') == '6974688834588036388'}
        self.assertEqual(len(remote_ids), 2, 'repeated catalog selections must remain independent material entries')
        remote_segments = [segment for track in self.content['tracks'] for segment in track['segments']
                           if segment['material_id'] in remote_ids]
        self.assertEqual(len(remote_segments), 3)
        for segment in remote_segments:
            self.assertEqual(key_values[segment['id']]['materialId'], '6974688834588036388')
            self.assertEqual(key_values[segment['id']]['segmentId'], segment['id'])

    def test_existing_text_content_size_visibility_and_positions_are_preserved(self):
        tracks = self.text_tracks()
        for name, key, text in [('cover_title', 'title', '离线主标题'),
                                ('cover_subtitle', 'subtitle', '副标题第一行\n副标题第二行'),
                                ('cover_disclaimer', 'disclaimer', self.snapshot['config']['disclaimer']['text'])]:
            with self.subTest(track=name):
                track, material = tracks[name]
                content = json.loads(material['content'])
                cfg = self.snapshot['config'][key]
                self.assertEqual(content['text'], text)
                self.assertEqual(content['styles'][0]['size'], cfg['fontSize'])
                # Story omits global_alpha for fully opaque text, and places
                # non-unit fill opacity in the rich text solid definition.
                self.assertAlmostEqual(material.get('global_alpha', 1), cfg['alpha'])
                self.assertAlmostEqual(track['segments'][0]['clip']['transform']['y'], cfg['y'])
                self.assertEqual(track['segments'][0]['target_timerange']['duration'], self.content['duration'])


if __name__ == '__main__':
    unittest.main()
