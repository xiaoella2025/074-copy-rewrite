import json,tempfile,unittest
from pathlib import Path
import task_cover

class CoverFirstErrorTests(unittest.TestCase):
 def test_first_error_records_safe_http_cause_and_survives_later_errors(self):
  with tempfile.TemporaryDirectory() as d:
   path=Path(d)/'job.json';job={'status':'unknown'}
   with self.assertRaises(RuntimeError):task_cover.record_error(path,job,RuntimeError('HTTP 502: private-response-key'))
   saved=json.loads(path.read_text('utf8'))
   self.assertEqual(saved.get('firstDiagnostic',{}).get('httpStatus'),502)
   self.assertIn('502',saved['error']);self.assertNotIn('private-response-key',json.dumps(saved))
   first=saved['firstDiagnostic']
   with self.assertRaises(TimeoutError):task_cover.record_error(path,saved,TimeoutError('private-network-address'))
   self.assertEqual(json.loads(path.read_text('utf8'))['firstDiagnostic'],first)
 def test_network_timeout_and_auth_messages_remain_distinct(self):
  self.assertEqual(task_cover.cover_error(RuntimeError('HTTP 401: secret'))['kind'],'authentication')
  self.assertEqual(task_cover.cover_error(RuntimeError('连接失败: private-host'))['kind'],'network')
  self.assertEqual(task_cover.cover_error(TimeoutError('secret'))['kind'],'timeout')

if __name__=='__main__':unittest.main()
