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

    def test_runninghub_key_and_model_are_enough_to_mark_configured(self):
        settings = {"image": {"provider": "runninghub"},
                    "runninghub": {"api_key": "fake", "model": "rh-image-g2", "ratio": "9:16"},
                    "tts": {}, "jimeng": {}, "modelscope": {}, "custom_image": {}}
        with patch.object(server, "load_settings", return_value=settings):
            public = server.public_settings()
        self.assertTrue(public["runninghub"]["configured"])

    def test_image_job_uses_saved_resolution_and_task_ratio_override(self):
        cfg = {"ratio": "3:4", "resolution": "2k"}
        self.assertEqual(server.image_job_options({}, cfg), ("3:4", "2k"))
        self.assertEqual(server.image_job_options({"ratio": "16:9"}, cfg), ("16:9", "2k"))

    def test_image_job_uses_saved_runninghub_concurrency(self):
        cfg = {"provider": "runninghub", "concurrency": 6}
        self.assertEqual(server.image_job_concurrency({}, cfg), 6)
        self.assertEqual(server.image_job_concurrency({"concurrency": 25}, cfg), 20)

    def test_modelscope_tokens_can_change_without_disclosing_existing_values(self):
        base = {"provider": "openai", "protocol": "openai", "base_url": "https://example.test",
                "model": "m", "api_key": "llm-key",
                "modelscope": {"tokens": ["old-secret", "keep-secret"]}}
        with patch.object(server, "load_settings", return_value=base):
            result = server._merged({"modelscope_tokens_remove": [0],
                                     "modelscope_tokens_add": ["new-secret"]})
        self.assertEqual(result["modelscope"]["tokens"], ["keep-secret", "new-secret"])

    def test_runninghub_selected_model_uses_native_api_without_workflow_ids(self):
        calls = []

        def fake_post(url, headers, body, timeout=180):
            calls.append((url, headers, json.loads(body)))
            if url.endswith("/query"):
                return 200, '{"taskId":"task-1","status":"SUCCESS","results":[{"url":"https://example.test/image.png"}]}'
            return 200, '{"taskId":"task-1","status":"RUNNING"}'

        with patch.object(server, "_http_post_json", side_effect=fake_post), patch.object(server.time, "sleep"):
            result = server._call_runninghub({"api_key": "fake", "model": "rh-image-v2"},
                                             "一只猫", "16:9", "4k")
        self.assertEqual(result["url"], "https://example.test/image.png")
        self.assertEqual(calls[0][0], "https://www.runninghub.ai/openapi/v2/rhart-image-n-g31-flash/text-to-image")
        self.assertEqual(calls[0][1]["Authorization"], "Bearer fake")
        self.assertEqual(calls[0][2], {"prompt": "一只猫", "aspectRatio": "16:9", "resolution": "4k"})
        self.assertEqual(calls[1][0], "https://www.runninghub.ai/openapi/v2/query")
        self.assertEqual(calls[1][2], {"taskId": "task-1"})

    def test_runninghub_x_ignores_resolution_and_requests_png(self):
        calls = []

        def fake_post(url, headers, body, timeout=180):
            calls.append((url, json.loads(body)))
            if url.endswith("/query"):
                return 200, '{"status":"SUCCESS","results":[{"url":"https://example.test/x.png"}]}'
            return 200, '{"taskId":"task-x","status":"RUNNING"}'

        with patch.object(server, "_http_post_json", side_effect=fake_post), patch.object(server.time, "sleep"):
            result = server._call_runninghub({"api_key": "fake", "model": "rh-image-x"},
                                             "海报", "9:16", "4k")
        self.assertEqual(result["url"], "https://example.test/x.png")
        self.assertEqual(calls[0][0], "https://www.runninghub.ai/openapi/v2/rhart-image-x-official/text-to-image")
        self.assertEqual(calls[0][1], {"prompt": "海报", "aspectRatio": "9:16", "outputFormat": "png"})

    def test_runninghub_g2_uses_its_model_endpoint(self):
        calls = []

        def fake_post(url, headers, body, timeout=180):
            calls.append((url, json.loads(body)))
            if url.endswith("/query"):
                return 200, '{"status":"SUCCESS","results":[{"url":"https://example.test/g2.png"}]}'
            return 200, '{"taskId":"task-g2","status":"RUNNING"}'

        with patch.object(server, "_http_post_json", side_effect=fake_post), patch.object(server.time, "sleep"):
            result = server._call_runninghub({"api_key": "fake", "model": "rh-image-g2"},
                                             "文字海报", "3:4", "2k")
        self.assertEqual(result["url"], "https://example.test/g2.png")
        self.assertEqual(calls[0][0], "https://www.runninghub.ai/openapi/v2/rhart-image-g-2/text-to-image")
        self.assertEqual(calls[0][1], {"prompt": "文字海报", "aspectRatio": "3:4", "resolution": "2k"})

    def test_runninghub_key_probe_uses_query_without_generating(self):
        with patch.object(server, "_http_post_json", return_value=(200, '{"status":"FAILED","errorCode":"TASK_NOT_FOUND"}')) as post:
            server._probe_runninghub_key({"api_key": "fake"})
        self.assertEqual(post.call_args.args[0], "https://www.runninghub.ai/openapi/v2/query")
        self.assertEqual(json.loads(post.call_args.args[2]), {"taskId": "00000000-0000-0000-0000-000000000000"})

    def test_runninghub_key_probe_rejects_unauthorized(self):
        with patch.object(server, "_http_post_json", side_effect=RuntimeError("HTTP 401: Unauthorized")):
            with self.assertRaisesRegex(ValueError, "API Key 无效"):
                server._probe_runninghub_key({"api_key": "fake"})

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
