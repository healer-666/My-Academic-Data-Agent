from __future__ import annotations

import sys
import unittest
import uuid
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from data_analysis_agent.prompts import build_system_prompt
from data_analysis_agent.tools.python_interpreter import PythonInterpreterTool


class PythonInterpreterToolTests(unittest.TestCase):
    def setUp(self):
        self.tool = PythonInterpreterTool()

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

    def test_warning_is_captured_without_leaking(self):
        result = self.tool.execute({"code": "import warnings\nwarnings.warn('demo warning')"})
        self.assertEqual(result.status.value, "partial")
        self.assertIn("demo warning", result.text)
        self.assertIn("warnings", result.data)

    def test_plotting_helpers_are_available(self):
        result = self.tool.execute(
            {
                "code": (
                    "labels = ensure_ascii_sequence(['alpha', 'beta'])\n"
                    "print(callable(apply_publication_style))\n"
                    "print(callable(beautify_axes))\n"
                    "print(callable(prepare_month_index))\n"
                    "print(get_plot_font_family())\n"
                    "print(labels)"
                )
            }
        )
        self.assertEqual(result.status.value, "success")
        self.assertIn("True", result.text)
        self.assertIn("alpha", result.text)

    def test_prepare_month_index_converts_month_labels(self):
        result = self.tool.execute(
            {
                "code": (
                    "month_index = prepare_month_index(['2025-06', '2025-07'])\n"
                    "print(str(month_index[0])[:10])"
                )
            }
        )
        self.assertEqual(result.status.value, "success")
        self.assertIn("2025-06-01", result.text)

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

    def test_heatmap_can_be_saved_without_layout_crash(self):
        case_dir = self._workspace_case_dir()
        output_path = case_dir / "heatmap.png"
        result = self.tool.execute(
            {
                "code": (
                    "import pandas as pd\n"
                    "df = pd.DataFrame([[1.0, 0.2], [0.2, 1.0]], columns=['A', 'B'], index=['A', 'B'])\n"
                    "fig, ax = plt.subplots(figsize=(6, 5))\n"
                    "sns.heatmap(df, annot=True, cmap='coolwarm', cbar=True, ax=ax)\n"
                    "beautify_axes(ax, title='Heatmap', xlabel='Features', ylabel='Features')\n"
                    f"save_figure(r'{output_path.as_posix()}')\n"
                    "print('saved heatmap')"
                )
            }
        )
        self.assertEqual(result.status.value, "success")
        self.assertTrue(output_path.exists())
        self.assertIn("saved heatmap", result.text)

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
        self.assertIn("Do not redefine save_fig()", prompt)
        self.assertIn("Official plotting template", prompt)

    def test_tool_description_mentions_small_sample_caution(self):
        self.assertIn("N < 30", self.tool.description)
        self.assertIn("non-parametric tests", self.tool.description)


if __name__ == "__main__":
    unittest.main()
