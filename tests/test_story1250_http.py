import base64
import http.client
from http.server import ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import wave

import server


class Update1250HttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for key, value in [('DATA_DIR', self.root), ('SETTINGS_PATH', self.root/'settings.json'), ('PROFILES_PATH', self.root/'profiles.json')]:
            context = patch.object(server, key, value); context.start(); self.addCleanup(context.stop)
        context = patch.dict(os.environ, {'APP074_SESSION_TOKEN': 'fixture-session'})
        context.start(); self.addCleanup(context.stop)
        self.http = ThreadingHTTPServer(('127.0.0.1',0), server.Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True); self.thread.start()
        self.addCleanup(self.close)

    def close(self):
        self.http.shutdown(); self.http.server_close(); self.thread.join(5)

    def request(self, method, path, body=None, authorized=True, foreign=False):
        connection = http.client.HTTPConnection('127.0.0.1', self.http.server_port, timeout=8)
        headers = {'Content-Type':'application/json'}
        if authorized: headers['Cookie'] = 'app074_session=fixture-session'
        if foreign: headers['Origin'] = 'https://foreign.invalid'
        connection.request(method, path, json.dumps(body) if body is not None else None, headers)
        response=connection.getresponse(); status=response.status; raw=response.read(); connection.close()
        return status, json.loads(raw) if raw else {}

    def test_every_new_route_requires_session_and_same_origin(self):
        routes = [('GET','/api/runtime/health'), ('GET','/api/runtime/draft-path-check?path=C:/fixture'),
                  ('POST','/api/template-sound/upload'), ('POST','/api/music/delete'), ('POST','/api/materials/open-folder'), ('POST','/api/image_lab/delete')]
        for method, path in routes:
            with self.subTest(path=path):
                self.assertEqual(self.request(method,path,{},authorized=False)[0],403)
                self.assertEqual(self.request(method,path,{},foreign=True)[0],403)

    def test_sound_upload_real_local_wav_and_invalid_body(self):
        raw=io.BytesIO()
        with wave.open(raw,'wb') as audio:
            audio.setparams((1,2,8000,0,'NONE','not compressed')); audio.writeframes(b'\0\0'*8000)
        body={'name':'隔离音效.wav','data_url':'data:audio/wav;base64,'+base64.b64encode(raw.getvalue()).decode()}
        status,result=self.request('POST','/api/template-sound/upload',body)
        self.assertEqual(status,200,result)
        self.assertEqual(Path(result['path']).read_bytes(),raw.getvalue())
        self.assertAlmostEqual(result['duration'],1)
        self.assertEqual(self.request('POST','/api/template-sound/upload',[])[0],400)
        self.assertEqual(self.request('POST','/api/template-sound/upload',{'name':'x.mp4','data_url':body['data_url']})[0],400)

    def test_invalid_delete_and_material_do_not_open_explorer(self):
        with patch('story1250_assets.os.startfile') as opener:
            self.assertEqual(self.request('POST','/api/materials/open-folder',{'material_id':'../bad'})[0],400)
            self.assertEqual(self.request('POST','/api/music/delete',{'id':'../bad'})[0],400)
            opener.assert_not_called()

    def test_delete_failed_history_route_does_not_delete_successful_media(self):
        import image_lab
        # Use the same owned history layout as the image lab's saved records.
        folder=self.root/'image-lab'; folder.mkdir()
        ident='a'*32
        record=folder/(ident+'.json'); record.write_text(json.dumps({'id':ident,'ok':False,'error':'fixture'}),'utf8')
        status,result=self.request('POST','/api/image_lab/delete',{'id':ident})
        self.assertEqual(status,200,result); self.assertFalse(record.exists())
        record.write_text(json.dumps({'id':ident,'ok':True,'url':'/covers/owned.png'}),'utf8')
        self.assertEqual(self.request('POST','/api/image_lab/delete',{'id':ident})[0],400)
        self.assertTrue(record.exists())


if __name__ == '__main__': unittest.main()
