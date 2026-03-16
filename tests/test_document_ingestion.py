from __future__ import annotations

import json
import sys
import types
import unittest
import uuid
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from data_analysis_agent.document_ingestion import ingest_input_document, preview_pdf_tables


class _FakePage:
    def __init__(self, text: str, tables: list[list[list[str]]]):
        self._text = text
        self._tables = tables

    def extract_text(self):
        return self._text

    def extract_tables(self):
        return self._tables


class _FakePdf:
    def __init__(self, pages):
        self.pages = pages

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class DocumentIngestionTests(unittest.TestCase):
    def _workspace_case_dir(self) -> Path:
        base_dir = PROJECT_ROOT / "tool-output" / "test-temp"
        base_dir.mkdir(parents=True, exist_ok=True)
        case_dir = base_dir / f"ingestion_case_{uuid.uuid4().hex}"
        case_dir.mkdir(parents=True, exist_ok=True)
        return case_dir

    def test_tabular_input_skips_document_ingestion(self):
        case_dir = self._workspace_case_dir()
        source_path = case_dir / "sample.csv"
        source_path.write_text("a,b\n1,2\n", encoding="utf-8")

        result = ingest_input_document(
            source_path,
            run_dir=case_dir / "run",
            data_dir=case_dir / "run" / "data",
            logs_dir=case_dir / "run" / "logs",
        )

        self.assertEqual(result.input_kind, "tabular")
        self.assertEqual(result.status, "not_needed")
        self.assertEqual(result.normalized_data_path, source_path.resolve())
        self.assertFalse(result.pdf_multi_table_mode)
        self.assertTrue(result.log_path.exists())

    def test_pdf_ingestion_selects_largest_numeric_table(self):
        case_dir = self._workspace_case_dir()
        pdf_path = case_dir / "paper.pdf"
        pdf_path.write_text("fake-pdf", encoding="utf-8")
        pages = [
            _FakePage(
                "Abstract: BMI means body mass index. Methods and results follow.",
                [
                    [["group", "mean"], ["A", "1.2"], ["B", "2.4"]],
                    [["feature", "v1", "v2"], ["x", "1", "2"], ["y", "3", "4"], ["z", "5", "6"]],
                ],
            )
        ]
        fake_pdfplumber = types.SimpleNamespace(open=lambda _path: _FakePdf(pages))

        with unittest.mock.patch.dict(sys.modules, {"pdfplumber": fake_pdfplumber}):
            result = ingest_input_document(
                pdf_path,
                run_dir=case_dir / "run",
                data_dir=case_dir / "run" / "data",
                logs_dir=case_dir / "run" / "logs",
                mode="text_only",
                max_pdf_pages=10,
                max_candidate_tables=5,
            )

        self.assertEqual(result.input_kind, "pdf")
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.selected_table_id, "table_02")
        self.assertEqual(result.candidate_table_count, 2)
        self.assertEqual(result.selected_table_shape, (3, 3))
        self.assertEqual(result.selected_table_numeric_columns, ("v1", "v2"))
        self.assertTrue(result.pdf_multi_table_mode)
        self.assertEqual(len(result.candidate_table_summaries), 2)
        self.assertTrue((case_dir / "run" / "data" / "cleaned_data.csv").exists())
        self.assertTrue(result.parsed_document_path.exists())
        parsed_payload = json.loads(result.parsed_document_path.read_text(encoding="utf-8"))
        self.assertEqual(parsed_payload["selected_table_id"], "table_02")
        self.assertEqual(len(parsed_payload["candidate_tables"]), 2)
        self.assertTrue(parsed_payload["pdf_multi_table_mode"])
        self.assertIn("candidate_table_summaries", parsed_payload)
        self.assertIn("BMI means body mass index", parsed_payload["background_literature_context"])
        loaded_primary = pd.read_csv(result.normalized_data_path)
        self.assertEqual(loaded_primary.shape, (3, 3))

    def test_pdf_preview_returns_default_table_and_candidates(self):
        case_dir = self._workspace_case_dir()
        pdf_path = case_dir / "paper.pdf"
        pdf_path.write_text("fake-pdf", encoding="utf-8")
        pages = [
            _FakePage(
                "Abstract: BMI means body mass index. Methods and results follow.",
                [
                    [["group", "mean"], ["A", "1.2"], ["B", "2.4"]],
                    [["feature", "v1", "v2"], ["x", "1", "2"], ["y", "3", "4"], ["z", "5", "6"]],
                ],
            )
        ]
        fake_pdfplumber = types.SimpleNamespace(open=lambda _path: _FakePdf(pages))

        with unittest.mock.patch.dict(sys.modules, {"pdfplumber": fake_pdfplumber}):
            preview = preview_pdf_tables(pdf_path, max_pdf_pages=10, max_candidate_tables=5)

        self.assertEqual(preview.default_table_id, "table_02")
        self.assertEqual(len(preview.candidate_tables), 2)
        self.assertIn("BMI means body mass index", preview.background_literature_context)
        self.assertIn("综合报告", preview.warnings[0])

    def test_pdf_ingestion_respects_selected_table_override(self):
        case_dir = self._workspace_case_dir()
        pdf_path = case_dir / "paper.pdf"
        pdf_path.write_text("fake-pdf", encoding="utf-8")
        pages = [
            _FakePage(
                "Abstract: metrics table.",
                [
                    [["group", "mean"], ["A", "1.2"], ["B", "2.4"]],
                    [["feature", "v1", "v2"], ["x", "1", "2"], ["y", "3", "4"], ["z", "5", "6"]],
                ],
            )
        ]
        fake_pdfplumber = types.SimpleNamespace(open=lambda _path: _FakePdf(pages))

        with unittest.mock.patch.dict(sys.modules, {"pdfplumber": fake_pdfplumber}):
            result = ingest_input_document(
                pdf_path,
                run_dir=case_dir / "run",
                data_dir=case_dir / "run" / "data",
                logs_dir=case_dir / "run" / "logs",
                selected_table_id="table_01",
            )

        self.assertEqual(result.selected_table_id, "table_01")
        loaded_primary = pd.read_csv(result.normalized_data_path)
        self.assertEqual(loaded_primary.shape, (2, 2))

    def test_pdf_ingestion_rejects_invalid_selected_table_id(self):
        case_dir = self._workspace_case_dir()
        pdf_path = case_dir / "paper.pdf"
        pdf_path.write_text("fake-pdf", encoding="utf-8")
        pages = [
            _FakePage(
                "Abstract: metrics table.",
                [
                    [["feature", "v1", "v2"], ["x", "1", "2"], ["y", "3", "4"]],
                ],
            )
        ]
        fake_pdfplumber = types.SimpleNamespace(open=lambda _path: _FakePdf(pages))

        with unittest.mock.patch.dict(sys.modules, {"pdfplumber": fake_pdfplumber}):
            with self.assertRaises(ValueError) as context:
                ingest_input_document(
                    pdf_path,
                    run_dir=case_dir / "run",
                    data_dir=case_dir / "run" / "data",
                    logs_dir=case_dir / "run" / "logs",
                    selected_table_id="table_99",
                )

        self.assertIn("table_99", str(context.exception))

    def test_pdf_ingestion_fails_when_no_numeric_table_exists(self):
        case_dir = self._workspace_case_dir()
        pdf_path = case_dir / "paper.pdf"
        pdf_path.write_text("fake-pdf", encoding="utf-8")
        pages = [
            _FakePage(
                "Abstract: qualitative appendix only.",
                [
                    [["group", "label"], ["A", "high"], ["B", "low"]],
                ],
            )
        ]
        fake_pdfplumber = types.SimpleNamespace(open=lambda _path: _FakePdf(pages))

        with unittest.mock.patch.dict(sys.modules, {"pdfplumber": fake_pdfplumber}):
            result = ingest_input_document(
                pdf_path,
                run_dir=case_dir / "run",
                data_dir=case_dir / "run" / "data",
                logs_dir=case_dir / "run" / "logs",
            )

        self.assertEqual(result.status, "failed")
        self.assertIn("主表路由规则", result.summary)
        self.assertTrue(result.parsed_document_path.exists())


if __name__ == "__main__":
    unittest.main()
