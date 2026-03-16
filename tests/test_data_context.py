from __future__ import annotations

import json
import sys
import unittest
import uuid
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from data_analysis_agent.data_context import build_data_context


class DataContextTests(unittest.TestCase):
    def test_build_data_context_from_excel(self):
        summary = build_data_context(PROJECT_ROOT / "data" / "simple_data.xls")

        self.assertEqual(summary.data_path.as_posix(), "data/simple_data.xls")
        self.assertEqual(summary.shape, (13, 6))
        self.assertIn("数据文件相对路径", summary.context_text)
        self.assertIn("数据列名", summary.context_text)
        self.assertIn("数据类型", summary.context_text)
        self.assertIn("前 5 行样本", summary.context_text)
        self.assertIn("居民消费价格指数", summary.context_text)
        self.assertTrue(summary.small_sample_warning)
        self.assertIn("WARNING / 红色警告", summary.context_text)
        self.assertIn("Mann-Whitney U 检验", summary.sample_size_warning)

    def test_context_is_metadata_only(self):
        summary = build_data_context(PROJECT_ROOT / "data" / "simple_data.xls")

        self.assertNotIn("前 6 行样本", summary.context_text)
        self.assertNotIn("to_json", summary.context_text)
        self.assertEqual(summary.context_text.count("| 居民消费价格指数(上年同月=100)"), 1)

    def test_large_sample_does_not_add_small_sample_warning(self):
        case_dir = PROJECT_ROOT / "tool-output" / "test-temp" / f"data_context_{uuid.uuid4().hex}"
        case_dir.mkdir(parents=True, exist_ok=True)
        csv_path = case_dir / "large_sample.csv"
        pd.DataFrame({"value": list(range(30))}).to_csv(csv_path, index=False)

        summary = build_data_context(csv_path)

        self.assertFalse(summary.small_sample_warning)
        self.assertEqual(summary.sample_size_warning, "")
        self.assertNotIn("WARNING / 红色警告", summary.context_text)

    def test_pdf_context_injects_background_literature_and_candidate_table_context(self):
        case_dir = PROJECT_ROOT / "tool-output" / "test-temp" / f"pdf_context_{uuid.uuid4().hex}"
        case_dir.mkdir(parents=True, exist_ok=True)
        csv_path = case_dir / "table.csv"
        parsed_path = case_dir / "parsed_document.json"
        pd.DataFrame({"bmi": [22.1, 24.4], "risk": [0.2, 0.5]}).to_csv(csv_path, index=False)
        parsed_path.write_text(
            json.dumps(
                {
                    "background_literature_context": "BMI 代表身体质量指数，用于评估体重与身高关系。",
                    "candidate_tables": [
                        {
                            "table_id": "table_01",
                            "shape": [2, 2],
                            "headers": ["bmi", "risk"],
                            "numeric_columns": ["bmi", "risk"],
                            "content_hint": "22.1 | 0.2",
                            "selected_as_primary": True,
                        }
                    ],
                    "candidate_table_summaries": [
                        {
                            "table_id": "table_01",
                            "shape": [2, 2],
                            "headers": ["bmi", "risk"],
                            "numeric_columns": ["bmi", "risk"],
                            "content_hint": "22.1 | 0.2",
                            "selected_as_primary": True,
                        }
                    ],
                    "selected_table_id": "table_01",
                    "pdf_multi_table_mode": True,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        summary = build_data_context(csv_path, input_kind="pdf", parsed_document_path=parsed_path)

        self.assertEqual(summary.input_kind, "pdf")
        self.assertTrue(summary.pdf_multi_table_mode)
        self.assertIn("<Background_Literature_Context>", summary.context_text)
        self.assertIn("BMI 代表身体质量指数", summary.context_text)
        self.assertIn("<PDF_Candidate_Tables_Context>", summary.context_text)
        self.assertIn("selected_table_id=table_01", summary.context_text)
        self.assertEqual(summary.parsed_document_path, parsed_path)

    def test_pdf_small_table_mode_is_injected_for_model_comparison_table(self):
        case_dir = PROJECT_ROOT / "tool-output" / "test-temp" / f"pdf_small_table_{uuid.uuid4().hex}"
        case_dir.mkdir(parents=True, exist_ok=True)
        csv_path = case_dir / "table.csv"
        parsed_path = case_dir / "parsed_document.json"
        pd.DataFrame(
            {
                "model": ["A", "B", "C"],
                "precision": [0.81, 0.84, 0.86],
                "recall": [0.74, 0.78, 0.79],
            }
        ).to_csv(csv_path, index=False)
        parsed_path.write_text(
            json.dumps(
                {
                    "candidate_tables": [
                        {
                            "table_id": "table_01",
                            "shape": [3, 3],
                            "headers": ["model", "precision", "recall"],
                            "numeric_columns": ["precision", "recall"],
                            "content_hint": "A | 0.81 | 0.74",
                            "selected_as_primary": True,
                        }
                    ],
                    "candidate_table_summaries": [
                        {
                            "table_id": "table_01",
                            "shape": [3, 3],
                            "headers": ["model", "precision", "recall"],
                            "numeric_columns": ["precision", "recall"],
                            "content_hint": "A | 0.81 | 0.74",
                            "selected_as_primary": True,
                        }
                    ],
                    "selected_table_id": "table_01",
                    "background_literature_context": "This table compares different model variants.",
                    "pdf_multi_table_mode": True,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        summary = build_data_context(csv_path, input_kind="pdf", parsed_document_path=parsed_path)

        self.assertTrue(summary.pdf_small_table_mode)
        self.assertEqual(summary.candidate_table_count, 1)
        self.assertEqual(summary.selected_table_id, "table_01")
        self.assertIn("<PDF_Small_Table_Mode>", summary.context_text)
        self.assertIn("Do not run one-sample tests", summary.context_text)
        self.assertIn("candidate_table_count=1", summary.context_text)


if __name__ == "__main__":
    unittest.main()
