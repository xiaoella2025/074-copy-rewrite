import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


class CandidateGate1250Tests(unittest.TestCase):
    def test_success_from_an_old_candidate_cannot_authorize_the_current_payload(self):
        path=Path(__file__).resolve().parents[1]/'scripts/deploy-story1250-updates.py'
        spec=importlib.util.spec_from_file_location('deploy1250_test',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            audit=Path(directory);payload=audit/'payload';payload.mkdir()
            manifest=payload/'backend-runtime.json';manifest.write_text('{"candidate":1}','utf8')
            gate=audit/'candidate-node-results.json';gate.write_text(json.dumps({'success':True,'manifestSha256':hashlib.sha256(manifest.read_bytes()).hexdigest()}),'utf8')
            with patch.object(module,'audit',audit),patch.object(module,'payload',payload):
                module.require_gate('candidate-node-results.json')
                manifest.write_text('{"candidate":2}','utf8')
                with self.assertRaisesRegex(AssertionError,'stale'):module.require_gate('candidate-node-results.json')
                gate.write_text('{"success":true}','utf8')
                with self.assertRaisesRegex(AssertionError,'stale'):module.require_gate('candidate-node-results.json')


if __name__=='__main__':unittest.main()
