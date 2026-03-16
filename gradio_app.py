"""Launch script for the Academic-Data-Agent Gradio demo."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from data_analysis_agent.web.app import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
