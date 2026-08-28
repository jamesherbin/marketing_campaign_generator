import os
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from campaign.config import RunnerMode, Settings, get_settings


class SettingsTests(unittest.TestCase):
    def tearDown(self) -> None:
        get_settings.cache_clear()

    def test_safe_defaults(self) -> None:
        settings = Settings(_env_file=None)
        self.assertEqual(settings.runner_mode, RunnerMode.DETERMINISTIC)
        self.assertEqual(settings.port, 8080)
        self.assertEqual(settings.adk_auth_mode, "ambient")

    def test_loads_and_types_environment_values(self) -> None:
        environment = {
            "CAMPAIGN_RUNNER_MODE": "adk",
            "PORT": "9090",
            "LOG_LEVEL": "debug",
            "GOOGLE_GENAI_USE_VERTEXAI": "true",
            "GOOGLE_CLOUD_PROJECT": "demo-project",
        }
        with patch.dict(os.environ, environment, clear=True):
            settings = Settings(_env_file=None)
        self.assertEqual(settings.runner_mode, RunnerMode.ADK)
        self.assertEqual(settings.port, 9090)
        self.assertTrue(settings.google_genai_use_vertexai)
        self.assertEqual(settings.adk_auth_mode, "vertex_ai")

    def test_api_keys_remain_secret_values(self) -> None:
        settings = Settings(gemini_api_key="secret", _env_file=None)
        self.assertEqual(settings.adk_auth_mode, "api_key")
        self.assertNotIn("secret", repr(settings))
        self.assertEqual(settings.gemini_api_key.get_secret_value(), "secret")

    def test_rejects_invalid_port_and_runner_mode(self) -> None:
        with self.assertRaises(ValidationError):
            Settings(port=70_000, _env_file=None)
        with self.assertRaises(ValidationError):
            Settings(campaign_runner_mode="invalid", _env_file=None)


if __name__ == "__main__":
    unittest.main()
