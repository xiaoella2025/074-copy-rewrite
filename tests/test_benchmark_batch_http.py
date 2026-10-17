import http.client
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import benchmark
import benchmark_batch_jobs
import server


class BatchHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name)
        change=patch.object(server,'DATA_DIR',root);change.start();self.addCleanup(change.stop)
        change=patch.dict(os.environ,{'APP074_SESSION_TOKEN':'batch-fixture'});change.start();self.addCleanup(change.stop)
        self.item={'accountId':'v2_fixture','feedId':'same'}
        benchmark._write(server,{'version':1,'accounts':[],'feeds':[self.item]})
        self.http=ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start();self.addCleanup(self.close)
    def close(self):
        manager=benchmark_batch_jobs._managers.get(str(server.DATA_DIR.resolve()))
        if manager and manager.thread:manager.thread.join(5)
        self.http.shutdown();self.http.server_close();self.thread.join(5)
    def request(self,method,path,data=None,authorized=True,origin=None,raw=None):
        c=http.client.HTTPConnection('127.0.0.1',self.http.server_port,timeout=5)
        headers={'Content-Type':'application/json'}
        if authorized:headers['Cookie']='app074_session=batch-fixture'
        if origin:headers['Origin']=origin
        c.request(method,path,raw if raw is not None else json.dumps(data) if data is not None else None,headers)
        r=c.getresponse();body=r.read();status=r.status;c.close()
        try:return status,json.loads(body)
        except ValueError:return status,{}
    def test_auth_origin_submit_read_control_and_other_routes(self):
        self.assertEqual(self.request('GET','/api/benchmark/batch-jobs',authorized=False)[0],403)
        payload={'id':'a'*32,'kind':'mark','mark':True,'items':[self.item]}
        self.assertEqual(self.request('POST','/api/benchmark/batch-start',payload,origin='https://foreign.invalid')[0],403)
        self.assertEqual(self.request('POST','/api/benchmark/batch-start',payload)[0],200)
        status,value=self.request('GET','/api/benchmark/batch-jobs');self.assertEqual(status,200);self.assertEqual(len(value['jobs']),1)
        for action in ('stop','resume'):
            self.assertEqual(self.request('POST','/api/benchmark/batch-control',{'id':'a'*32,'action':action})[0],200)
        self.assertEqual(self.request('GET','/api/benchmark')[0],200)
        self.assertEqual(self.request('GET','/api/benchmark/auto-backup')[0],200)
    def test_invalid_payload_oversize_and_conflicting_ids(self):
        base={'id':'b'*32,'kind':'mark','mark':True,'items':[self.item]}
        for data in [{**base,'id':'../bad'},{**base,'items':[{'accountId':'v2_fixture','feedId':'missing'}]},[]]:
            self.assertEqual(self.request('POST','/api/benchmark/batch-start',data)[0],400)
        self.assertEqual(self.request('POST','/api/benchmark/batch-start',raw='{bad')[0],400)
        self.assertEqual(self.request('POST','/api/benchmark/batch-start',raw='x'*131073)[0],413)
        self.assertEqual(self.request('POST','/api/benchmark/batch-start',base)[0],200)
        self.assertEqual(self.request('POST','/api/benchmark/batch-start',{**base,'mark':False})[0],409)
    def test_corrupt_saved_record_returns_error_and_is_preserved(self):
        folder=server.DATA_DIR/'benchmark/batch-jobs';folder.mkdir(parents=True)
        path=folder/('c'*32+'.json');path.write_bytes(b'broken')
        self.assertEqual(self.request('GET','/api/benchmark/batch-jobs')[0],400)
        self.assertEqual(path.read_bytes(),b'broken')
