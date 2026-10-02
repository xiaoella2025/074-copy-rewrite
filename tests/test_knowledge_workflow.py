import json
import http.client
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from unittest.mock import patch

import knowledge
import server


class KnowledgeWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.vault = self.root / "vault"
        (self.vault / ".obsidian").mkdir(parents=True)
        self.folder = self.vault / "图文创作"
        self.folder.mkdir()
        self.task = self.root / "task_1"
        self.task.mkdir()
        (self.task / "02-rewrite.txt").write_text("这是合成改写文案。", encoding="utf-8")
        (self.task / "02-meta.json").write_text(json.dumps({"title": "合成标题"}), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_obsidian_search_and_repeat_export(self):
        config = {"vault": str(self.vault), "folder": "图文创作"}
        (self.folder / "人物.md").write_text("这位人物创办了一所学校。", encoding="utf-8")
        results = knowledge.search_obsidian(config, "人物")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["source"], "Obsidian")
        first = knowledge.save_obsidian(self.task, config)
        second = knowledge.save_obsidian(self.task, config)
        self.assertEqual(first["path"], second["path"])
        self.assertEqual(len(list(self.folder.glob("合成标题-*.md"))), 1)
        self.assertIn("合成改写文案", Path(first["path"]).read_text(encoding="utf-8"))

    def test_ima_export_is_idempotent_and_uncertain_write_is_not_retried(self):
        config = {"client_id": "fake-client", "api_key": "fake-key", "kb_id": "kb", "notebook_id": "nb"}
        def reply(path, payload, _config):
            return {"note_id": "note-1"} if path.endswith("import_doc") else {}
        with patch.object(knowledge, "_ima_call", side_effect=reply) as caller:
            self.assertEqual(knowledge.save_ima(self.task, config)["status"], "saved")
            self.assertEqual(knowledge.save_ima(self.task, config)["status"], "already_saved")
        self.assertEqual(caller.call_count, 2)
        self.assertNotIn("fake-key", (self.task / "ima-export.json").read_text("utf-8"))

        (self.task / "02-rewrite.txt").write_text("另一个版本。", encoding="utf-8")
        with patch.object(knowledge, "_ima_call", side_effect=ValueError("synthetic failure")) as caller:
            with self.assertRaisesRegex(ValueError, "未完整确认"):
                knowledge.save_ima(self.task, config)
            with self.assertRaisesRegex(ValueError, "未重复发送"):
                knowledge.save_ima(self.task, config)
        self.assertEqual(caller.call_count, 1)

    def test_ima_search_extracts_bounded_snippets(self):
        config = {"client_id": "fake-client", "api_key": "fake-key", "kb_id": "kb"}
        with patch.object(knowledge, "_ima_call", return_value={"info_list": [
            {"title": "素材", "highlight_content": "<em>人物</em>事迹"},
        ]}) as caller:
            results = knowledge.search_ima(config, "人物")
        self.assertEqual(results, [{"title": "素材", "excerpt": "人物事迹", "source": "IMA"}])
        self.assertEqual(caller.call_args.args[0], "openapi/wiki/v1/search_knowledge")
        self.assertEqual(caller.call_args.args[1]["knowledge_base_id"], "kb")

    def test_prompt_uses_retrieved_material_only_when_selected(self):
        with patch.object(server, "load_settings", return_value={
            "obsidian": {"vault": str(self.vault), "folder": "图文创作"}
        }):
            (self.folder / "人物.md").write_text("人物生平材料。", encoding="utf-8")
            selected = server.task_knowledge({"sources": ["obsidian"], "keywords": "人物"})
            unselected = server.task_knowledge({"sources": ["search"], "keywords": "人物"})
        self.assertEqual(len(selected), 1)
        self.assertEqual(unselected, [])
        block = server.build_context_block({"sources": ["obsidian"], "knowledge_results": selected})
        self.assertIn("人物生平材料", block)

    def test_http_task_export_to_obsidian_uses_saved_configuration(self):
        with patch.object(server, "DATA_DIR", self.root), patch.object(server, "SETTINGS_PATH", self.root / "settings.json"):
            task_root = self.root / "tasks"
            task_root.mkdir()
            target_task = task_root / "task_1"
            target_task.mkdir()
            for name in ("02-rewrite.txt", "02-meta.json"):
                (target_task / name).write_bytes((self.task / name).read_bytes())
            server.save_settings({"obsidian_vault": str(self.vault), "obsidian_folder": "图文创作"})
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
            worker = threading.Thread(target=httpd.serve_forever, daemon=True)
            worker.start()
            try:
                conn = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=5)
                body = json.dumps({"task_id": "task_1", "provider": "obsidian"}).encode("utf-8")
                conn.request("POST", "/api/knowledge/export", body, {"Content-Type": "application/json"})
                response = conn.getresponse()
                result = json.loads(response.read())
                conn.close()
                self.assertEqual(response.status, 200)
                self.assertTrue(result["ok"])
                self.assertEqual(Path(result["path"]).parent, self.folder)
            finally:
                httpd.shutdown()
                httpd.server_close()
                worker.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
