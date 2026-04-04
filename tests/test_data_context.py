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

from data_analysis_agent.data_context import _read_dataframe, build_data_context


class DataContextTests(unittest.TestCase):
    def _workspace_case_dir(self) -> Path:
        base_dir = PROJECT_ROOT / "tool-output" / "test-temp"
        base_dir.mkdir(parents=True, exist_ok=True)
        case_dir = base_dir / f"data_context_{uuid.uuid4().hex}"
        case_dir.mkdir(parents=True, exist_ok=True)
        return case_dir

    def test_build_data_context_from_dynamic_excel_fixture(self):
        case_dir = self._workspace_case_dir()
        xlsx_path = case_dir / "sample_context.xlsx"
        pd.DataFrame(
            {
                "metric_name": ["row1", "row2", "row3", "row4", "row5", "row6"],
                "value": [10, 11, 12, 13, 14, 15],
                "group": ["A", "A", "B", "B", "C", "C"],
            }
        ).to_excel(xlsx_path, index=False)

        summary = build_data_context(xlsx_path)

        self.assertEqual(summary.data_path.as_posix(), xlsx_path.relative_to(PROJECT_ROOT).as_posix())
        self.assertEqual(summary.shape, (6, 3))
        self.assertIn("数据文件相对路径", summary.context_text)
        self.assertIn("数据列名", summary.context_text)
        self.assertIn("数据类型", summary.context_text)
        self.assertIn("前 5 行样本", summary.context_text)
        self.assertIn("metric_name", summary.context_text)
        self.assertTrue(summary.small_sample_warning)
        self.assertIn("WARNING / 红色警告", summary.context_text)
        self.assertIn("Mann-Whitney U 检验", summary.sample_size_warning)

    def test_context_is_metadata_only_for_dynamic_excel_fixture(self):
        case_dir = self._workspace_case_dir()
        xlsx_path = case_dir / "sample_context.xlsx"
        pd.DataFrame(
            {
                "metric_name": ["row1", "row2", "row3", "row4", "row5", "row6"],
                "value": [10, 11, 12, 13, 14, 15],
            }
        ).to_excel(xlsx_path, index=False)

        summary = build_data_context(xlsx_path)

        self.assertIn("row5", summary.context_text)
        self.assertNotIn("row6", summary.context_text)
        self.assertNotIn("to_json", summary.context_text)
        self.assertIn("metric_name", summary.context_text)
        self.assertIn("value", summary.context_text)

    def test_xls_path_falls_back_to_same_name_xlsx(self):
        case_dir = self._workspace_case_dir()
        xlsx_path = case_dir / "fallback_sample.xlsx"
        xls_path = case_dir / "fallback_sample.xls"
        expected = pd.DataFrame({"feature": ["A", "B"], "value": [1.0, 2.0]})
        expected.to_excel(xlsx_path, index=False)

        loaded = _read_dataframe(xls_path)
        summary = build_data_context(xls_path)

        self.assertEqual(loaded.shape, (2, 2))
        self.assertEqual(list(loaded.columns), ["feature", "value"])
        self.assertEqual(summary.shape, (2, 2))
        self.assertEqual(summary.absolute_path, xls_path.resolve())

    def test_large_sample_does_not_add_small_sample_warning(self):
        case_dir = self._workspace_case_dir()
        csv_path = case_dir / "large_sample.csv"
        pd.DataFrame({"value": list(range(30))}).to_csv(csv_path, index=False)

        summary = build_data_context(csv_path)

        self.assertFalse(summary.small_sample_warning)
        self.assertEqual(summary.sample_size_warning, "")
        self.assertNotIn("WARNING / 红色警告", summary.context_text)

    def test_pdf_context_injects_background_literature_and_candidate_table_context(self):
        case_dir = self._workspace_case_dir()
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
        self.assertEqual(summary.selected_table_headers, ("bmi", "risk"))
        self.assertEqual(summary.selected_table_numeric_columns, ("bmi", "risk"))
        self.assertIn("<Background_Literature_Context>", summary.context_text)
        self.assertIn("BMI 代表身体质量指数", summary.context_text)
        self.assertIn("<PDF_Candidate_Tables_Context>", summary.context_text)
        self.assertIn("selected_table_id=table_01", summary.context_text)
        self.assertEqual(summary.parsed_document_path, parsed_path)

    def test_pdf_small_table_mode_is_injected_for_model_comparison_table(self):
        case_dir = self._workspace_case_dir()
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
        self.assertEqual(summary.selected_table_headers, ("model", "precision", "recall"))
        self.assertEqual(summary.selected_table_numeric_columns, ("precision", "recall"))
        self.assertIn("<PDF_Small_Table_Mode>", summary.context_text)
        self.assertIn("Do not run one-sample tests", summary.context_text)
        self.assertIn("candidate_table_count=1", summary.context_text)


if __name__ == "__main__":
    unittest.main()
