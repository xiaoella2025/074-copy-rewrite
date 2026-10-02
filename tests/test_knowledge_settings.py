import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import server


class KnowledgeSettingsTests(unittest.TestCase):
    def test_ima_ids_and_obsidian_vault_save_and_clear_without_losing_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vault = root / "vault"
            (vault / ".obsidian").mkdir(parents=True)
            with patch.object(server, "DATA_DIR", root), patch.object(server, "SETTINGS_PATH", root / "settings.json"):
                server.save_settings({"ima_client_id": "client", "ima_api_key": "secret",
                                      "ima_kb_id": "kb-1", "ima_notebook_id": "nb-1",
                                      "obsidian_vault": str(vault), "obsidian_folder": "系列一"})
                public = server.public_settings()
                self.assertTrue(public["ima"]["configured"])
                self.assertTrue(public["obsidian"]["configured"])
                self.assertEqual(public["ima"]["kb_id"], "kb-1")
                self.assertEqual(public["obsidian"]["folder"], "系列一")
                self.assertNotIn("secret", str(public))
                server.save_settings({"ima_api_key": server.KEEP, "ima_kb_id": "",
                                      "ima_notebook_id": "", "obsidian_vault": ""})
                saved = server.load_settings()
                self.assertEqual(saved["ima"]["api_key"], "secret")
                self.assertEqual(saved["ima"]["kb_id"], "")
                self.assertEqual(saved["obsidian"]["vault"], "")

    def test_invalid_obsidian_vault_or_folder_does_not_replace_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(server, "DATA_DIR", root), patch.object(server, "SETTINGS_PATH", root / "settings.json"):
                server.save_settings({"ima_client_id": "client"})
                before = (root / "settings.json").read_bytes()
                for payload in ({"obsidian_vault": str(root)},
                                {"obsidian_folder": "../outside"}):
                    with self.subTest(payload=payload), self.assertRaises(ValueError):
                        server.save_settings(payload)
                    self.assertEqual((root / "settings.json").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
