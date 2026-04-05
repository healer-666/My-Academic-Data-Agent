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

from data_analysis_agent.config import RuntimeConfig
from data_analysis_agent.knowledge_context import KnowledgeContextProvider
from data_analysis_agent.rag.document_reader import chunk_documents, load_knowledge_documents
from data_analysis_agent.rag.models import RetrievedChunk
from data_analysis_agent.rag.query_builder import build_retrieval_queries
from data_analysis_agent.rag.reranker import rerank_candidates
from data_analysis_agent.rag.service import RagService


class _FakeEmbeddingClient:
    def __init__(self, *args, **kwargs):
        pass

    def embed_texts(self, texts):
        return [[0.1, 0.2, 0.3] for _ in list(texts)]


class _FakeVectorStore:
    def __init__(self, *args, **kwargs):
        self.count_value = 0
        self.upserts = []

    def count(self):
        return self.count_value

    def replace_document(self, *, doc_id, chunks, embeddings):
        chunk_list = list(chunks)
        embedding_list = list(embeddings)
        self.upserts.append((doc_id, chunk_list, embedding_list))
        self.count_value += len(chunk_list)
        return len(chunk_list)

    def query(self, *, query_embedding, top_k=4):
        return (
            RetrievedChunk(
                chunk_id="chunk-1",
                text="Biomarker A often indicates inflammatory burden.",
                source_name="glossary.md",
                source_path="memory/knowledge_base/files/glossary.md",
                knowledge_type="glossary",
                page_number=None,
                distance=0.12,
                dense_score=0.89,
            ),
        )[:top_k]


class _FakeKeywordIndexStore:
    def __init__(self, *args, **kwargs):
        self.upserts = []

    def replace_document(self, *, doc_id, chunks):
        chunk_list = list(chunks)
        self.upserts.append((doc_id, chunk_list))
        return len(chunk_list)

    def query(self, *, keyword_query, top_k=8):
        if "keywordonly" in keyword_query:
            return (
                RetrievedChunk(
                    chunk_id="chunk-k",
                    text="Keyword-only glossary explanation for marker.",
                    source_name="keyword_glossary.md",
                    source_path="memory/knowledge_base/files/keyword_glossary.md",
                    knowledge_type="glossary",
                    keyword_score=3.5,
                ),
            )[:top_k]
        return (
            RetrievedChunk(
                chunk_id="chunk-1",
                text="Biomarker A often indicates inflammatory burden.",
                source_name="glossary.md",
                source_path="memory/knowledge_base/files/glossary.md",
                knowledge_type="glossary",
                keyword_score=2.1,
            ),
            RetrievedChunk(
                chunk_id="chunk-2",
                text="Guideline note on biomarker interpretation.",
                source_name="guideline_note.md",
                source_path="memory/knowledge_base/files/guideline_note.md",
                knowledge_type="guideline",
                keyword_score=1.8,
            ),
        )[:top_k]


