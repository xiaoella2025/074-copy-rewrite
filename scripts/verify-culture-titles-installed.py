"""Verify the installed metadata HTTP flow against a localhost fake LLM."""
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
audit = repo / '.desktop-tools/culture-titles-20261019'


def main():
    calls = []
    metadata = {'title': '寺庙宫观有何不同', 'short_title': '寺庙宫观各有来由', 'subtitle': ['名称各有来由', '不同体系不同称呼'],
                'summary': 'fixture publishing copy', 'tags': ['#华夏文化', '#涨知识'], 'comments': ['fixture comment'],
                'characters': [], 'cover_image_prompts': []}
    class Model(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            assert self.path.endswith('/chat/completions')
            calls.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            self.send_response(200); self.send_header('Content-Type', 'application/json'); self.end_headers()
            self.wfile.write(json.dumps({'choices': [{'message': {'role': 'assistant', 'content': json.dumps(metadata, ensure_ascii=False)}}]}).encode())
    fake = ThreadingHTTPServer(('127.0.0.1', 0), Model)
    threading.Thread(target=fake.serve_forever, daemon=True).start()
    with tempfile.TemporaryDirectory(prefix='074-culture-title-fixture-') as directory:
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
            legacy = next(t for t in json.loads((audit / 'source-before/assets/prompt_templates.json').read_text('utf8')) if t['id'] == 'culture-knowledge')
            for mode in ['new', 'legacy', 'custom']:
                body = {'task_id': 'fixture-' + mode, 'profile_id': 'fixture', 'track': 'culture-knowledge', 'run_steps': ['meta'],
                        'reference': '寺、庙、宫、观的名称对应不同信仰体系，本文说明它们的区别。',
                        'rewritten': '寺、庙、宫、观的名称对应不同信仰体系，本文说明它们的区别。'}
                if mode != 'new':
                    snapshot = json.loads(json.dumps(legacy))
                    if mode == 'custom': snapshot['step1MetadataSystemPrompt'] += '\n用户自定义：栏目固定命名。'
                    body.update(prompt_template_id='culture-knowledge', prompt_template=snapshot)
                c = http.client.HTTPConnection('127.0.0.1', ready['port'], timeout=15)
                c.request('POST', '/api/generate', json.dumps(body), {'Content-Type': 'application/json', 'Cookie': 'app074_session=' + token})
                response = c.getresponse(); status = response.status; value = json.loads(response.read()); c.close()
                assert status == 200, value
                assert value['steps']['meta']['title'] == metadata['title']
                assert len(calls) == ['new', 'legacy', 'custom'].index(mode) + 1
                system = calls[-1]['messages'][0]['content']
                if mode == 'custom': assert '用户自定义：栏目固定命名。' in system and '从下列词库轮换选用' in system
                else: assert '正文中的具体问题' in system and '从下列词库轮换选用' not in system
            result = {'installedDesktopEntry': True, 'newTaskUsesSpecificTitlePolicy': True, 'legacySnapshotUsesNewPolicy': True,
                      'customMetadataPreserved': True, 'oneRequestPerMetadataStage': True, 'localFakeLLMRequests': 3,
                      'realProviderRequests': 0, 'productionDataAccess': False, 'actualModelTitleQualityEvaluated': False}
            (audit / 'installed-entry-verified.json').write_text(json.dumps(result, indent=2), 'utf8')
            print(json.dumps(result))
        finally:
            process.terminate(); process.wait(timeout=10); process.stdout.close(); process.stderr.close(); fake.shutdown(); fake.server_close()


if __name__ == '__main__':
    main()
