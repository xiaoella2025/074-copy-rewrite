import json
from pathlib import Path
import tempfile
import unittest
from captions import build_captions, plain, save_captions, split_lines, task_captions
from jianying_export import register_draft


class CaptionExportTests(unittest.TestCase):
    def test_long_sentences_keep_common_words_and_place_names_intact(self):
        examples = [
            ('你有没有带孩子逛名胜古迹的时候被问住过', ['名胜古迹']),
            ('它原本跟佛教一点关系都没有', ['关系']),
            ('朝廷把他们安顿在鸿胪寺里暂住', ['鸿胪寺']),
            ('你脑子里第一个蹦出来的是谁', ['出来']),
        ]
        for text, phrases in examples:
            with self.subTest(text=text):
                lines=split_lines(text,12)
                self.assertEqual(''.join(lines),plain(text))
                self.assertTrue(all(0<len(line)<=12 for line in lines))
                for phrase in phrases:
                    self.assertTrue(any(phrase in line for line in lines), (phrase,lines))

    def test_enumeration_does_not_create_single_character_flashing_captions(self):
        text='你知道寺、庙、观、庵、祠有什么区别吗？'
        lines=split_lines(text,12)
        self.assertEqual(''.join(lines),plain(text))
        self.assertTrue(all(3<=len(line)<=12 for line in lines),lines)

    def test_complete_comma_clauses_stay_separate_instead_of_joining_half_sentences(self):
        clauses=['搞懂了这句','你今天就值回这条视频了','先点个赞收藏起来','下次逛景点你一定用得上']
        self.assertEqual(split_lines('，'.join(clauses)+'。',12),clauses)

    def test_clear_recognition_pause_is_a_caption_boundary_without_punctuation(self):
        first,second='先把这件事讲清楚','再来解释第二件事情'
        item=build_captions([{'idx':1,'text':first+second}],
            [{'index':1,'duration':6,'asr_segments':[
                {'text':first,'start':.2,'end':2},
                {'text':second,'start':3,'end':5.8}]}])['items'][0]
        self.assertEqual(item['lines'],[first,second])
        self.assertEqual(item['cues'][0]['end'],2)
        self.assertEqual(item['cues'][1]['start'],3)

    def test_old_automatic_breaks_are_rebuilt_but_manual_breaks_stay(self):
        text='它原本跟佛教一点关系都没有'
        old=['它原本跟佛教一点关','系都没有']
        shots=[{'idx':1,'text':text}];segments=[{'index':1,'duration':4}]
        auto=build_captions(shots,segments,{'source':'rules','max_chars':12,'items':[{'id':1,'lines':old}]})
        self.assertNotEqual(auto['items'][0]['lines'],old)
        self.assertEqual(''.join(auto['items'][0]['lines']),text)
        manual=build_captions(shots,segments,{'source':'manual','max_chars':12,'items':[{'id':1,'lines':old}]})
        self.assertEqual(manual['items'][0]['lines'],old)

    def test_numbers_and_units_are_kept_together_and_limits_still_hold(self):
        text='这项工程在2026年完成总共花了2300万元'
        lines=split_lines(text,12)
        self.assertEqual(''.join(lines),plain(text))
        for number in ['2026年','2300万元']:
            self.assertTrue(any(number in line for line in lines),(number,lines))
        self.assertTrue(all(len(line)<=12 for line in lines))

    def test_small_template_limits_and_mixed_text_preserve_every_spoken_character(self):
        for limit in [1,2,4,8,12,20]:
            for text in ['你好，世界。','2026年10月17日发布','RunningHub与DeepSeek一起使用',
                         '甲、乙、丙；这是另一句话！','a.b,版本3.14发布了','']:
                with self.subTest(limit=limit,text=text):
                    lines=split_lines(text,limit)
                    self.assertEqual(''.join(lines),plain(text))
                    self.assertTrue(all(0<len(line)<=limit for line in lines))

    def test_manual_lines_use_template_limit_instead_of_fixed_twelve(self):
        text='字幕长度应按模板设置的上限校验'
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory)/'05-captions.json').write_text(json.dumps({
                'max_chars':20,'source':'rules','items':[]}),encoding='utf-8')
            result=save_captions(directory,[{'idx':1,'text':text}],
                [{'index':1,'duration':3}],[{'id':1,'lines':[text]}])
            self.assertEqual(result['max_chars'],20)
            self.assertEqual(result['items'][0]['lines'],[text])

    def test_short_lines_preserve_text_and_recognition_timing(self):
        text = '这是测试的字幕，内容比较长需要拆成短句。继续保持所有原文字词。'
        result = build_captions([{'idx':1,'text':text}], [{'index':1,'duration':12,
            'asr_segments':[{'text':text,'start':1,'end':11}]}])['items'][0]
        self.assertEqual(plain(''.join(result['lines'])), plain(text))
        self.assertTrue(all(len(x) <= 12 for x in result['lines']))
        self.assertGreater(len(result['lines']), 1)
        self.assertEqual(result['cues'][0]['start'], 1)
        self.assertEqual(result['cues'][-1]['end'], 11)
        for i, cue in enumerate(result['cues']):
            self.assertLess(cue['start'], cue['end'])
            self.assertLessEqual(cue['end'], 12)
            if i: self.assertLessEqual(result['cues'][i-1]['end'], cue['start'])

    def test_save_rejects_changed_script_without_overwriting(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                save_captions(directory, [{'idx':1,'text':'完整原文'}],
                    [{'index':1,'duration':2}], [{'id':1,'lines':['少字']}])
            self.assertFalse((Path(directory)/'05-captions.json').exists())

    def test_registration_preserves_other_drafts_and_root_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); folder = root/'project'; folder.mkdir()
            original = {'draft_fold_path':'other', 'draft_name':'keep', 'extra':[1,2]}
            index = root/'root_meta_info.json'
            index.write_text(json.dumps({'all_draft_store':[original], 'draft_ids':5, 'root_path':'existing'}),'utf-8')
            (folder/'draft_meta_info.json').write_text(json.dumps({'draft_name':'new','draft_id':'new'}),'utf-8')
            (folder/'draft_info.json').write_text('{"duration":2000000}','utf-8')
            register_draft(folder, index_path=index)
            register_draft(folder, index_path=index)
            saved=json.loads(index.read_text('utf-8'))
            self.assertEqual(saved['draft_ids'],5)
            self.assertEqual(saved['root_path'],'existing')
            self.assertEqual(saved['all_draft_store'][1],original)
            self.assertEqual(len(saved['all_draft_store']),2)
            self.assertEqual(saved['all_draft_store'][0]['tm_duration'],2000000)
            self.assertTrue(list(root.glob('root_meta_info.json.app074-backup-*')))
