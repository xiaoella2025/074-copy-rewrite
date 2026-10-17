import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import benchmark


class AsrRaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.backend = SimpleNamespace(DATA_DIR=Path(self.temp.name))
        self.identity = {'accountId':'v2_fixture', 'feedId':'same'}
        benchmark._write(self.backend, {'version':1, 'accounts':[], 'feeds':[
            {**self.identity, 'transcript':'old', 'transcriptReviewed':''}]})
        self.media = self.backend.DATA_DIR/'fixture.mp3'
        self.media.write_bytes(b'fixture')

    def recognize(self, during=lambda:None):
        def run(path):
            during()
            return [{'text':'machine result'}]
        self.backend._local_asr_transcribe = Mock(side_effect=run)
        return benchmark.transcribe(self.backend, {**self.identity, 'path':str(self.media)})

    def test_manual_raw_and_reviewed_edits_are_preserved(self):
        for field in ('transcript', 'transcriptReviewed'):
            with self.subTest(field=field):
                def edit():
                    benchmark.edit(self.backend, {**self.identity, 'changes':{field:'manual '+field}})
                with self.assertRaisesRegex(ValueError, '修改|变化'):
                    self.recognize(edit)
                self.assertEqual(benchmark.state(self.backend)['feeds'][0][field], 'manual '+field)
                self.assertNotIn(tuple(self.identity.values()), benchmark.ASR_RUNNING)

    def test_deleted_feed_is_not_restored(self):
        def remove():
            with benchmark.LOCK:
                value=benchmark._read(self.backend);value['feeds']=[];benchmark._write(self.backend,value)
        with self.assertRaises(ValueError):self.recognize(remove)
        self.assertEqual(benchmark.state(self.backend)['feeds'], [])

    def test_metrics_change_is_preserved_and_does_not_block_asr(self):
        def metrics():
            with benchmark.LOCK:
                value=benchmark._read(self.backend);value['feeds'][0]['fav']=12;benchmark._write(self.backend,value)
        result=self.recognize(metrics)
        self.assertEqual(result['fav'],12)
        self.assertEqual(result['transcript'],'machine result')

    def test_normal_result_and_failure_release_running(self):
        self.assertEqual(self.recognize()['transcript'],'machine result')
        self.backend._local_asr_transcribe=Mock(side_effect=RuntimeError('fixture'))
        with self.assertRaises(RuntimeError):benchmark.transcribe(self.backend,{**self.identity,'path':str(self.media)})
        self.assertNotIn(tuple(self.identity.values()),benchmark.ASR_RUNNING)
