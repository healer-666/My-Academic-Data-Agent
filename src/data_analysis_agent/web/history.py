"""History browsing helpers for the Gradio web UI."""

from __future__ import annotations

import html
import json
from dataclasses import dataclass
from pathlib import Path

from ..reporting import convert_markdown_images_to_gradio_urls
from .viewmodels import (
    ingestion_status_label,
    input_kind_label,
    latency_mode_label,
    quality_mode_label,
    review_status_label,
    vision_review_status_label,
    workflow_status_label,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class RunHistoryEntry:
    run_dir: Path
    timestamp: str
    quality_mode: str
    latency_mode: str
    input_kind: str
    document_ingestion_status: str
    document_ingestion_summary: str
    candidate_table_count: int
    selected_table_id: str
    selected_table_shape: tuple[int, int] | None
    pdf_multi_table_mode: bool
    review_status: str
    vision_review_status: str
    vision_review_summary: str
    workflow_complete: bool
    stage_contract_status: str
    stage_contract_findings: tuple[str, ...]
    stage_contract_passed: bool
    domain: str
    report_path: Path | None
    trace_path: Path | None
    cleaned_data_path: Path | None
    document_ingestion_log_path: Path | None
    figure_paths: tuple[Path, ...]
    trace_payload: dict[str, object]


def _escape(value: object) -> str:
    return html.escape(str(value))


def _resolve_outputs_root(outputs_root: str | Path = "outputs") -> Path:
    root = Path(outputs_root)
    return root if root.is_absolute() else (PROJECT_ROOT / root)


def _resolve_candidate_path(path_value: str | Path | None, *, base_dir: Path) -> Path | None:
    if not path_value:
        return None
    candidate = Path(path_value)
    if candidate.is_absolute():
        return candidate
    direct = (PROJECT_ROOT / candidate).resolve()
    if direct.exists():
        return direct
    nested = (base_dir / candidate).resolve()
    if nested.exists():
        return nested
    return direct


def _read_trace_payload(trace_path: Path | None) -> dict[str, object]:
    if trace_path is None or not trace_path.exists():
        return {}
    try:
        payload = json.loads(trace_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _infer_timestamp_from_name(run_dir: Path) -> str:
    name = run_dir.name
    if not name.startswith("run_"):
        return name
    parts = name.split("_", 2)
    if len(parts) < 3:
        return name
    date_part, time_part = parts[1], parts[2]
    if len(date_part) == 8 and len(time_part) == 6:
        return f"{date_part[0:4]}-{date_part[4:6]}-{date_part[6:8]} {time_part[0:2]}:{time_part[2:4]}:{time_part[4:6]}"
    return name


def _collect_figure_paths(run_dir: Path, trace_payload: dict[str, object]) -> tuple[Path, ...]:
    telemetry = trace_payload.get("telemetry", {})
    if isinstance(telemetry, dict):
        figure_values = telemetry.get("figures_generated", [])
        if isinstance(figure_values, list) and figure_values:
            resolved = [
                _resolve_candidate_path(item, base_dir=run_dir)
                for item in figure_values
                if str(item).strip()
            ]
            return tuple(path for path in resolved if path is not None)

    figure_dir = run_dir / "figures"
    if not figure_dir.exists():
        return ()

    image_paths = sorted(
        path
        for path in figure_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".svg"}
    )
    return tuple(image_paths)


def _latest_visual_summary(trace_payload: dict[str, object]) -> tuple[str, str]:
    history = trace_payload.get("vision_review_history", [])
    if isinstance(history, list) and history:
        latest = history[-1]
        if isinstance(latest, dict):
            return (
                str(latest.get("status", "skipped")).strip() or "skipped",
                str(latest.get("summary", "")).strip() or "暂无视觉审稿摘要。",
            )
    return "skipped", "暂无视觉审稿摘要。"


def _build_history_entry(run_dir: Path) -> RunHistoryEntry:
    trace_path = run_dir / "logs" / "agent_trace.json"
    trace_payload = _read_trace_payload(trace_path if trace_path.exists() else None)
    run_metadata = trace_payload.get("run_metadata", {})
    telemetry = trace_payload.get("telemetry", {})
    artifact_validation = trace_payload.get("artifact_validation", {})
    document_ingestion = trace_payload.get("document_ingestion", {})

    if not isinstance(run_metadata, dict):
        run_metadata = {}
    if not isinstance(telemetry, dict):
        telemetry = {}
    if not isinstance(artifact_validation, dict):
        artifact_validation = {}
    if not isinstance(document_ingestion, dict):
        document_ingestion = {}

    selected_shape_value = document_ingestion.get("selected_table_shape")
    selected_shape = None
    if isinstance(selected_shape_value, list) and len(selected_shape_value) == 2:
        try:
            selected_shape = (int(selected_shape_value[0]), int(selected_shape_value[1]))
        except (TypeError, ValueError):
            selected_shape = None

    report_path = run_dir / "final_report.md"
    cleaned_data_path = run_dir / "data" / "cleaned_data.csv"
    figure_paths = _collect_figure_paths(run_dir, trace_payload)
    vision_status, vision_summary = _latest_visual_summary(trace_payload)
    ingestion_log_path = run_dir / "logs" / "document_ingestion.json"

    return RunHistoryEntry(
        run_dir=run_dir.resolve(),
        timestamp=str(run_metadata.get("timestamp", "")).strip() or _infer_timestamp_from_name(run_dir),
        quality_mode=str(run_metadata.get("quality_mode", "unknown")).strip() or "unknown",
        latency_mode=str(run_metadata.get("latency_mode", "auto")).strip() or "auto",
        input_kind=str(run_metadata.get("input_kind", document_ingestion.get("input_kind", "tabular"))).strip()
        or "tabular",
        document_ingestion_status=str(document_ingestion.get("status", "not_needed")).strip() or "not_needed",
        document_ingestion_summary=str(document_ingestion.get("summary", "")).strip(),
        candidate_table_count=int(document_ingestion.get("candidate_table_count", 0) or 0),
        selected_table_id=str(document_ingestion.get("selected_table_id", "")).strip(),
        selected_table_shape=selected_shape,
        pdf_multi_table_mode=bool(document_ingestion.get("pdf_multi_table_mode", False)),
        review_status=str(trace_payload.get("review_status", "unknown")).strip() or "unknown",
        vision_review_status=vision_status,
        vision_review_summary=vision_summary,
        workflow_complete=bool(artifact_validation.get("workflow_complete", False)),
        stage_contract_status=str(artifact_validation.get("stage_contract_status", "not_checked")).strip() or "not_checked",
        stage_contract_findings=tuple(
            str(item).strip()
            for item in artifact_validation.get("stage_contract_findings", [])
            if str(item).strip()
        )
        if isinstance(artifact_validation.get("stage_contract_findings", []), list)
        else (),
        stage_contract_passed=bool(artifact_validation.get("stage_contract_passed", False)),
        domain=str(telemetry.get("domain", "unknown")).strip() or "unknown",
        report_path=report_path.resolve() if report_path.exists() else None,
        trace_path=trace_path.resolve() if trace_path.exists() else None,
        cleaned_data_path=cleaned_data_path.resolve() if cleaned_data_path.exists() else None,
        document_ingestion_log_path=ingestion_log_path.resolve() if ingestion_log_path.exists() else None,
        figure_paths=figure_paths,
        trace_payload=trace_payload,
    )


def scan_run_history(outputs_root: str | Path = "outputs") -> list[RunHistoryEntry]:
    root = _resolve_outputs_root(outputs_root)
    if not root.exists():
        return []

    entries = []
    for candidate in root.iterdir():
        if candidate.is_dir() and candidate.name.startswith("run_"):
            entries.append(_build_history_entry(candidate))
    return sorted(entries, key=lambda item: (item.timestamp, item.run_dir.name), reverse=True)


def build_history_label(entry: RunHistoryEntry) -> str:
    timestamp = entry.timestamp.replace("T", " ")
    return f"{entry.run_dir.name} | {entry.domain} | {review_status_label(entry.review_status)} | {timestamp}"


def build_history_choices(outputs_root: str | Path = "outputs") -> tuple[list[tuple[str, str]], str | None]:
    entries = scan_run_history(outputs_root)
    choices = [(build_history_label(entry), entry.run_dir.as_posix()) for entry in entries]
    selected = choices[0][1] if choices else None
    return choices, selected


def _build_history_overview_html(entry: RunHistoryEntry) -> str:
    memory_payload = entry.trace_payload.get("success_memory", entry.trace_payload.get("memory", {}))
    if not isinstance(memory_payload, dict):
        memory_payload = {}
    failure_memory_payload = entry.trace_payload.get("failure_memory", {})
    if not isinstance(failure_memory_payload, dict):
        failure_memory_payload = {}
    table_shape = (
        f"{entry.selected_table_shape[0]} x {entry.selected_table_shape[1]}"
        if entry.selected_table_shape
        else "unknown"
    )
    cards = [
        ("时间", entry.timestamp),
        ("领域", entry.domain),
        ("输入", input_kind_label(entry.input_kind)),
        ("质量", quality_mode_label(entry.quality_mode)),
        ("阶段审计", "已通过" if entry.stage_contract_passed else entry.stage_contract_status),
        ("文本审稿", review_status_label(entry.review_status)),
        ("工作流", workflow_status_label(entry.workflow_complete)),
    ]
    card_html = "".join(
        (
            "<article class='metric-card'>"
            f"<div class='metric-label'>{_escape(label)}</div>"
            f"<div class='metric-value'>{_escape(value)}</div>"
            "</article>"
        )
        for label, value in cards
    )

    if entry.input_kind == "pdf":
        multi_table = "已启用" if entry.pdf_multi_table_mode else "未启用"
        ingestion_block = (
            "<div class='review-highlight'>"
            "<div class='review-status-pill'>PDF 主表</div>"
            f"<div class='review-highlight-body'>状态：{_escape(ingestion_status_label(entry.document_ingestion_status))}<br>"
            f"候选表数量：{_escape(entry.candidate_table_count)}<br>"
            f"主表：{_escape(entry.selected_table_id or 'unknown')}<br>"
            f"形状：{_escape(table_shape)}<br>"
            f"PDF 多表综合：{_escape(multi_table)}</div>"
            "</div>"
        )
    else:
        ingestion_block = (
            "<div class='review-highlight'>"
            "<div class='review-status-pill'>文档解析</div>"
            "<div class='review-highlight-body'>输入已是结构化表格，无需额外解析。</div>"
            "</div>"
        )

    visual_block = (
        "<div class='review-highlight'>"
        f"<div class='review-status-pill'>视觉审稿 · {_escape(vision_review_status_label(entry.vision_review_status))}</div>"
        f"<div class='review-highlight-body'>{_escape(entry.vision_review_summary)}</div>"
        "</div>"
    )
    memory_block = (
        "<div class='review-highlight'>"
        "<div class='review-status-pill'>历史经验</div>"
        f"<div class='review-highlight-body'>状态：{'启用' if bool(memory_payload.get('enabled', False)) else '关闭'}<br>"
        f"分组：{_escape(memory_payload.get('scope_key', 'N/A'))}<br>"
        f"命中：{_escape(len(memory_payload.get('retrieved_records', [])) if isinstance(memory_payload.get('retrieved_records'), list) else 0)} 条</div>"
        "</div>"
    )
    audit_findings = "<br>".join(_escape(item) for item in entry.stage_contract_findings) or "未记录阶段审计问题。"
    audit_block = (
        "<div class='review-highlight'>"
        "<div class='review-status-pill'>阶段审计</div>"
        f"<div class='review-highlight-body'>状态：{_escape('已通过' if entry.stage_contract_passed else entry.stage_contract_status)}<br>"
        f"{audit_findings}</div>"
        "</div>"
    )

    return (
        "<section class='results-overview'>"
        "<div class='section-heading'>历史运行总览</div>"
        f"<div class='section-subtitle'>{_escape(entry.run_dir.name)}</div>"
        f"{ingestion_block}"
        f"<div class='metric-grid'>{card_html}</div>"
        f"{audit_block}"
        f"{memory_block}"
        f"{visual_block}"
        "</section>"
    )


def _build_history_trace_html(entry: RunHistoryEntry) -> str:
    payload = entry.trace_payload
    memory_payload = payload.get("memory", {})
    if not isinstance(memory_payload, dict):
        memory_payload = {}
    step_traces = payload.get("step_traces", [])
    warnings: list[str] = []
    artifact_validation = payload.get("artifact_validation", {})
    if isinstance(artifact_validation, dict):
        warning_values = artifact_validation.get("warnings", [])
        if isinstance(warning_values, list):
            warnings = [str(item).strip() for item in warning_values if str(item).strip()]

    if not isinstance(step_traces, list):
        step_traces = []

    recent_rows = []
    for item in step_traces[-8:]:
        if not isinstance(item, dict):
            continue
        step_index = item.get("step_index", "?")
        tool_name = item.get("tool_name") or item.get("action", "unknown")
        summary = item.get("summary") or item.get("observation_preview") or "无摘要。"
        recent_rows.append(
            "<tr>"
            f"<td>{_escape(step_index)}</td>"
            f"<td>{_escape(tool_name)}</td>"
            f"<td>{_escape(summary)}</td>"
            "</tr>"
        )

    warnings_html = "".join(f"<li>{_escape(item)}</li>" for item in warnings) or "<li>无</li>"
    table_html = "".join(recent_rows) or "<tr><td colspan='3'>暂无可展示的轨迹摘要。</td></tr>"

    extra_rows = []
    if memory_payload:
        extra_rows.append(
            "<tr>"
            "<td>历史经验</td>"
            f"<td colspan='2'>分组={_escape(memory_payload.get('scope_key', 'N/A'))} | "
            f"读取={_escape(memory_payload.get('retrieval_status', 'unknown'))} | "
            f"写回={_escape(memory_payload.get('writeback_status', 'unknown'))}</td>"
            "</tr>"
        )
    if entry.stage_contract_status:
        extra_rows.append(
            "<tr>"
            "<td>阶段审计</td>"
            f"<td colspan='2'>状态={_escape(entry.stage_contract_status)} | "
            f"passed={_escape(entry.stage_contract_passed)} | "
            f"findings={_escape(' | '.join(entry.stage_contract_findings) if entry.stage_contract_findings else 'none')}</td>"
            "</tr>"
        )
    if entry.document_ingestion_log_path is not None:
        extra_rows.append(
            "<tr>"
            "<td>文档解析日志</td>"
            f"<td colspan='2'>{_escape(entry.document_ingestion_log_path.as_posix())}</td>"
            "</tr>"
        )
    if entry.trace_path is not None:
        extra_rows.append(
            "<tr>"
            "<td>Trace</td>"
            f"<td colspan='2'>{_escape(entry.trace_path.as_posix())}</td>"
            "</tr>"
        )
    extra_table = "".join(extra_rows) or "<tr><td colspan='3'>暂无额外诊断信息。</td></tr>"

    return (
        "<section class='trace-workbench'>"
        "<div class='section-heading'>历史诊断与轨迹</div>"
        "<div class='section-subtitle'>展示最近步骤、文档解析日志和工件告警，便于快速回顾历史分析。</div>"
        "<div class='history-trace-grid'>"
        "<div class='history-trace-card'>"
        "<div class='history-trace-title'>工件告警</div>"
        f"<div class='history-scroll-area'><ul class='history-warning-list'>{warnings_html}</ul></div>"
        "</div>"
        "<div class='history-trace-card'>"
        "<div class='history-trace-title'>最近步骤</div>"
        "<div class='history-scroll-area'>"
        "<table class='trace-table compact'><thead><tr><th>步骤</th><th>工具</th><th>摘要</th></tr></thead>"
        f"<tbody>{table_html}</tbody></table>"
        "</div>"
        "</div>"
        "<div class='history-trace-card'>"
        "<div class='history-trace-title'>附加诊断</div>"
        "<div class='history-scroll-area'>"
        "<table class='trace-table compact'><thead><tr><th>项目</th><th colspan='2'>内容</th></tr></thead>"
        f"<tbody>{extra_table}</tbody></table>"
        "</div>"
        "</div>"
        "</div>"
        "</section>"
    )


def empty_history_outputs() -> tuple[str, str, list[tuple[str, str]], str, str | None, str | None, str | None]:
    overview = (
        "<section class='results-overview'>"
        "<div class='section-heading'>历史运行总览</div>"
        "<div class='empty-panel'>当前还没有可浏览的历史运行记录。</div>"
        "</section>"
    )
    report = "## 历史报告\n\n当前没有可预览的历史报告。"
    diagnostics = (
        "<section class='trace-workbench'>"
        "<div class='section-heading'>历史诊断与轨迹</div>"
        "<div class='empty-panel'>请先运行一次分析任务，或点击“刷新历史记录”。</div>"
        "</section>"
    )
    return overview, report, [], diagnostics, None, None, None


def load_history_record(
    run_dir_value: str | None,
    *,
    outputs_root: str | Path = "outputs",
) -> tuple[str, str, list[tuple[str, str]], str, str | None, str | None, str | None]:
    if not run_dir_value:
        return empty_history_outputs()

    selected_path = Path(run_dir_value)
    if not selected_path.is_absolute():
        selected_path = (_resolve_outputs_root(outputs_root).parent / selected_path).resolve()
    if not selected_path.exists():
        return empty_history_outputs()

    entry = _build_history_entry(selected_path)
    report_markdown = "## 历史报告\n\n当前运行未生成可用报告。"
    if entry.report_path and entry.report_path.exists():
        report_markdown = convert_markdown_images_to_gradio_urls(
            entry.report_path.read_text(encoding="utf-8"),
            project_root=PROJECT_ROOT,
            base_dir=entry.report_path.parent,
        )

    gallery_items = [
        (path.as_posix(), f"{path.parent.name} | {path.name}")
        for path in entry.figure_paths
        if path.exists()
    ]
    return (
        _build_history_overview_html(entry),
        report_markdown,
        gallery_items,
        _build_history_trace_html(entry),
        entry.report_path.as_posix() if entry.report_path else None,
        entry.trace_path.as_posix() if entry.trace_path else None,
        entry.cleaned_data_path.as_posix() if entry.cleaned_data_path else None,
    )
