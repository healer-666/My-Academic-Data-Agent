from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

import data_analysis_agent.config as config_module
from data_analysis_agent.config import DEEPSEEK_FLASH_MODEL_ID, load_runtime_config


class ConfigTests(unittest.TestCase):
    def test_load_runtime_config_marks_vision_as_configured_when_complete(self):
        env = {
            "LLM_MODEL_ID": "demo-model",
            "LLM_API_KEY": "demo-key",
            "LLM_BASE_URL": "https://example.com/v1",
            "VISION_LLM_MODEL_ID": "vision-model",
            "VISION_LLM_API_KEY": "vision-key",
            "VISION_LLM_BASE_URL": "https://vision.example.com/v1",
        }
        with patch.dict(os.environ, env, clear=True):
            config = load_runtime_config(env_file=PROJECT_ROOT / ".env.test.missing")

        self.assertTrue(config.vision_configured)
        self.assertEqual(config.vision_model_id, "vision-model")

    def test_load_runtime_config_marks_vision_as_unconfigured_when_partial(self):
        env = {
            "LLM_MODEL_ID": "demo-model",
            "LLM_API_KEY": "demo-key",
            "LLM_BASE_URL": "https://example.com/v1",
            "VISION_LLM_MODEL_ID": "vision-model",
            "VISION_LLM_API_KEY": "vision-key",
        }
        with patch.dict(os.environ, env, clear=True):
            config = load_runtime_config(env_file=PROJECT_ROOT / ".env.test.missing")

        self.assertFalse(config.vision_configured)

    def test_load_runtime_config_marks_embedding_as_configured_when_complete(self):
        env = {
            "LLM_MODEL_ID": "demo-model",
            "LLM_API_KEY": "demo-key",
            "LLM_BASE_URL": "https://example.com/v1",
            "EMBEDDING_MODEL_ID": "text-embedding-demo",
            "EMBEDDING_API_KEY": "embed-key",
            "EMBEDDING_BASE_URL": "https://embed.example.com/v1",
        }
        with patch.dict(os.environ, env, clear=True):
            config = load_runtime_config(env_file=PROJECT_ROOT / ".env.test.missing")

        self.assertTrue(config.embedding_configured)
        self.assertEqual(config.embedding_model_id, "text-embedding-demo")

    def test_load_runtime_config_maps_deepseek_chat_to_v4_flash(self):
        env = {
            "LLM_MODEL_ID": "deepseek-chat",
            "LLM_API_KEY": "demo-key",
            "LLM_BASE_URL": "https://api.deepseek.com/v1",
        }
        with patch.dict(os.environ, env, clear=True):
            config = load_runtime_config(env_file=PROJECT_ROOT / ".env.test.missing")
            self.assertEqual(os.environ["LLM_MODEL_ID"], DEEPSEEK_FLASH_MODEL_ID)

        self.assertEqual(config.model_id, DEEPSEEK_FLASH_MODEL_ID)

    def test_load_runtime_config_maps_deepseek_pro_to_v4_flash(self):
        env = {
            "LLM_MODEL_ID": "deepseek-v4-pro",
            "LLM_API_KEY": "demo-key",
            "LLM_BASE_URL": "https://api.deepseek.com/v1",
        }
        with patch.dict(os.environ, env, clear=True):
            config = load_runtime_config(env_file=PROJECT_ROOT / ".env.test.missing")

        self.assertEqual(config.model_id, DEEPSEEK_FLASH_MODEL_ID)

    def test_load_runtime_config_keeps_mimo_model_for_anthropic_endpoint(self):
        env = {
            "LLM_MODEL_ID": "mimo-v2.5",
            "LLM_API_KEY": "demo-key",
            "LLM_BASE_URL": "https://token-plan-cn.xiaomimimo.com/anthropic",
        }
        with patch.dict(os.environ, env, clear=True):
            config = load_runtime_config(env_file=PROJECT_ROOT / ".env.test.missing")

        self.assertEqual(config.model_id, "mimo-v2.5")
        self.assertTrue(config.anthropic_messages_configured)

    def test_load_runtime_config_accepts_utf8_sig_env_files(self):
        if config_module.load_dotenv.__module__ == config_module.__name__:
            self.skipTest("python-dotenv is not installed in this interpreter")
        env_path = PROJECT_ROOT / "tool-output" / "test-temp" / "bom_env.env"
        env_path.parent.mkdir(parents=True, exist_ok=True)
        env_path.write_text(
            "LLM_MODEL_ID=mimo-v2.5\n"
            "LLM_API_KEY=demo-key\n"
            "LLM_BASE_URL=https://token-plan-cn.xiaomimimo.com/anthropic\n",
            encoding="utf-8-sig",
        )

        with patch.dict(os.environ, {}, clear=True):
            config = load_runtime_config(env_file=env_path)

        self.assertEqual(config.model_id, "mimo-v2.5")


if __name__ == "__main__":
    unittest.main()
