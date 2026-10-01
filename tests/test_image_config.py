import unittest
import json
from unittest.mock import patch

import server


class ImageConfigTests(unittest.TestCase):
    def test_provider_config_comes_from_selected_block(self):
        settings = {
            "image": {"provider": "runninghub", "api_key": "gpt-key"},
            "runninghub": {"api_key": "rh-key", "workflow_id": "flow"},
            "custom_image": {"api_key": "custom-key", "base_url": "https://example.test", "model": "m"},
        }
        self.assertEqual(server.resolve_image_config(settings)["api_key"], "rh-key")
        self.assertEqual(server.resolve_image_config(settings, "custom")["api_key"], "custom-key")
        self.assertEqual(server.resolve_image_config(settings, "custom")["provider"], "custom_image")

    def test_image_ui_save_fields_reach_stored_blocks(self):
        base = {"provider": "openai", "protocol": "openai", "base_url": "https://example.test",
                "model": "m", "api_key": "llm-key"}
        with patch.object(server, "load_settings", return_value=base):
            result = server._merged({"image_provider": "runninghub", "rh_key": "rh-key",
                                     "gpt_image_ratio": "16:9", "gpt_image_concurrency": 4})
        self.assertEqual(result["runninghub"]["api_key"], "rh-key")
        self.assertEqual(result["image"]["ratio"], "16:9")
        self.assertEqual(result["image"]["concurrency"], 4)

    def test_modelscope_tokens_can_change_without_disclosing_existing_values(self):
        base = {"provider": "openai", "protocol": "openai", "base_url": "https://example.test",
                "model": "m", "api_key": "llm-key",
                "modelscope": {"tokens": ["old-secret", "keep-secret"]}}
        with patch.object(server, "load_settings", return_value=base):
            result = server._merged({"modelscope_tokens_remove": [0],
                                     "modelscope_tokens_add": ["new-secret"]})
        self.assertEqual(result["modelscope"]["tokens"], ["keep-secret", "new-secret"])

    def test_runninghub_workflow_receives_prompt_override(self):
        calls = []

        def fake_post(url, headers, body, timeout=180):
            calls.append((url, json.loads(body)))
            if url.endswith("/create"):
                return 200, '{"code":0,"data":{"taskId":"task-1"}}'
            return 200, '{"code":0,"data":[{"fileUrl":"https://example.test/image.png"}]}'

        with patch.object(server, "_http_post_json", side_effect=fake_post):
            result = server._call_runninghub({"api_key": "fake", "workflow_id": "flow-1",
                                              "prompt_node_id": "6", "prompt_field_name": "text"},
                                             "一只猫", "9:16", "1k")
        self.assertEqual(result["url"], "https://example.test/image.png")
        self.assertEqual(calls[0][0], "https://www.runninghub.ai/task/openapi/create")
        self.assertEqual(calls[0][1]["nodeInfoList"][0],
                         {"nodeId": "6", "fieldName": "text", "fieldValue": "一只猫"})

    def test_modelscope_async_result_uses_output_images(self):
        with patch.object(server, "_http_post_json", return_value=(200, '{"task_id":"task-1"}')) as post, \
             patch.object(server, "_http_get_json", return_value=(200, '{"task_status":"SUCCEED","output_images":["https://example.test/p.png"]}')) as get:
            result = server._call_modelscope({"api_key":"fake", "model":"org/model"}, "一只猫")
        self.assertEqual(result["url"], "https://example.test/p.png")
        self.assertEqual(post.call_args.args[0], "https://api-inference.modelscope.cn/v1/images/generations")
        self.assertEqual(get.call_args.args[0], "https://api-inference.modelscope.cn/v1/tasks/task-1")

    def test_modelscope_switches_to_next_token_only_when_quota_is_exhausted(self):
        cfg = {"provider":"modelscope", "model":"org/model", "tokens":["token-1", "token-2"]}
        with patch.object(server, "_call_modelscope", side_effect=[RuntimeError("HTTP 429 quota exceeded"),
                                                                    {"url":"https://example.test/p.png"}]) as call:
            result = server.image_dispatcher(cfg, "画面")
        self.assertEqual(result["url"], "https://example.test/p.png")
        self.assertEqual(call.call_args_list[1].args[0]["api_key"], "token-2")


if __name__ == "__main__":
    unittest.main()
