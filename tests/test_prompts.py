from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from data_analysis_agent.prompts import build_observation_prompt, build_reviewer_prompt, build_system_prompt


class PromptGuardrailTests(unittest.TestCase):
    def test_system_prompt_contains_academic_guardrails(self):
        prompt = build_system_prompt(
            run_dir="outputs/run_demo",
            cleaned_data_path="outputs/run_demo/data/cleaned_data.csv",
            figures_dir="outputs/run_demo/figures",
            logs_dir="outputs/run_demo/logs",
            max_steps=6,
            tool_descriptions="- PythonInterpreterTool: Execute Python code.",
        )

        self.assertIn("effect size", prompt)
        self.assertIn("95% CI", prompt)
        self.assertIn("Bonferroni", prompt)
        self.assertIn("Tukey HSD", prompt)
        self.assertIn("Never report an isolated p-value", prompt)
        self.assertIn("strictly separate correlation from causation", prompt)
        self.assertIn("统计学治理说明", prompt)
        self.assertIn("<Retrieved_Evidence_Register>", prompt)
        self.assertIn("<Success_Memory_Context>", prompt)
        self.assertIn("<Failure_Memory_Context>", prompt)

    def test_system_prompt_can_include_background_literature_context(self):
        prompt = build_system_prompt(
            run_dir="outputs/run_demo",
            cleaned_data_path="outputs/run_demo/data/cleaned_data.csv",
            figures_dir="outputs/run_demo/figures",
            logs_dir="outputs/run_demo/logs",
            max_steps=6,
            tool_descriptions="- PythonInterpreterTool: Execute Python code.",
            background_literature_context="BMI 代表身体质量指数。",
        )

        self.assertIn("<Background_Literature_Context>", prompt)
        self.assertIn("BMI 代表身体质量指数", prompt)

    def test_observation_prompt_blocks_p_value_only_finishes(self):
        prompt = build_observation_prompt(
            tool_name="PythonInterpreterTool",
            observation="t = 2.10, p = 0.03",
            remaining_steps=2,
        )

        self.assertIn("effect sizes", prompt)
        self.assertIn("95% CIs", prompt)
        self.assertIn("do not finish yet", prompt)

    def test_reviewer_prompt_contains_review_contract(self):
        publication_prompt = build_reviewer_prompt("publication")
        standard_prompt = build_reviewer_prompt("standard")

        self.assertIn("Nature, Science, or Cell", publication_prompt)
        self.assertIn("One-pass review principle", publication_prompt)
        self.assertIn("numbered list", publication_prompt)
        self.assertIn("high-quality technical or academic report", standard_prompt)
        self.assertIn("Accept", publication_prompt)
        self.assertIn("Reject", publication_prompt)
        self.assertIn("effect size", publication_prompt)
        self.assertIn("95% CI", publication_prompt)
        self.assertIn("correlation with causation", publication_prompt)
        self.assertIn("evidence register", publication_prompt)
        self.assertIn("success memory", publication_prompt)
        self.assertIn("failure memory", publication_prompt)
        self.assertIn("evidence_findings", publication_prompt)


if __name__ == "__main__":
    unittest.main()
