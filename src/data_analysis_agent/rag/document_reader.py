"""Knowledge-document loading and structured chunking helpers."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Iterable

from .models import KnowledgeChunk, KnowledgeDocument


SUPPORTED_KNOWLEDGE_SUFFIXES = frozenset({".txt", ".md", ".pdf"})

_SECTION_HEADING_PATTERN = re.compile(
    r"^(abstract|introduction|background|methods?|materials?|results?|discussion|conclusion|references?)\b[:：]?\s*$",
    flags=re.IGNORECASE,
)
_NUMBERED_HEADING_PATTERN = re.compile(r"^\d+(?:\.\d+)*\s+\S+")


def build_doc_id(path: str | Path) -> str:
    resolved = Path(path).resolve()
    try:
        digest = hashlib.sha1(resolved.read_bytes()).hexdigest()[:12]
    except Exception:
        digest = hashlib.sha1(resolved.as_posix().encode("utf-8")).hexdigest()[:12]
    safe_name = "".join(ch if ch.isalnum() else "-" for ch in resolved.stem).strip("-") or "knowledge"
    return f"{safe_name[:32]}-{digest}"


def load_knowledge_documents(path: str | Path) -> tuple[tuple[KnowledgeDocument, ...], tuple[str, ...]]:
    resolved = Path(path).resolve()
    suffix = resolved.suffix.lower()
    knowledge_type = infer_knowledge_type(resolved.name)
    if suffix not in SUPPORTED_KNOWLEDGE_SUFFIXES:
        return (), (f"Unsupported knowledge file type: {resolved.name}",)
    if suffix == ".md":
        return _load_text_documents(resolved, source_type="md", knowledge_type=knowledge_type, markdown_mode=True)
    if suffix == ".txt":
        return _load_text_documents(resolved, source_type="txt", knowledge_type=knowledge_type, markdown_mode=False)
    return _load_pdf_documents(resolved, knowledge_type=knowledge_type)


def chunk_documents(
    documents: tuple[KnowledgeDocument, ...],
    *,
    chunk_size: int = 800,
    chunk_overlap: int = 120,
) -> tuple[KnowledgeChunk, ...]:
    effective_chunk_size = max(200, int(chunk_size))
    effective_overlap = max(0, min(int(chunk_overlap), effective_chunk_size - 1))
    chunks: list[KnowledgeChunk] = []
    for document_number, document in enumerate(documents, start=1):
        text = document.text.strip()
        if not text:
            continue
        chunk_texts = _split_text_with_overlap(
            text,
            chunk_size=effective_chunk_size,
            chunk_overlap=effective_overlap,
            preserve_whole=(document.chunk_kind == "table_summary"),
        )
        for index, chunk_text in enumerate(chunk_texts, start=1):
            page_label = document.page_number or 0
            chunks.append(
                    KnowledgeChunk(
                        doc_id=document.doc_id,
                        chunk_id=f"{document.doc_id}-d{document_number}-p{page_label}-c{index}-{document.chunk_kind}",
                    text=chunk_text,
                    source_name=document.source_name,
                    source_type=document.source_type,
                    source_path=document.source_path,
                    knowledge_type=document.knowledge_type,
                    page_number=document.page_number,
                    chunk_kind=document.chunk_kind,
                    section_title=document.section_title,
                    heading_path=document.heading_path,
                    table_id=document.table_id,
                    table_headers=document.table_headers,
                    table_numeric_columns=document.table_numeric_columns,
                    content_hint=document.content_hint,
                )
            )
    return tuple(chunks)


def infer_knowledge_type(file_name: str) -> str:
    lowered = str(file_name or "").lower()
    if "glossary" in lowered:
        return "glossary"
    if "guideline" in lowered or "guide" in lowered:
        return "guideline"
    if "summary" in lowered:
        return "paper_summary"
    return "general"


def _load_text_documents(
    path: Path,
    *,
    source_type: str,
    knowledge_type: str,
    markdown_mode: bool,
) -> tuple[tuple[KnowledgeDocument, ...], tuple[str, ...]]:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        return (), (f"Failed to read knowledge file {path.name}: {exc}",)
    normalized = str(text or "").strip()
    if not normalized:
        return (), (f"Knowledge file {path.name} is empty after normalization.",)
    doc_id = build_doc_id(path)
    sections = _split_markdown_sections(normalized) if markdown_mode else _split_plaintext_sections(normalized)
    documents = tuple(
        KnowledgeDocument(
            doc_id=doc_id,
            source_name=path.name,
            source_type=source_type,
            source_path=path.as_posix(),
            text=_normalize_text(section["text"]),
            knowledge_type=knowledge_type,
            chunk_kind="text_section",
            section_title=str(section.get("section_title", "") or ""),
            heading_path=tuple(str(item) for item in section.get("heading_path", ()) if str(item or "").strip()),
        )
        for section in sections
        if _normalize_text(str(section.get("text", "") or ""))
    )
    if not documents:
        return (), (f"Knowledge file {path.name} produced no readable sections.",)
    return documents, ()


def _load_pdf_documents(path: Path, *, knowledge_type: str) -> tuple[tuple[KnowledgeDocument, ...], tuple[str, ...]]:
    warnings: list[str] = []
    page_texts = _read_pdf_with_pypdf(path)
    if not any(page_texts):
        warnings.append(f"Primary PDF extraction returned no text for {path.name}; falling back to pdfplumber.")
        page_texts = _read_pdf_with_pdfplumber(path)

    doc_id = build_doc_id(path)
    documents: list[KnowledgeDocument] = []
    for page_number, text in enumerate(page_texts, start=1):
        documents.extend(
            _build_pdf_text_documents(
                path=path,
                doc_id=doc_id,
                text=text,
                page_number=page_number,
                knowledge_type=knowledge_type,
            )
        )

    table_documents, table_warnings = _extract_pdf_table_documents(
        path=path,
        doc_id=doc_id,
        knowledge_type=knowledge_type,
    )
    documents.extend(table_documents)
    warnings.extend(table_warnings)

    if not documents:
        warnings.append(f"Knowledge PDF {path.name} did not yield readable text and was skipped.")
    return tuple(documents), tuple(warnings)


def _build_pdf_text_documents(
    *,
    path: Path,
    doc_id: str,
    text: str,
    page_number: int,
    knowledge_type: str,
) -> list[KnowledgeDocument]:
    normalized = str(text or "").strip()
    if not normalized:
        return []
    sections = _split_pdf_sections(normalized, page_number=page_number)
    documents: list[KnowledgeDocument] = []
    for section in sections:
        section_text = _normalize_text(str(section.get("text", "") or ""))
        if not section_text:
            continue
        documents.append(
            KnowledgeDocument(
                doc_id=doc_id,
                source_name=path.name,
                source_type="pdf",
                source_path=path.as_posix(),
                text=section_text,
                knowledge_type=knowledge_type,
                page_number=page_number,
                chunk_kind="text_section",
                section_title=str(section.get("section_title", "") or ""),
                heading_path=tuple(str(item) for item in section.get("heading_path", ()) if str(item or "").strip()),
            )
        )
    return documents


def _extract_pdf_table_documents(
    *,
    path: Path,
    doc_id: str,
    knowledge_type: str,
) -> tuple[list[KnowledgeDocument], list[str]]:
    try:
        import pdfplumber
    except Exception:
        return [], ["pdfplumber is unavailable; skipping PDF table-aware chunk extraction."]

    documents: list[KnowledgeDocument] = []
    warnings: list[str] = []
    try:
        with pdfplumber.open(str(path)) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                for table_index, raw_table in enumerate(page.extract_tables() or [], start=1):
                    rows = [list(row) for row in raw_table if any(str(cell or "").strip() for cell in row)]
                    if len(rows) < 2:
                        continue
                    headers = tuple(_normalize_header(cell, index) for index, cell in enumerate(rows[0]))
                    body_rows = [
                        tuple(_normalize_cell(row[index] if index < len(row) else "") for index in range(len(headers)))
                        for row in rows[1:]
                    ]
                    if not body_rows:
                        continue
                    numeric_columns = tuple(
                        header
                        for header, column_values in zip(headers, zip(*body_rows))
                        if _looks_numeric(column_values)
                    )
                    content_hint = _build_table_content_hint(body_rows)
                    table_id = f"table_p{page_number:02d}_{table_index:02d}"
                    summary_text = _build_table_summary_text(
                        table_id=table_id,
                        page_number=page_number,
                        headers=headers,
                        numeric_columns=numeric_columns,
                        content_hint=content_hint,
                    )
                    documents.append(
                        KnowledgeDocument(
                            doc_id=doc_id,
                            source_name=path.name,
                            source_type="pdf",
                            source_path=path.as_posix(),
                            text=summary_text,
                            knowledge_type=knowledge_type,
                            page_number=page_number,
                            chunk_kind="table_summary",
                            section_title=f"Table {table_id}",
                            heading_path=(f"Page {page_number}", f"Table {table_index}"),
                            table_id=table_id,
                            table_headers=headers,
                            table_numeric_columns=numeric_columns,
                            content_hint=content_hint,
                        )
                    )
    except Exception as exc:
        warnings.append(f"Table extraction failed for {path.name}: {exc}")
    return documents, warnings


def _split_markdown_sections(text: str) -> list[dict[str, object]]:
    sections: list[dict[str, object]] = []
    current_heading_path: list[str] = []
    current_title = ""
    current_lines: list[str] = []

    def flush_section() -> None:
        section_text = _normalize_text("\n".join(current_lines))
        if not section_text:
            return
        sections.append(
            {
                "section_title": current_title or (current_heading_path[-1] if current_heading_path else ""),
                "heading_path": tuple(current_heading_path),
                "text": section_text,
            }
        )

    for raw_line in str(text or "").splitlines():
        line = raw_line.rstrip()
        heading_match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if heading_match:
            flush_section()
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()
            current_heading_path = current_heading_path[: level - 1]
            current_heading_path.append(title)
            current_title = title
            current_lines = []
            continue
        if not line.strip() and current_lines:
            current_lines.append("")
            continue
        if line.strip():
            current_lines.append(line)

    flush_section()
    if sections:
        return sections
    return _split_plaintext_sections(text)


def _split_plaintext_sections(text: str) -> list[dict[str, object]]:
    paragraphs = [
        _normalize_text(block)
        for block in re.split(r"\n\s*\n", str(text or ""))
        if _normalize_text(block)
    ]
    if not paragraphs:
        return []
    return [
        {
            "section_title": f"Section {index}",
            "heading_path": (),
            "text": paragraph,
        }
        for index, paragraph in enumerate(paragraphs, start=1)
    ]


def _split_pdf_sections(text: str, *, page_number: int) -> list[dict[str, object]]:
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if not lines:
        return []

    sections: list[dict[str, object]] = []
    current_title = f"Page {page_number}"
    current_lines: list[str] = []

    def flush_section() -> None:
        section_text = _normalize_text("\n".join(current_lines))
        if not section_text:
            return
        sections.append(
            {
                "section_title": current_title,
                "heading_path": (current_title,),
                "text": section_text,
            }
        )

    for line in lines:
        if _looks_like_section_heading(line):
            flush_section()
            current_title = line
            current_lines = []
            continue
        current_lines.append(line)
    flush_section()
    return sections


def _looks_like_section_heading(line: str) -> bool:
    clean = str(line or "").strip()
    if not clean:
        return False
    if _SECTION_HEADING_PATTERN.match(clean) or _NUMBERED_HEADING_PATTERN.match(clean):
        return True
    if len(clean) <= 60 and clean.upper() == clean and len(clean.split()) <= 8:
        return True
    return False


def _split_text_with_overlap(
    text: str,
    *,
    chunk_size: int,
    chunk_overlap: int,
    preserve_whole: bool,
) -> tuple[str, ...]:
    normalized = str(text or "").strip()
    if not normalized:
        return ()
    if preserve_whole or len(normalized) <= chunk_size:
        return (normalized,)
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + chunk_size)
        piece = normalized[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(normalized):
            break
        start = max(end - chunk_overlap, start + 1)
    return tuple(chunks)


def _normalize_text(text: str) -> str:
    return " ".join(str(text or "").split()).strip()


def _normalize_header(value: object, index: int) -> str:
    normalized = _normalize_text(str(value or ""))
    return normalized or f"column_{index + 1}"


def _normalize_cell(value: object) -> str:
    return _normalize_text(str(value or ""))


def _looks_numeric(values: Iterable[str]) -> bool:
    seen = False
    for value in values:
        normalized = str(value or "").replace(",", "").replace("%", "").strip()
        if not normalized:
            continue
        seen = True
        try:
            float(normalized)
        except Exception:
            return False
    return seen


def _build_table_content_hint(rows: Iterable[tuple[str, ...]], *, max_rows: int = 2, max_cols: int = 4) -> str:
    preview_lines: list[str] = []
    for row in list(rows)[:max_rows]:
        cells = [cell for cell in row[:max_cols] if str(cell or "").strip()]
        if cells:
            preview_lines.append(" | ".join(cells))
    return " || ".join(preview_lines)


def _build_table_summary_text(
    *,
    table_id: str,
    page_number: int,
    headers: tuple[str, ...],
    numeric_columns: tuple[str, ...],
    content_hint: str,
) -> str:
    header_text = ", ".join(headers[:10]) if headers else "none"
    numeric_text = ", ".join(numeric_columns[:10]) if numeric_columns else "none"
    return _normalize_text(
        (
            f"Table summary for {table_id}. Page {page_number}. "
            f"Headers: {header_text}. "
            f"Numeric columns: {numeric_text}. "
            f"Content hint: {content_hint or 'none'}."
        )
    )


def _read_pdf_with_pypdf(path: Path) -> list[str]:
    try:
        from pypdf import PdfReader
    except Exception:
        return []
    try:
        reader = PdfReader(str(path))
    except Exception:
        return []
    page_texts: list[str] = []
    for page in getattr(reader, "pages", []):
        try:
            page_texts.append(str(page.extract_text() or ""))
        except Exception:
            page_texts.append("")
    return page_texts


def _read_pdf_with_pdfplumber(path: Path) -> list[str]:
    try:
        import pdfplumber
    except Exception:
        return []
    page_texts: list[str] = []
    try:
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                try:
                    page_texts.append(str(page.extract_text() or ""))
                except Exception:
                    page_texts.append("")
    except Exception:
        return []
    return page_texts
