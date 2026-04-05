"""Report extraction, telemetry parsing, and persistence helpers."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote


_TELEMETRY_PATTERN = re.compile(r"\s*<telemetry>\s*(\{[\s\S]*?\})\s*</telemetry>\s*$", re.IGNORECASE)
_MARKDOWN_IMAGE_PATTERN = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_INLINE_CITATION_PATTERN = re.compile(r"\[来源:\s*[^\]]+\]")
_URL_SCHEMES = ("http://", "https://", "data:", "file://")
_KNOWLEDGE_SECTION_HINTS = ("结果解释", "讨论", "结论", "背景", "result interpretation", "discussion", "conclusion", "background")
_KNOWLEDGE_CONTENT_HINTS = (
    "术语",
    "背景",
    "文献",
    "指南",
    "glossary",
    "guideline",
    "literature",
    "通常",
    "一般",
    "意味着",
    "提示",
    "说明",
    "reflects",
    "indicates",
    "suggests",
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ReportTelemetry:
    methods: tuple[str, ...] = ()
    domain: str = "unknown"
    tools_used: tuple[str, ...] = ()
    search_used: bool = False
    search_notes: str = "unknown"
    cleaned_data_saved: bool = False
    cleaned_data_path: str = ""
    figures_generated: tuple[str, ...] = ()
    valid: bool = False
    warning: str | None = None
    raw_payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class ReportExtractionResult:
    report_markdown: str
    telemetry: ReportTelemetry


@dataclass(frozen=True)
class EvidenceCitation:
    citation_label: str
    evidence_ids: tuple[str, ...] = ()
    source_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvidenceCoverage:
    status: str = "not_checked"
    citation_count: int = 0
    used_evidence_ids: tuple[str, ...] = ()
    used_citation_labels: tuple[str, ...] = ()
    cited_sources: tuple[str, ...] = ()
    invalid_citation_labels: tuple[str, ...] = ()
    uncited_knowledge_sections_detected: tuple[str, ...] = ()


def _normalize_string_list(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    normalized = [str(item).strip() for item in value if str(item).strip()]
    return tuple(normalized)


def extract_report_and_telemetry(result_text: str) -> ReportExtractionResult:
    """Extract the report body and structured telemetry from the model output."""

    if not result_text.strip():
        return ReportExtractionResult(
            report_markdown="# Data Analysis Report\n\nNo valid output was produced.",
            telemetry=ReportTelemetry(warning="missing_output"),
        )

    raw_text = result_text.strip()
    telemetry = ReportTelemetry(warning="missing")
    telemetry_match = _TELEMETRY_PATTERN.search(raw_text)
    report_body = raw_text

    if telemetry_match:
        report_body = raw_text[: telemetry_match.start()].strip()
        telemetry_json = telemetry_match.group(1).strip()
        try:
            payload = json.loads(telemetry_json)
            if not isinstance(payload, dict):
                raise ValueError("Telemetry JSON must decode to an object.")
            telemetry = ReportTelemetry(
                methods=_normalize_string_list(payload.get("methods")),
                domain=str(payload.get("domain", "unknown")).strip() or "unknown",
                tools_used=_normalize_string_list(payload.get("tools_used")),
                search_used=bool(payload.get("search_used", False)),
                search_notes=str(payload.get("search_notes", "unknown")).strip() or "unknown",
                cleaned_data_saved=bool(payload.get("cleaned_data_saved", False)),
                cleaned_data_path=str(payload.get("cleaned_data_path", "")).strip(),
                figures_generated=_normalize_string_list(payload.get("figures_generated")),
                valid=True,
                warning=None,
                raw_payload=payload,
            )
        except Exception as exc:
            telemetry = ReportTelemetry(warning=f"malformed:{exc}")

    report_match = re.search(r"(# .+[\s\S]*)", report_body)
    if report_match:
        cleaned_report = report_match.group(1).strip()
    else:
        cleaned_report = report_body.strip()

    if not cleaned_report:
        cleaned_report = "# Data Analysis Report\n\nNo valid Markdown report body was produced."

    return ReportExtractionResult(report_markdown=cleaned_report, telemetry=telemetry)


def extract_markdown_report(result_text: str) -> str:
    """Extract only the human-facing Markdown report from the agent output."""

    return extract_report_and_telemetry(result_text).report_markdown


def analyze_evidence_coverage(
    report_markdown: str,
    *,
    evidence_register: Iterable[Any] = (),
) -> EvidenceCoverage:
    chunks = tuple(evidence_register or ())
    if not chunks:
        return EvidenceCoverage(status="not_applicable")

    used_citation_labels = tuple(dict.fromkeys(_INLINE_CITATION_PATTERN.findall(report_markdown or "")))
    label_map: dict[str, list[Any]] = {}
    for chunk in chunks:
        label = str(getattr(chunk, "citation_label", "") or "").strip()
        if not label:
            continue
        label_map.setdefault(label, []).append(chunk)

    used_evidence_ids: list[str] = []
    cited_sources: list[str] = []
    invalid_citation_labels: list[str] = []
    for label in used_citation_labels:
        matched_chunks = label_map.get(label, [])
        if not matched_chunks:
            invalid_citation_labels.append(label)
            continue
        for chunk in matched_chunks:
            evidence_id = str(getattr(chunk, "evidence_id", "") or "").strip()
            if evidence_id and evidence_id not in used_evidence_ids:
                used_evidence_ids.append(evidence_id)
            source_name = str(getattr(chunk, "source_name", "") or "").strip()
            if source_name and source_name not in cited_sources:
                cited_sources.append(source_name)

    uncited_sections: list[str] = []
    for title, body in _iter_markdown_sections(report_markdown or ""):
        if not _looks_like_knowledge_section(title, body):
            continue
        if not _section_uses_knowledge_explanation(body):
            continue
        if not _INLINE_CITATION_PATTERN.search(body):
            uncited_sections.append(title)

    status = "covered"
    if invalid_citation_labels and uncited_sections:
        status = "invalid_and_missing"
    elif invalid_citation_labels:
        status = "invalid_citations"
    elif uncited_sections:
        status = "missing_citations"
    elif not used_citation_labels:
        status = "not_cited"

    return EvidenceCoverage(
        status=status,
        citation_count=len(used_citation_labels),
        used_evidence_ids=tuple(used_evidence_ids),
        used_citation_labels=used_citation_labels,
        cited_sources=tuple(cited_sources),
        invalid_citation_labels=tuple(invalid_citation_labels),
        uncited_knowledge_sections_detected=tuple(uncited_sections),
    )


def _iter_markdown_sections(report_markdown: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    current_title = "Document"
    current_lines: list[str] = []
    for line in str(report_markdown or "").splitlines():
        match = re.match(r"^##+\s+(.+?)\s*$", line.strip())
        if match:
            if current_lines:
                sections.append((current_title, "\n".join(current_lines).strip()))
            current_title = match.group(1).strip()
            current_lines = []
            continue
        current_lines.append(line)
    if current_lines:
        sections.append((current_title, "\n".join(current_lines).strip()))
    return sections


def _looks_like_knowledge_section(title: str, body: str) -> bool:
    normalized_title = str(title or "").strip().lower()
    normalized_body = str(body or "").strip().lower()
    return any(hint in normalized_title for hint in _KNOWLEDGE_SECTION_HINTS) or any(
        hint in normalized_body for hint in ("文献", "背景", "guideline", "literature", "glossary")
    )


def _section_uses_knowledge_explanation(body: str) -> bool:
    normalized = str(body or "").strip().lower()
    return any(hint in normalized for hint in _KNOWLEDGE_CONTENT_HINTS)


def _resolve_markdown_asset_path(
    raw_target: str,
    *,
    project_root: str | Path | None = None,
    base_dir: str | Path | None = None,
) -> str:
    target = raw_target.strip()
    if not target:
        return raw_target

    if target.startswith(_URL_SCHEMES) or target.startswith("/"):
        return target

    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1].strip()

    candidate_path = Path(target)
    if candidate_path.is_absolute():
        return candidate_path.resolve().as_posix()

    roots: list[Path] = []
    if base_dir is not None:
        roots.append(Path(base_dir))
    if project_root is not None:
        roots.append(Path(project_root))
    else:
        roots.append(PROJECT_ROOT)
    roots.append(Path.cwd())

    for root in roots:
        try:
            resolved = (root / candidate_path).resolve()
        except OSError:
            continue
        if resolved.exists():
            return resolved.as_posix()

    fallback_root = Path(project_root) if project_root is not None else PROJECT_ROOT
    return (fallback_root / candidate_path).resolve().as_posix()


def normalize_markdown_image_paths(
    report_markdown: str,
    *,
    project_root: str | Path | None = None,
    base_dir: str | Path | None = None,
) -> str:
    """Convert Markdown image references to absolute filesystem paths."""

    def replace(match: re.Match[str]) -> str:
        alt_text = match.group(1)
        raw_target = match.group(2).strip()
        normalized_target = _resolve_markdown_asset_path(
            raw_target,
            project_root=project_root,
            base_dir=base_dir,
        )
        return f"![{alt_text}]({normalized_target})"

    return _MARKDOWN_IMAGE_PATTERN.sub(replace, report_markdown)


def convert_markdown_images_to_gradio_urls(
    report_markdown: str,
    *,
    project_root: str | Path | None = None,
    base_dir: str | Path | None = None,
) -> str:
    """Convert Markdown image references to Gradio-served file URLs."""

    def replace(match: re.Match[str]) -> str:
        alt_text = match.group(1)
        raw_target = match.group(2).strip()
        absolute_target = _resolve_markdown_asset_path(
            raw_target,
            project_root=project_root,
            base_dir=base_dir,
        )
        # Gradio 4.x serves local files through the /file=... route.
        gradio_target = f"/file={quote(absolute_target, safe='/:')}"
        return f"![{alt_text}]({gradio_target})"

    return _MARKDOWN_IMAGE_PATTERN.sub(replace, report_markdown)


def save_markdown_report(report_markdown: str, report_path: str | Path) -> Path:
    """Persist a Markdown report to disk."""

    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report_markdown, encoding="utf-8")
    return path
