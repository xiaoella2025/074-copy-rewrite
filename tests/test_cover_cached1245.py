import base64
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
import server
import task_cover


class CachedCoverTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.data=Path(self.temp.name);self.tid='fixture'
        self.folder=self.data/'tasks'/self.tid;self.folder.mkdir(parents=True)
        change=patch.object(server,'DATA_DIR',self.data);change.start();self.addCleanup(change.stop)
        task_cover.write(self.folder/'02-meta.json',{'title':'fixture','cover_image_prompts':['fixture visual']})
        stream=io.BytesIO();Image.new('RGB',(32,48)).save(stream,'PNG');self.png=stream.getvalue()
        self.job={'operationId':'fixture-op','status':'download_pending','provider':'runninghub',
                  'result':{'b64':base64.b64encode(self.png).decode()}}
        task_cover.write(self.folder/'cover-job-1.json',self.job)

    def test_cached_result_is_recovered_without_loading_provider_configuration(self):
        with patch.object(server,'load_settings',side_effect=AssertionError('cached result needs no settings')),patch.object(server,'resolve_image_config',side_effect=AssertionError('no provider config')),patch.object(server,'image_dispatcher',side_effect=AssertionError('no new purchase')):
            result=task_cover.action(server,self.tid,'query',{})
        self.assertEqual(result['job']['status'],'ok')
        self.assertEqual((self.folder/'cover-poster-1.png').read_bytes(),self.png)

    def test_same_completed_operation_returns_owned_image_without_settings(self):
        task_cover.commit(server,self.tid,1,self.png,{'provider':'runninghub'})
        task_cover.write(self.folder/'cover-job-1.json',{**self.job,'status':'ok'})
        with patch.object(server,'load_settings',side_effect=AssertionError('idempotent replay needs no settings')):
            result=task_cover.action(server,self.tid,'generate',{'operation_id':'fixture-op'})
        self.assertEqual(result['job']['status'],'ok')

    def test_same_completed_operation_with_missing_image_recovers_saved_result(self):
        task_cover.write(self.folder/'cover-job-1.json',{**self.job,'status':'ok'})
        with patch.object(server,'resolve_image_config',side_effect=AssertionError('reuse saved result')):
            result=task_cover.action(server,self.tid,'generate',{'operation_id':'fixture-op'})
        self.assertEqual(result['job']['status'],'ok')
        self.assertTrue((self.folder/'cover-poster-1.png').is_file())

    def test_task_id_without_cached_result_still_requires_original_credentials(self):
        task_cover.write(self.folder/'cover-job-1.json',{'provider':'runninghub','taskId':'fixture-paid','status':'pending','credential':'old'})
        with patch.object(server,'resolve_image_config',return_value={'provider':'runninghub','api_key':'new'}),patch.object(task_cover,'query_provider',side_effect=AssertionError('changed credentials cannot query')):
            with self.assertRaisesRegex(ValueError,'凭据或服务地址已经变化'):
                task_cover.action(server,self.tid,'query',{})
