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

from data_analysis_agent.tools.tavily_search import TavilySearchTool


class TavilySearchToolTests(unittest.TestCase):
    def setUp(self):
        self.tool = TavilySearchTool()

    def test_missing_api_key_returns_partial(self):
        with patch.dict(os.environ, {}, clear=True):
            result = self.tool.execute({"query": "What does CPI mean in economics?"})

        self.assertEqual(result.status.value, "partial")
        self.assertIn("Skip online search", result.text)

    def test_missing_dependency_returns_partial(self):
        with patch.dict(os.environ, {"TAVILY_API_KEY": "demo"}, clear=True):
            with patch.dict(sys.modules, {"tavily": None}):
                result = self.tool.execute({"query": "What does CPI mean in economics?"})

        self.assertEqual(result.status.value, "partial")
        self.assertIn("tavily-python dependency is unavailable", result.text)


if __name__ == "__main__":
    unittest.main()
