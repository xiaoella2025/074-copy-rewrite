"""Exercise installed desktop HTTP metadata with isolated data and a local model."""
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import queue
import secrets
import subprocess
import tempfile
import threading

repo = Path(__file__).resolve().parent.parent
host = Path.home() / 'AppData/Local/074 创作工作台/app074-backend'
audit = repo / '.desktop-tools/user-title-priority-20261019'


def main():
    calls = []
    title = '人这一辈子，有101个地方，去晚了就只剩后悔'
    metadata = {'title': 'AI擅自改写的标题', 'short_title': '独立发布短题', 'subtitle': ['副题'],
                'summary': '发布正文', 'tags': ['#旅行'], 'comments': ['评论'], 'characters': [], 'cover_image_prompts': ['山水']}
    class Model(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            assert self.path.endswith('/chat/completions')
            calls.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            self.send_response(200); self.send_header('Content-Type', 'application/json'); self.end_headers()
            self.wfile.write(json.dumps({'choices': [{'message': {'content': json.dumps(metadata, ensure_ascii=False)}}]}).encode())
    fake = ThreadingHTTPServer(('127.0.0.1', 0), Model)
    threading.Thread(target=fake.serve_forever, daemon=True).start()
    try:
        with tempfile.TemporaryDirectory(prefix='074-user-title-fixture-') as directory:
            root = Path(directory); data = root / 'data'; data.mkdir()
            (data / 'profiles.json').write_text(json.dumps([{'id': 'fixture', 'enabled': True, 'provider': 'custom', 'protocol': 'openai',
                'baseUrl': f'http://127.0.0.1:{fake.server_port}/v1', 'apiKey': 'fixture-local-only', 'model': 'fixture'}]), 'utf8')
            token = secrets.token_hex(24)
            process = subprocess.Popen([str(host / 'python.exe'), '-B', str(host / '_internal/desktop_backend.pyc'), '--data-dir', str(data),
                '--legacy-data-dir', str(root / 'absent')], env={**os.environ, 'APP074_SESSION_TOKEN': token},
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            try:
                lines = queue.Queue(); threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True).start()
                ready = json.loads(lines.get(timeout=30)); assert ready['event'] == 'ready'
                for supplied in [title, '']:
                    tid = 'fixture-user' if supplied else 'fixture-auto'
                    folder = data / 'tasks' / tid; folder.mkdir(parents=True)
                    (folder / 'client_config.json').write_text(json.dumps({'cover': {'title': supplied, 'subtitle': '指定副题' if supplied else ''}}), 'utf8')
                    body = {'task_id': tid, 'track_progress': True, 'title': '独立的任务名称', 'profile_id': 'fixture', 'track': 'general', 'run_steps': ['meta'],
                            'reference': '本地隔离测试正文。', 'rewritten': '本地隔离测试正文。'}
                    c = http.client.HTTPConnection('127.0.0.1', ready['port'], timeout=15)
                    c.request('POST', '/api/generate', json.dumps(body), {'Content-Type': 'application/json', 'Cookie': 'app074_session=' + token})
                    response = c.getresponse(); status = response.status; value = json.loads(response.read()); c.close()
                    assert status == 200, value
                    expected = supplied or metadata['title']
                    assert value['steps']['meta']['title'] == expected
                    saved = json.loads((data / 'tasks' / tid / '02-meta.json').read_text('utf8'))
                    assert saved['title'] == expected and saved['short_title'] == metadata['short_title']
                    if supplied: assert saved['subtitle'] == ['指定副题']
                assert len(calls) == 2
                result = {'installedDesktopEntry': True, 'explicitCoverTextPreserved': True, 'taskNameDoesNotOverrideCover': True,
                          'publishingShortTitleIndependent': True, 'persistedMetadataChecked': True,
                          'localFakeLLMRequests': 2, 'realProviderRequests': 0, 'productionDataAccess': False}
                (audit / 'installed-entry-verified.json').write_text(json.dumps(result, indent=2), 'utf8')
                print(json.dumps(result))
            finally:
                process.terminate(); process.wait(timeout=10); process.stdout.close(); process.stderr.close()
    finally:
        fake.shutdown(); fake.server_close()


if __name__ == '__main__': main()
