import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from template_store import TemplateStore, validate

ROOT = Path(__file__).resolve().parents[1]


class Template1250Tests(unittest.TestCase):
    def base(self):
        return copy.deepcopy(json.loads((ROOT / 'assets/draft_templates.json').read_text('utf-8'))[0])

    def test_defaults_round_trip_preserves_every_existing_field(self):
        defaults = json.loads((ROOT / 'assets/draft_templates.json').read_text('utf-8'))
        with tempfile.TemporaryDirectory() as directory:
            store = TemplateStore(directory, ROOT)
            for item in defaults:
                saved = store.save('drafts', item, item['id'])
                self.assertEqual(saved['config'], item['config'])
                self.assertEqual(store.resolve('drafts', item['id'])['config'], item['config'])

    def test_new_fields_round_trip_including_duplicate_sound_and_explicit_none(self):
        item = self.base()
        for layer in ('title', 'subtitle', 'caption', 'disclaimer'):
            item['config'][layer]['font'] = '得意黑'
        image = item['config']['image']
        image.update(effect='旧特效', effects=[])
        sound = dict(path='', jianyingId='6974688834588036388', duration=1, name='一滴水滴声', vip=False, volume=1, placement='start', atSeconds=0)
        item['config']['audio']['soundEffects'] = [sound, {**sound, 'placement': 'end'}]
        with tempfile.TemporaryDirectory() as directory:
            saved = TemplateStore(directory, ROOT).save('drafts', item)
            self.assertEqual(saved['config'], item['config'])
        self.assertEqual(item['config']['image']['effects'], [])

    def test_legacy_effect_migration_preserves_input_and_legacy_key(self):
        item = self.base()
        item['config']['image']['effect'] = '飘雪'
        result = validate('drafts', item)
        self.assertEqual(result['config']['image']['effects'], [{'name': '飘雪', 'mode': 'full'}])
        self.assertEqual(result['config']['image']['effect'], '飘雪')
        self.assertNotIn('effects', item['config']['image'])

    def test_reject_invalid_types_ranges_and_nonfinite_new_fields(self):
        def check(path, value):
            item = self.base()
            target = item['config']
            for key in path[:-1]:
                target = target.setdefault(key, {})
            target[path[-1]] = value
            with self.subTest(path=path, value=value), self.assertRaises(ValueError):
                validate('drafts', item)
        for value in (False, [], 9, {'name': 'x'}): check(('title','font'), value)
        for value in (None, {}, 'x', [{'name':'x','mode':'full'}] * 4, [{'name':'x','mode':'bad'}], [{'name':'x','mode':'head','seconds':float('nan')}], [{'name':'x','mode':'head','seconds':0}], [{'name':'x','mode':'head','seconds':True}]): check(('image','effects'), value)
        good = dict(path='C:/audio/a.wav', name='a', placement='start', volume=1, atSeconds=0)
        for value in ([good] * 6, [{**good, 'volume': 10.1}], [{**good, 'volume': float('inf')}], [{**good, 'atSeconds': -1}], [{**good, 'placement':'every_scene', 'everyN':1.5}], [{**good, 'duration':False}], [{**good, 'vip':'yes'}], [{**good, 'jianyingId':'bad'}], [{**good, 'path':42}], [{**good, 'placement':'unknown'}]): check(('audio','soundEffects'), value)
        self.assertEqual(validate('drafts', item := self.base())['config'], item['config'])

    def test_catalog_counts_flags_and_provenance(self):
        catalog=json.loads((ROOT / 'assets/draft_catalog1250.json').read_text('utf-8'))
        self.assertEqual(sum(not x['vip'] for x in catalog['fonts']),219)
        self.assertEqual(sum(x['vip'] for x in catalog['fonts']),116)
        self.assertEqual(sum(not x['vip'] for x in catalog['effects']),615)
        self.assertEqual(sum(x['vip'] for x in catalog['effects']),298)
        self.assertEqual(catalog['sounds'],[{'name':'\u4e00\u6ef4\u6c34\u6ef4\u58f0','id':'6974688834588036388','duration':1,'vip':False,'group':'\u6c34\u58f0'}])
        self.assertEqual(catalog['limits']['soundEffects'],5)
        self.assertEqual(len(catalog['provenance']['templateEditor']['sha256']),64)

    def test_catalog_matches_audited_literals_without_executing_vendor_code(self):
        audit = ROOT / '.desktop-tools/story1250-audit'
        if not (audit / 'template-literal-arrays.json').exists():
            self.skipTest('vendor audit is not part of the installed application')
        arrays = json.loads((audit / 'template-literal-arrays.json').read_text('utf-8'))
        catalog = json.loads((ROOT / 'assets/draft_catalog1250.json').read_text('utf-8'))
        self.assertEqual([x['name'] for x in catalog['fonts']], arrays['Ce'] + arrays['ye'])
        self.assertEqual([x['name'] for x in catalog['effects']], arrays['Te'] + arrays['Re'] + arrays['_e'])
        self.assertEqual(catalog['recommendedFonts'], arrays['Se'])
        self.assertEqual(catalog['recommendedEffects'], arrays['Fe'])
        for key in ('templateEditor', 'index'):
            source = catalog['provenance'][key]
            raw = (audit / 'frontend/assets' / source['module']).read_bytes()
            self.assertEqual(source['sha256'], hashlib.sha256(raw).hexdigest())


if __name__ == '__main__': unittest.main()
