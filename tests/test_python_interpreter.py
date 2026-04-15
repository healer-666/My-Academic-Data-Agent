from __future__ import annotations

import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from data_analysis_agent.prompts import build_system_prompt
from data_analysis_agent.tools.python_interpreter import PythonInterpreterTool


class _FakeAxis:
    def plot(self, *args, **kwargs):
        return None

    def get_legend(self):
        return None

    def get_xticklabels(self):
        return []

    def tick_params(self, *args, **kwargs):
        return None

    def margins(self, *args, **kwargs):
        return None


class _FakeFigure:
    def __init__(self):
        self.saved_path: Path | None = None

    def savefig(self, output_path, **kwargs):
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("fake-image", encoding="utf-8")
        self.saved_path = target


class _FakePlt:
    def __init__(self):
        self._current = _FakeFigure()

    def subplots(self, *args, **kwargs):
        self._current = _FakeFigure()
        return self._current, _FakeAxis()

    def gcf(self):
        return self._current


class _FakeSns:
    def set_theme(self, *args, **kwargs):
        return None


def _fake_save_figure(output_path):
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("fake-image", encoding="utf-8")
    return target


class PythonInterpreterToolTests(unittest.TestCase):
    def setUp(self):
        self.fake_plt = _FakePlt()
        self.apply_patch = patch(
            "data_analysis_agent.tools.python_interpreter.apply_publication_style",
            return_value=(self.fake_plt, _FakeSns()),
        )
        self.save_patch = patch("data_analysis_agent.tools.python_interpreter.save_figure", side_effect=_fake_save_figure)
        self.apply_patch.start()
        self.save_patch.start()
        self.tool = PythonInterpreterTool()

    def tearDown(self):
        self.save_patch.stop()
        self.apply_patch.stop()

    def _workspace_case_dir(self) -> Path:
        base_dir = PROJECT_ROOT / "tool-output" / "test-temp"
        base_dir.mkdir(parents=True, exist_ok=True)
        case_dir = base_dir / f"plot_case_{uuid.uuid4().hex}"
        case_dir.mkdir(parents=True, exist_ok=True)
        return case_dir

    def test_printed_output_returns_success(self):
        result = self.tool.execute({"code": "print(1 + 1)"})
        self.assertEqual(result.status.value, "success")
        self.assertIn("2", result.text)

    def test_silent_execution_returns_partial(self):
        result = self.tool.execute({"code": "x = 10"})
        self.assertEqual(result.status.value, "partial")
        self.assertIn("Please use print()", result.text)

    def test_runtime_error_returns_traceback(self):
        result = self.tool.execute({"code": "1 / 0"})
        self.assertEqual(result.status.value, "error")
        self.assertIn("ZeroDivisionError", result.text)

    def test_plotting_helpers_are_available(self):
        result = self.tool.execute(
            {
                "code": (
                    "labels = ensure_ascii_sequence(['alpha', 'beta'])\n"
                    "print(callable(apply_publication_style))\n"
                    "print(callable(beautify_axes))\n"
                    "print(callable(save_figure))\n"
                    "print(labels)"
                )
            }
        )
        self.assertEqual(result.status.value, "success")
        self.assertIn("True", result.text)
        self.assertIn("alpha", result.text)

    def test_save_figure_supports_single_argument_api(self):
        case_dir = self._workspace_case_dir()
        output_path = case_dir / "single_arg_plot.png"
        result = self.tool.execute(
            {
                "code": (
                    "fig, ax = plt.subplots()\n"
                    "ax.plot([1, 2, 3], [2, 3, 5])\n"
                    f"saved = save_figure(r'{output_path.as_posix()}')\n"
                    "print(saved)"
                )
            }
        )
        self.assertEqual(result.status.value, "success")
        self.assertTrue(output_path.exists())
        self.assertIn("single_arg_plot.png", result.text)

    def test_prompt_contains_strict_plotting_protocol(self):
        prompt = build_system_prompt(
            run_dir="outputs/run_demo",
            cleaned_data_path="outputs/run_demo/data/cleaned_data.csv",
            figures_dir="outputs/run_demo/figures",
            logs_dir="outputs/run_demo/logs",
            max_steps=6,
            tool_descriptions="- PythonInterpreterTool: Execute Python code.",
        )
        self.assertIn("save_figure(output_path)", prompt)
        self.assertIn("Do not call plt.tight_layout() manually.", prompt)


if __name__ == "__main__":
    unittest.main()
