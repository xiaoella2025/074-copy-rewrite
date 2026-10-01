"""074 settings must not require or expose a product activation code."""

import unittest
from unittest.mock import patch

import server


class SettingsNoActivationTests(unittest.TestCase):
    def test_legacy_activation_code_is_ignored_by_new_settings(self):
        legacy = {
            "provider": "custom", "protocol": "openai",
            "base_url": "https://example.invalid", "model": "m1", "api_key": "fake-key",
            "license": {"key": "old-placeholder-code"},
        }
        with patch.object(server, "load_settings", return_value=legacy):
            saved = server._merged({"license_key": "another-placeholder-code"})
            public = server.public_settings()
        self.assertNotIn("license", saved)
        self.assertNotIn("license", public)
        self.assertEqual(saved["api_key"], "fake-key")


if __name__ == "__main__":
    unittest.main()
