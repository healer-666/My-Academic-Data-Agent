from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from data_analysis_agent.config import RuntimeConfig
from data_analysis_agent.llm import build_llm


class FakeHelloAgentsLLM:
    def __init__(self, **kwargs):
        self.init_kwargs = kwargs
        self.invoke_kwargs = None

    def invoke(self, messages, **kwargs):
        self.invoke_kwargs = kwargs
        return "ok"


class LLMTests(unittest.TestCase):
    def test_build_llm_disables_deepseek_flash_thinking(self):
        with patch("data_analysis_agent.llm.HelloAgentsLLM", FakeHelloAgentsLLM):
            llm = build_llm(
                RuntimeConfig(
                    model_id="deepseek-v4-flash",
                    api_key="demo-key",
                    base_url="https://api.deepseek.com/v1",
                )
            )
            response = llm.invoke([{"role": "user", "content": "ping"}])

        self.assertEqual(response, "ok")
        self.assertEqual(
            llm._llm.invoke_kwargs,
            {"extra_body": {"thinking": {"type": "disabled"}}},
        )

    def test_build_llm_keeps_non_deepseek_calls_plain(self):
        with patch("data_analysis_agent.llm.HelloAgentsLLM", FakeHelloAgentsLLM):
            llm = build_llm(
                RuntimeConfig(
                    model_id="demo-model",
                    api_key="demo-key",
                    base_url="https://example.com/v1",
                )
            )
            llm.invoke([{"role": "user", "content": "ping"}])

        self.assertEqual(llm._llm.invoke_kwargs, {})


if __name__ == "__main__":
    unittest.main()
