"""Isolated desktop-entry acceptance using only a localhost image supplier."""
import base64
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import queue
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
from PIL import Image

repo = Path(__file__).resolve().parent.parent
host = Path.home() / 'AppData/Local/074 创作工作台/app074-backend'
audit = repo / '.desktop-tools/image-auto-retry-20261019'


def main():
    candidate = '--candidate' in sys.argv
    with tempfile.TemporaryDirectory(prefix='074-auto-retry-fixture-') as directory:
        root = Path(directory); data = root / 'data'; folder = data / 'tasks/fixture'
        (folder / 'covers').mkdir(parents=True)
        out = io.BytesIO(); Image.new('RGB', (80, 120), '#587268').save(out, 'PNG'); png = out.getvalue(); calls = []
        class Provider(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                assert self.path == '/v1/images/generations'
                calls.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                self.send_response(429 if len(calls) == 1 else 200)
                self.send_header('Content-Type', 'application/json'); self.end_headers()
                value = {'error': 'worker busy, try again'} if len(calls) == 1 else {'data': [{'b64_json': base64.b64encode(png).decode()}]}
                self.wfile.write(json.dumps(value).encode())
        mock = ThreadingHTTPServer(('127.0.0.1', 0), Provider)
        threading.Thread(target=mock.serve_forever, daemon=True).start()
        def write(path, value):
            path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(value), 'utf8')
        write(data / 'settings.json', {'image': {'provider': 'custom_image'}, 'custom_image': {
            'base_url': f'http://127.0.0.1:{mock.server_port}', 'api_key': 'fixture-local-only', 'model': 'fixture'}})
        write(folder / '02-meta.json', {'title': '自动重试隔离验证'})
        (folder / '02-rewrite.txt').write_text('独立测试场景，不是正式任务。', 'utf8')
        prompts = [{'idx': i, 'desc_prompt': f'fixture visual {i}'} for i in range(1, 12)]
        write(folder / '04-prompts.json', prompts)
        write(folder / '03-shots.json', [{'idx': i, 'text': 'fixture'} for i in range(1, 12)])
        for i in range(1, 12):
            if i != 6:
                (folder / 'covers' / f'{i}.png').write_bytes(png)
        def hashes():
            return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (folder / 'covers').glob('*') if p.stem != '6'}
        before = hashes(); token = secrets.token_hex(24)
        args = [str(host / 'python.exe'), '-B']
        if candidate:
            # Use the same desktop main, with candidate modules and a disposable static tree.
            static = root / 'static'; static.mkdir()
            for p in (host / '_internal').glob('*.html'):
                shutil.copyfile(p, static / p.name)
            shutil.copytree(host / '_internal/assets', static / 'assets')
            for p in (audit / 'payload/_internal').rglob('*'):
                if p.is_file() and p.suffix in ('.js', '.html'):
                    target = static / p.relative_to(audit / 'payload/_internal'); target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(p, target)
            code = ('import sys;from pathlib import Path;sys.path[:0]=' + repr([str(audit / 'payload/_internal'), str(host / '_internal')]) +
                    ';import server;server.ROOT=Path(' + repr(str(static)) + ');server.PROMPTS_DIR=Path(' + repr(str(host / '_internal/prompts')) + ');import desktop_backend;desktop_backend.main()')
            args += ['-c', code]
        else:
            args += [str(host / '_internal/desktop_backend.pyc')]
        args += ['--data-dir', str(data), '--legacy-data-dir', str(root / 'absent')]
        process = subprocess.Popen(args, env={**os.environ, 'APP074_SESSION_TOKEN': token}, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            lines = queue.Queue(); threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True).start()
            ready = json.loads(lines.get(timeout=30)); assert ready['event'] == 'ready'
            def request(method, path, value=None, auth=True, origin=None):
                c = http.client.HTTPConnection('127.0.0.1', ready['port'], timeout=20)
                headers = {'Content-Type': 'application/json'}
                if auth: headers['Cookie'] = 'app074_session=' + token
                if origin: headers['Origin'] = origin
                c.request(method, path, json.dumps(value) if value is not None else None, headers)
                response = c.getresponse(); result = response.status, response.read(); c.close(); return result
            path = '/api/step4_generate_images'; body = {'task_id': 'fixture', 'prompts': prompts}
            assert request('POST', path, body, auth=False)[0] == 403
            assert request('POST', path, body, origin='https://foreign.invalid')[0] == 403
            status, raw = request('POST', path, body); result = json.loads(raw)
            assert status == 200 and all(x['ok'] for x in result['results']), result
            assert result['results'][5]['auto_retries'] == 1
            assert len(calls) == 2 and all(x['prompt'] == 'fixture visual 6' for x in calls)
            assert before == hashes()
            assert all(x['ok'] for x in json.loads(request('POST', path, body)[1])['results'])
            assert len(calls) == 2
            detail = json.loads(request('GET', '/api/task/fixture')[1])
            assert len(detail['steps']['images']) == 11
            assert detail['steps']['image_retries'] == [{'index': 6, 'attempts': 1, 'status': 'ok'}]
            assert '单图失败自动重试' in request('GET', '/index.html')[1].decode('utf8')
            value = {'candidate': candidate, 'desktopEntry': True, 'sessionAndOrigin': True, 'firstFailureAutomaticallyRecovered': True,
                     'successfulImagesUnchanged': 10, 'repeatRequestUsesCache': True, 'localFakeRequests': 2, 'realProviderRequests': 0, 'productionDataAccess': False}
            write(audit / ('candidate-entry-verified.json' if candidate else 'installed-entry-verified.json'), value)
            print(json.dumps(value))
        finally:
            process.terminate(); process.wait(timeout=10); process.stdout.close(); process.stderr.close(); mock.shutdown(); mock.server_close()


if __name__ == '__main__':
    main()
