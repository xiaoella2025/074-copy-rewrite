"""System model changes are tested at the real HTTP construction boundary, offline."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import server
import task_cover
import creative_workflows


class GlobalTaskModelTests(unittest.TestCase):
    def setUp(self):
        self.profiles = [
            {'id':'old','name':'old','model':'model-old','baseUrl':'https://old.invalid',
             'apiKey':'fixture-old','protocol':'openai','enabled':True},
            {'id':'new','name':'new','model':'model-new','baseUrl':'https://new.invalid',
             'apiKey':'fixture-new','protocol':'anthropic','enabled':False},
        ]
        self.addCleanup(patch.stopall)
        patch.object(server,'load_profiles',side_effect=lambda:self.profiles).start()
        self.requests=[]
        def respond(request,**options):
            self.requests.append((request,json.loads(request.data)))
            content = ({'content':[{'type':'text','text':'fixture answer'}]}
                       if request.full_url.startswith('https://new.invalid') else
                       {'choices':[{'message':{'content':'fixture answer'}}]})
            return io.BytesIO(json.dumps(content).encode())
        patch.object(server.urllib.request,'urlopen',side_effect=respond).start()

    def activate_new(self):
        self.profiles[0]['enabled']=False
        self.profiles[1]['enabled']=True

    def test_next_global_request_refreshes_model_protocol_url_and_key_without_replaying(self):
        settings={**server.resolve_active_llm_settings(),'max_tokens':123,'temperature':0.1}
        server.call_llm(settings,'system','first')
        self.activate_new()
        server.call_llm(settings,'system','second')
        self.assertEqual(len(self.requests),2)
        first,second=self.requests
        self.assertEqual(first[1]['model'],'model-old')
        self.assertEqual(second[1]['model'],'model-new')
        self.assertEqual(second[0].full_url,'https://new.invalid/v1/messages')
        self.assertEqual(second[0].get_header('X-api-key'),'fixture-new')
        self.assertEqual(second[1]['max_tokens'],123)
        self.assertEqual(settings['model'],'model-old','do not mutate already-issued settings')

    def test_explicit_standalone_profile_remains_explicit(self):
        settings=server.resolve_active_llm_settings('old')
        self.activate_new()
        server.call_llm(settings,'system','explicit')
        self.assertEqual(self.requests[0][1]['model'],'model-old')

    def test_refreshed_legacy_key_is_cleaned_before_building_headers(self):
        settings=server.resolve_active_llm_settings()
        self.activate_new();self.profiles[1]['apiKey']=' \nfixture-new\u200b '
        server.call_llm(settings,'system','next')
        self.assertEqual(self.requests[0][0].get_header('X-api-key'),'fixture-new')

    def test_invalid_stale_key_does_not_block_switch_to_a_valid_current_profile(self):
        settings=server.resolve_active_llm_settings();settings['api_key']='invalid-旧值'
        self.activate_new()
        server.call_llm(settings,'system','next')
        self.assertEqual(self.requests[0][1]['model'],'model-new')

    def test_old_task_and_cover_override_cannot_pin_next_cover_text_request(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);folder=root/'tasks/fixture';folder.mkdir(parents=True)
            patch.object(server,'DATA_DIR',root).start()
            task_cover.write(folder/'client_config.json',{'generate':{'profile_id':'old'}})
            task_cover.write(folder/'cover-editor.json',{'1':{'profile_id':'old','title':'手填标题','subtitle':['手填副题']}})
            task_cover.write(folder/'02-meta.json',{'title':'历史标题'})
            (folder/'02-rewrite.txt').write_text('保留原正文','utf8')
            (folder/'image.png').write_bytes(b'existing paid image')
            before={p.name:p.read_bytes() for p in folder.iterdir()}
            self.activate_new()
            info=task_cover.view(server,'fixture')
            self.assertEqual(info['profile_id'],'new')
            self.assertEqual(info['profile_override'],'')
            self.assertEqual(info['title'],'手填标题')
            task_cover.build_selected_prompt(server,folder,info)
            self.assertEqual(self.requests[0][1]['model'],'model-new')
            self.assertEqual(before,{p.name:p.read_bytes() for p in folder.iterdir()})

    def test_saved_deleted_profile_does_not_block_task_cover(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);folder=root/'tasks/fixture';folder.mkdir(parents=True)
            patch.object(server,'DATA_DIR',root).start()
            task_cover.write(folder/'client_config.json',{'generate':{'profile_id':'deleted'}})
            task_cover.write(folder/'02-meta.json',{'title':'保留标题'})
            (folder/'02-rewrite.txt').write_text('保留正文','utf8')
            self.activate_new()
            task_cover.build_selected_prompt(server,folder,task_cover.view(server,'fixture'))
            self.assertEqual(self.requests[0][1]['model'],'model-new')

    def test_ordinary_rewrite_ignores_old_task_snapshot(self):
        self.activate_new()
        with patch.object(server,'rewrite_with_attempts',return_value='fixture rewrite') as rewrite, \
             patch.object(server,'task_knowledge',return_value=[]):
            class LocalHandler(server.Handler):
                def __init__(self):self.path='/api/rewrite';self.response=None
                def _json(self,status,value):self.response=(status,value)
            handler=LocalHandler()
            handler._handle_json_post({'profile_id':'old','line':'story','level':'standard','reference':'fixture'})
            self.assertEqual(handler.response[0],200)
        self.assertEqual(rewrite.call_args.args[0]['model'],'model-new')
        self.assertEqual(self.requests,[],'resolving the model does not submit a provider request')

    def test_creative_text_ignores_old_profile_but_keeps_lyric_text(self):
        self.activate_new()
        result=creative_workflows.llm(server,{'profile_id':'old'},'fixture system','原词一字不改')
        self.assertEqual(result,'fixture answer')
        self.assertEqual(self.requests[0][1]['model'],'model-new')
        self.assertEqual(self.requests[0][1]['messages'][0]['content'],'原词一字不改')


if __name__=='__main__':unittest.main()