class RagServiceTests(unittest.TestCase):
    def _workspace_case_dir(self) -> Path:
        base_dir = PROJECT_ROOT / "tool-output" / "test-temp"
        base_dir.mkdir(parents=True, exist_ok=True)
        case_dir = base_dir / f"rag_case_{uuid.uuid4().hex}"
        case_dir.mkdir(parents=True, exist_ok=True)
        return case_dir

    def test_load_knowledge_documents_reads_markdown_and_chunks_it(self):
        case_dir = self._workspace_case_dir()
        ref_path = case_dir / "glossary.md"
        ref_path.write_text(
            "# Notes\nBiomarker A is clinically relevant.\n\n## Interpretation\nMarker A supports inflammatory interpretation.",
            encoding="utf-8",
        )

        documents, warnings = load_knowledge_documents(ref_path)
        chunks = chunk_documents(documents, chunk_size=20, chunk_overlap=5)

        self.assertFalse(warnings)
        self.assertGreaterEqual(len(documents), 2)
        self.assertGreaterEqual(len(chunks), 2)
        self.assertEqual(chunks[0].source_name, "glossary.md")
        self.assertEqual(chunks[0].chunk_kind, "text_section")
        self.assertTrue(chunks[0].section_title)

    def test_build_retrieval_queries_splits_dense_and_keyword_queries(self):
        class _DataContext:
            columns = ["Marker_A", "GC含量", "胎儿是否健康"]
            background_literature_context = "NIPT glossary and guideline summary."
            selected_table_id = "table_01"
            candidate_table_summaries_text = "table_01 includes z-score and GC columns."

        bundle = build_retrieval_queries(
            data_context=_DataContext(),
            user_query="Please interpret marker_a and GC含量.",
        )

        self.assertIn("Marker_A", bundle.dense_query)
        self.assertIn("marker_a", bundle.keyword_query)
        self.assertIn("gc含量", bundle.keyword_query)
        self.assertTrue(bundle.normalized_terms)

    def test_load_knowledge_documents_falls_back_for_pdf(self):
        case_dir = self._workspace_case_dir()
        pdf_path = case_dir / "paper.pdf"
        pdf_path.write_text("fake-pdf", encoding="utf-8")

        with patch(
            "data_analysis_agent.rag.document_reader._read_pdf_with_pypdf",
            return_value=["", ""],
        ), patch(
            "data_analysis_agent.rag.document_reader._read_pdf_with_pdfplumber",
            return_value=["Page one text", ""],
        ):
            documents, warnings = load_knowledge_documents(pdf_path)

        self.assertEqual(len(documents), 1)
        self.assertIn("falling back", warnings[0].lower())
        self.assertEqual(documents[0].page_number, 1)

    def test_load_knowledge_documents_extracts_pdf_table_summary_when_pdfplumber_available(self):
        case_dir = self._workspace_case_dir()
        pdf_path = case_dir / "paper.pdf"
        pdf_path.write_text("fake-pdf", encoding="utf-8")

        class _FakePage:
            def extract_tables(self):
                return [
                    [["model", "precision", "recall"], ["A", "0.81", "0.74"], ["B", "0.84", "0.78"]],
                ]

        class _FakePdf:
            def __init__(self):
                self.pages = [_FakePage()]

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        fake_pdfplumber = type("_FakePdfPlumber", (), {"open": staticmethod(lambda _path: _FakePdf())})

        with patch(
            "data_analysis_agent.rag.document_reader._read_pdf_with_pypdf",
            return_value=["Results\nModel comparison section."],
        ), patch.dict(sys.modules, {"pdfplumber": fake_pdfplumber}):
            documents, warnings = load_knowledge_documents(pdf_path)

        self.assertFalse([warning for warning in warnings if "table extraction failed" in warning.lower()])
        self.assertTrue(any(document.chunk_kind == "table_summary" for document in documents))
        table_doc = next(document for document in documents if document.chunk_kind == "table_summary")
        self.assertEqual(table_doc.table_headers, ("model", "precision", "recall"))
        self.assertEqual(table_doc.table_numeric_columns, ("precision", "recall"))

    def test_rag_service_indexes_and_retrieves_with_stubbed_dependencies(self):
        case_dir = self._workspace_case_dir()
        ref_path = case_dir / "glossary.md"
        ref_path.write_text("Biomarker A maps to inflammatory burden.", encoding="utf-8")
        runtime_config = RuntimeConfig(
            model_id="demo-model",
            api_key="demo-key",
            base_url="https://example.com/v1",
            embedding_model_id="text-embedding-demo",
            embedding_api_key="embed-key",
            embedding_base_url="https://embed.example.com/v1",
        )

        with patch("data_analysis_agent.rag.service.OpenAIEmbeddingClient", _FakeEmbeddingClient), patch(
            "data_analysis_agent.rag.service.ChromaVectorStore",
            _FakeVectorStore,
        ), patch(
            "data_analysis_agent.rag.service.KeywordIndexStore",
            _FakeKeywordIndexStore,
        ):
            service = RagService(
                runtime_config=runtime_config,
                knowledge_base_dir=case_dir / "knowledge_base",
            )
            index_result = service.index_files((ref_path,))
            query_bundle = service.build_queries(
                data_context=type(
                    "_Ctx",
                    (),
                    {
                        "columns": ["marker_a", "marker_b"],
                        "background_literature_context": "Guideline summary.",
                        "selected_table_id": "",
                        "candidate_table_summaries_text": "",
                    },
                )(),
                user_query="Explain biomarker A.",
            )
            retrieval_result = service.retrieve(
                retrieval_query=query_bundle.retrieval_query,
                dense_query=query_bundle.dense_query,
                keyword_query=query_bundle.keyword_query,
                query_terms=query_bundle.normalized_terms,
                column_terms=("marker_a", "marker_b"),
                top_k=4,
            )

        self.assertEqual(index_result.status, "completed")
        self.assertEqual(index_result.indexed_documents, ("glossary.md",))
        self.assertEqual(retrieval_result.status, "retrieved")
        self.assertEqual(retrieval_result.retrieval_strategy, "hybrid")
        self.assertGreaterEqual(retrieval_result.dense_match_count, 1)
        self.assertGreaterEqual(retrieval_result.keyword_match_count, 1)
        self.assertGreaterEqual(retrieval_result.match_count, 1)
        self.assertIn("glossary.md", retrieval_result.source_names)
        self.assertTrue(retrieval_result.reranked_chunks[0].evidence_id.startswith("RAG-glossary-md-"))
        self.assertEqual(retrieval_result.reranked_chunks[0].citation_label, "[来源: glossary.md]")

    def test_rag_service_keyword_only_match_still_returns_results(self):
        case_dir = self._workspace_case_dir()
        ref_path = case_dir / "keyword_glossary.md"
        ref_path.write_text("Keyword only explanation.", encoding="utf-8")
        runtime_config = RuntimeConfig(
            model_id="demo-model",
            api_key="demo-key",
            base_url="https://example.com/v1",
            embedding_model_id="text-embedding-demo",
            embedding_api_key="embed-key",
            embedding_base_url="https://embed.example.com/v1",
        )

        class _DenseEmptyStore(_FakeVectorStore):
            def query(self, *, query_embedding, top_k=4):
                return ()

        with patch("data_analysis_agent.rag.service.OpenAIEmbeddingClient", _FakeEmbeddingClient), patch(
            "data_analysis_agent.rag.service.ChromaVectorStore",
            _DenseEmptyStore,
        ), patch(
            "data_analysis_agent.rag.service.KeywordIndexStore",
            _FakeKeywordIndexStore,
        ):
            service = RagService(
                runtime_config=runtime_config,
                knowledge_base_dir=case_dir / "knowledge_base",
            )
            service.index_files((ref_path,))
            retrieval_result = service.retrieve(
                retrieval_query="keywordonly marker",
                dense_query="keywordonly marker",
                keyword_query="keywordonly marker",
                query_terms=("keywordonly", "marker"),
                column_terms=("marker",),
                top_k=4,
            )

        self.assertEqual(retrieval_result.status, "retrieved")
        self.assertEqual(retrieval_result.dense_match_count, 0)
        self.assertEqual(retrieval_result.keyword_match_count, 1)
        self.assertEqual(retrieval_result.source_names, ("keyword_glossary.md",))

    def test_rag_service_builds_ephemeral_table_candidates_from_parsed_document(self):
        case_dir = self._workspace_case_dir()
        parsed_path = case_dir / "parsed_document.json"
        parsed_path.write_text(
            '{"source_pdf":"demo.pdf","selected_table_id":"table_02","candidate_table_summaries":[{"table_id":"table_01","page_number":2,"headers":["model","precision"],"numeric_columns":["precision"],"content_hint":"A | 0.81"},{"table_id":"table_02","page_number":3,"headers":["model","recall"],"numeric_columns":["recall"],"content_hint":"B | 0.78"}]}',
            encoding="utf-8",
        )
        runtime_config = RuntimeConfig(
            model_id="demo-model",
            api_key="demo-key",
            base_url="https://example.com/v1",
            embedding_model_id="text-embedding-demo",
            embedding_api_key="embed-key",
            embedding_base_url="https://embed.example.com/v1",
        )

        with patch("data_analysis_agent.rag.service.OpenAIEmbeddingClient", _FakeEmbeddingClient), patch(
            "data_analysis_agent.rag.service.ChromaVectorStore",
            _FakeVectorStore,
        ), patch(
            "data_analysis_agent.rag.service.KeywordIndexStore",
            _FakeKeywordIndexStore,
        ):
            service = RagService(runtime_config=runtime_config, knowledge_base_dir=case_dir / "knowledge_base")
            candidates = service.build_ephemeral_table_candidates(
                data_context=type(
                    "_Ctx",
                    (),
                    {"parsed_document_path": parsed_path, "selected_table_id": "table_02"},
                )(),
            )

        self.assertEqual(len(candidates), 2)
        self.assertTrue(all(candidate.chunk_kind == "table_summary" for candidate in candidates))
        self.assertTrue(any("selected_table" in candidate.match_reasons for candidate in candidates))

    def test_rule_reranker_promotes_guideline_and_dedupes_source_bias(self):
        reranked = rerank_candidates(
            candidates=(
                RetrievedChunk(
                    chunk_id="a1",
                    text="marker_a glossary note",
                    source_name="glossary.md",
                    source_path="x",
                    knowledge_type="glossary",
                    dense_score=0.7,
                    keyword_score=1.2,
                ),
                RetrievedChunk(
                    chunk_id="a2",
                    text="marker_a general note",
                    source_name="general.md",
                    source_path="y",
                    knowledge_type="general",
                    dense_score=0.72,
                    keyword_score=1.1,
                ),
                RetrievedChunk(
                    chunk_id="a3",
                    text="marker_a guideline interpretation",
                    source_name="guideline.md",
                    source_path="z",
                    knowledge_type="guideline",
                    dense_score=0.65,
                    keyword_score=1.0,
                ),
            ),
            query_terms=("marker_a", "interpretation"),
            column_terms=("marker_a",),
            top_k=2,
        )

        self.assertEqual(len(reranked), 2)
        self.assertEqual(reranked[0].source_name, "guideline.md")
        self.assertIsNotNone(reranked[0].rerank_score)

    def test_rule_reranker_promotes_selected_table_summary(self):
        reranked = rerank_candidates(
            candidates=(
                RetrievedChunk(
                    chunk_id="table-1",
                    text="Ephemeral table summary for table_02. Headers: precision, recall.",
                    source_name="demo.pdf",
                    source_path="x",
                    chunk_kind="table_summary",
                    table_id="table_02",
                    table_headers=("precision", "recall"),
                    table_numeric_columns=("precision", "recall"),
                ),
                RetrievedChunk(
                    chunk_id="text-1",
                    text="Results discussion for model comparison.",
                    source_name="demo.pdf",
                    source_path="y",
                    chunk_kind="text_section",
                    section_title="Results",
                ),
            ),
            query_terms=("precision", "recall"),
            column_terms=("precision", "recall"),
            selected_table_id="table_02",
            top_k=1,
        )

        self.assertEqual(reranked[0].chunk_kind, "table_summary")
        self.assertIn("selected_table", reranked[0].match_reasons)

    def test_knowledge_context_provider_renders_evidence_register(self):
        provider = KnowledgeContextProvider(max_retrieved_chars=400)
        bundle = provider.collect(
            data_context=type(
                "_Ctx",
                (),
                {"background_literature_context": "", "columns": ("marker_a",)},
            )(),
            user_query="Explain biomarker A.",
            retrieved_chunks=(
                RetrievedChunk(
                    chunk_id="chunk-1",
                    text="Biomarker A usually reflects inflammatory burden.",
                    source_name="glossary.md",
                    source_path="memory/glossary.md",
                ),
            ),
        )

        rendered = bundle.render_for_prompt()

        self.assertIn("<Retrieved_Knowledge_Context>", rendered)
        self.assertIn("<Retrieved_Evidence_Register>", rendered)
        self.assertIn("RAG-glossary-md-chunk-1", rendered)
        self.assertIn("[来源: glossary.md]", rendered)


if __name__ == "__main__":
    unittest.main()
