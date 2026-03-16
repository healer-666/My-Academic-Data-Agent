"""View-model helpers for the Gradio web demo."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

from ..agent_runner import AgentStepTrace, AnalysisRunResult


def default_max_reviews_for_quality(quality_mode: str) -> int:
    mapping = {
        "draft": 0,
        "standard": 1,
        "publication": 2,
    }
    return mapping.get(str(quality_mode).strip().lower(), 1)


def build_session_id(session_label: str | None = None) -> str:
    import uuid

    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(session_label or "").strip()).strip("-")
    prefix = normalized[:32] if normalized else "session"
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _escape(value: object) -> str:
    return html.escape(str(value))


def format_duration(duration_ms: int) -> str:
    return f"{duration_ms / 1000:.2f}s"


def quality_mode_label(quality_mode: str) -> str:
    return {
        "draft": "初稿",
        "standard": "标准",
        "publication": "高级",
    }.get(quality_mode, quality_mode or "未知")


def latency_mode_label(latency_mode: str) -> str:
    return {
        "auto": "自适应",
        "quality": "质量优先",
        "fast": "极速",
    }.get(latency_mode, latency_mode or "未知")


def review_status_label(status: str) -> str:
    return {
        "skipped": "已跳过",
        "accepted": "已通过",
        "rejected": "已拒绝",
        "max_reviews_reached": "达到最大返修次数",
    }.get(status, status or "未知")


def review_decision_label(decision: str) -> str:
    return {
        "Accept": "通过",
        "Reject": "拒绝",
    }.get(decision, decision or "未知")


def vision_review_status_label(status: str) -> str:
    return {
        "completed": "已完成",
        "skipped": "已跳过",
        "unavailable": "未配置",
        "failed": "执行失败",
    }.get(status, status or "未知")


def ingestion_status_label(status: str) -> str:
    return {
        "not_needed": "无需解析",
        "completed": "解析完成",
        "failed": "解析失败",
    }.get(status, status or "未知")


def input_kind_label(input_kind: str) -> str:
    return {
        "tabular": "结构化表格",
        "pdf": "PDF 文献",
    }.get(input_kind, input_kind or "未知")


def workflow_status_label(workflow_complete: bool) -> str:
    return "已完成" if workflow_complete else "未完成"


def format_event_line(event_type: str, payload: dict[str, object]) -> str:
    if event_type == "config_loading":
        return "[1/8] 正在加载运行配置..."
    if event_type == "config_loaded":
        model_id = payload.get("model_id", "unknown")
        tavily = "已配置" if payload.get("tavily_configured") else "未配置"
        vision = "已配置" if payload.get("vision_configured") else "未配置"
        latency_mode = latency_mode_label(str(payload.get("latency_mode", "auto")))
        return f"模型：{model_id} | Tavily：{tavily} | 视觉审稿：{vision} | 延迟模式：{latency_mode}"
    if event_type == "run_directory_created":
        return f"运行目录已创建：{payload.get('run_dir', '')}"
    if event_type == "document_ingestion_started":
        return f"文档解析已开始，输入类型：{payload.get('input_kind', 'unknown')}"
    if event_type == "document_ingestion_completed":
        return f"文档解析完成 | 状态：{payload.get('status', 'unknown')} | {payload.get('summary', '')}"
    if event_type == "document_ingestion_skipped":
        return "文档解析已跳过：当前输入已经是结构化表格。"
    if event_type == "data_context_ready":
        shape = payload.get("shape", ("?", "?"))
        return f"数据上下文已构建：{shape[0]} 行 x {shape[1]} 列"
    if event_type == "tool_registry_ready":
        tools = ", ".join(payload.get("tools", [])) if isinstance(payload.get("tools"), list) else ""
        return (
            f"工具注册完成：{tools}\n"
            f"快速路径：{payload.get('fast_path_enabled', False)} | "
            f"有效最大步数：{payload.get('effective_max_steps', '?')}"
        )
    if event_type == "analysis_started":
        return f"分析轮次 {payload.get('analysis_round', '?')} 已开始 | 最大步数 = {payload.get('max_steps', '?')}"
    if event_type == "step_started":
        return f"第 {payload.get('step_index', '?')}/{payload.get('max_steps', '?')} 步：正在思考..."
    if event_type == "tool_call_started":
        return f"调用 {payload.get('tool_name', 'UnknownTool')} | {payload.get('decision', '')}"
    if event_type == "tool_call_completed":
        preview = str(payload.get("observation_preview", "")).strip()
        line = (
            f"完成 {payload.get('tool_name', 'UnknownTool')} | "
            f"状态 = {payload.get('tool_status', 'unknown')} | "
            f"LLM = {payload.get('llm_duration_ms', 0)} ms | "
            f"工具 = {payload.get('tool_duration_ms', 0)} ms"
        )
        return f"{line}\n{preview}" if preview else line
    if event_type == "step_parse_error":
        return f"协议解析警告：{payload.get('message', '')}"
    if event_type == "report_persisting":
        return "正在保存 Markdown 报告与运行轨迹..."
    if event_type == "report_saved":
        return f"报告已保存：{payload.get('report_path', '')}"
    if event_type == "artifact_validation_completed":
        return "工件校验通过。" if payload.get("workflow_complete") else "工件校验失败。"
    if event_type == "analysis_finished":
        return "Analyst 已生成候选报告。"
    if event_type == "analysis_max_steps":
        return "Agent 已达到最大控制步数。"
    if event_type == "vision_review_started":
        return f"视觉审稿第 {payload.get('review_round', '?')} 轮已开始。"
    if event_type == "vision_review_completed":
        return (
            f"视觉审稿已完成。状态：{payload.get('status', 'unknown')} | "
            f"结论：{payload.get('decision', 'unknown')}"
        )
    if event_type == "vision_review_skipped":
        return f"视觉审稿已跳过。\n{payload.get('reason', '')}"
    if event_type == "review_started":
        return f"Reviewer 第 {payload.get('review_round', '?')} 轮已开始。"
    if event_type == "review_rejected":
        return f"Reviewer 拒绝了候选报告。\n{payload.get('critique', '')}"
    if event_type == "review_accepted":
        return "Reviewer 已通过当前报告。"
    if event_type == "review_max_reached":
        return "已达到最大返修次数，报告未正式通过审稿。"
    return f"{event_type}: {json.dumps(payload, ensure_ascii=False, default=str)}"


def build_status_markdown(status_text: str, level: str = "info") -> str:
    prefix = {
        "info": "### 当前状态",
        "success": "### 运行完成",
        "warning": "### 运行警告",
        "error": "### 运行失败",
    }.get(level, "### 当前状态")
    return f"{prefix}\n\n{status_text}"


def _build_ingestion_focus_block(result: AnalysisRunResult) -> str:
    if result.input_kind == "pdf":
        table_shape = (
            f"{result.selected_table_shape[0]} x {result.selected_table_shape[1]}"
            if result.selected_table_shape
            else "unknown"
        )
        multi_table = "已启用" if result.pdf_multi_table_mode else "未启用"
        return (
            "<div class='review-highlight'>"
            "<div class='review-status-pill'>文档解析总览</div>"
            f"<div class='review-highlight-body'>输入类型：{_escape(input_kind_label(result.input_kind))}<br>"
            f"解析状态：{_escape(ingestion_status_label(result.document_ingestion_status))}<br>"
            f"候选表数量：{_escape(result.candidate_table_count)}<br>"
            f"主表 ID：{_escape(result.selected_table_id or 'unknown')}<br>"
            f"主表形状：{_escape(table_shape)}<br>"
            f"PDF 多表综合：{_escape(multi_table)}<br>"
            f"文档解析耗时：{_escape(format_duration(result.document_ingestion_duration_ms))}<br>"
            f"{_escape(result.document_ingestion_summary or '暂无文档解析摘要。')}</div>"
            "</div>"
        )
    return (
        "<div class='review-highlight'>"
        "<div class='review-status-pill'>文档解析总览</div>"
        "<div class='review-highlight-body'>输入已是结构化表格，无需文档解析。</div>"
        "</div>"
    )


def build_overview_html(result: AnalysisRunResult) -> str:
    cards = [
        ("输入类型", input_kind_label(result.input_kind)),
        ("识别领域", result.detected_domain or "unknown"),
        ("报告质量", quality_mode_label(result.quality_mode)),
        ("延迟模式", latency_mode_label(result.latency_mode)),
        ("文本审稿", review_status_label(result.review_status)),
        ("视觉审稿", vision_review_status_label(result.vision_review_status)),
        ("总耗时", format_duration(result.total_duration_ms)),
        ("工作流", workflow_status_label(result.workflow_complete)),
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

    return (
        "<section class='results-overview'>"
        "<div class='section-heading'>运行总览</div>"
        "<div class='section-subtitle'>先看文档解析和关键指标，再进入报告、图表与审稿结果。</div>"
        f"{_build_ingestion_focus_block(result)}"
        f"<div class='metric-grid'>{card_html}</div>"
        "</section>"
    )


def _load_review_history(result: AnalysisRunResult) -> list[dict[str, str]]:
    history: list[dict[str, str]] = []
    for index, review_log_path in enumerate(result.review_log_paths, start=1):
        try:
            payload = json.loads(Path(review_log_path).read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        history.append(
            {
                "round_index": str(payload.get("round_index", index)),
                "decision": review_decision_label(str(payload.get("decision", ""))),
                "critique": str(payload.get("critique", "")).strip() or "无具体意见。",
            }
        )
    return history


def build_summary_markdown(result: AnalysisRunResult) -> str:
    methods = ", ".join(result.methods_used) if result.methods_used else "unknown"
    tools = ", ".join(result.tools_used) if result.tools_used else "unknown"
    warnings = "\n".join(f"- {item}" for item in result.workflow_warnings) if result.workflow_warnings else "- 无"
    ingestion_log = result.document_ingestion_log_path.as_posix() if result.document_ingestion_log_path else "无"
    pdf_mode = "启用" if result.pdf_multi_table_mode else "未启用"
    return (
        "## 运行摘要\n\n"
        f"- 输入类型：`{input_kind_label(result.input_kind)}`\n"
        f"- 识别领域：`{result.detected_domain}`\n"
        f"- 使用方法：`{methods}`\n"
        f"- 使用工具：`{tools}`\n"
        f"- 报告质量：`{quality_mode_label(result.quality_mode)} ({result.quality_mode})`\n"
        f"- 延迟模式：`{latency_mode_label(result.latency_mode)} ({result.latency_mode})`\n"
        f"- 文档解析：`{ingestion_status_label(result.document_ingestion_status)}`\n"
        f"- 文档解析摘要：`{result.document_ingestion_summary or '无'}`\n"
        f"- 文档解析日志：`{ingestion_log}`\n"
        f"- PDF 多表综合：`{pdf_mode}`\n"
        f"- 候选表数量：`{result.candidate_table_count}`\n"
        f"- 主表 ID：`{result.selected_table_id or 'N/A'}`\n"
        f"- 主表形状：`{result.selected_table_shape or 'N/A'}`\n"
        f"- 视觉审稿：`{vision_review_status_label(result.vision_review_status)} ({result.vision_review_mode})`\n"
        f"- 文本审稿：`{review_status_label(result.review_status)}`\n"
        f"- 审稿轮次：`{result.review_rounds_used}`\n"
        f"- 工作流完成：`{result.workflow_complete}`\n"
        f"- 运行目录：`{result.run_dir.as_posix()}`\n"
        f"- 清洗数据：`{result.cleaned_data_path.as_posix()}`\n"
        f"- 轨迹文件：`{result.trace_path.as_posix()}`\n\n"
        "### 耗时拆解\n"
        f"- 总耗时：`{format_duration(result.total_duration_ms)}`\n"
        f"- 文档解析耗时：`{format_duration(result.document_ingestion_duration_ms)}`\n"
        f"- LLM 耗时：`{format_duration(result.llm_duration_ms)}`\n"
        f"- 工具耗时：`{format_duration(result.tool_duration_ms)}`\n"
        f"- 文本审稿耗时：`{format_duration(result.review_duration_ms)}`\n"
        f"- 视觉审稿耗时：`{format_duration(result.vision_review_duration_ms)}`\n"
        f"- Tavily 耗时：`{format_duration(result.timing_breakdown.get('tavily_duration_ms', 0))}`\n\n"
        "### 工件告警\n"
        f"{warnings}"
    )


def build_review_markdown(result: AnalysisRunResult) -> str:
    latest_critique = result.review_critique or "暂无文本审稿意见。"
    visual_summary = result.vision_review_summary or "暂无视觉审稿摘要。"
    history = _load_review_history(result)
    history_cards = "".join(
        (
            "<article class='review-card'>"
            f"<div class='review-card-head'>第 {_escape(item['round_index'])} 轮 · {_escape(item['decision'])}</div>"
            f"<div class='review-card-body'>{_escape(item['critique'])}</div>"
            "</article>"
        )
        for item in history
    ) or "<div class='empty-panel'>暂无审稿历史。</div>"
    return (
        "<section class='review-workbench'>"
        "<div class='section-heading'>审稿工作台</div>"
        "<div class='review-highlight'>"
        f"<div class='review-status-pill'>视觉审稿 · {_escape(vision_review_status_label(result.vision_review_status))}</div>"
        f"<div class='review-highlight-body'>{_escape(visual_summary)}</div>"
        "</div>"
        "<div class='review-highlight'>"
        f"<div class='review-status-pill'>文本审稿 · {_escape(review_status_label(result.review_status))}</div>"
        f"<div class='review-highlight-body'>{_escape(latest_critique)}</div>"
        "</div>"
        "<div class='section-heading secondary'>各轮文本审稿记录</div>"
        f"<div class='review-history'>{history_cards}</div>"
        "</section>"
    )


def _tool_label(tool_name: str | None) -> str:
    if tool_name == "PythonInterpreterTool":
        return "本地 Python 分析"
    if tool_name == "TavilySearchTool":
        return "在线知识检索"
    return tool_name or "报告定稿"


def _trace_observation(trace: AgentStepTrace) -> str:
    if trace.observation_preview:
        return trace.observation_preview
    if trace.observation:
        return " ".join(trace.observation.split())[:220]
    return ""


def build_trace_html(result: AnalysisRunResult) -> str:
    rows: list[str] = []
    for trace in result.step_traces:
        status_class = "trace-status ok"
        if trace.parse_error or trace.tool_status == "error":
            status_class = "trace-status error"
        elif trace.tool_status not in {"success", "unknown"}:
            status_class = "trace-status warn"
        rows.append(
            """
            <tr>
              <td>{step}</td>
              <td>{tool}</td>
              <td><span class="{status_class}">{status}</span></td>
              <td>{decision}</td>
              <td>{timing}</td>
              <td>{summary}</td>
            </tr>
            """.format(
                step=_escape(trace.step_index),
                tool=_escape(_tool_label(trace.tool_name)),
                status_class=_escape(status_class),
                status=_escape(trace.tool_status),
                decision=_escape(trace.decision or trace.action),
                timing=_escape(f"LLM={trace.llm_duration_ms} ms | 工具={trace.tool_duration_ms} ms"),
                summary=_escape(trace.summary or _trace_observation(trace) or "无"),
            )
        )
    body = "".join(rows) or "<tr><td colspan='6'><div class='empty-panel'>暂无可展示的执行轨迹。</div></td></tr>"
    pdf_mode = "启用" if result.pdf_multi_table_mode else "未启用"
    document_block = (
        "<div class='empty-panel'>"
        f"文档解析：{_escape(ingestion_status_label(result.document_ingestion_status))} | "
        f"耗时：{_escape(format_duration(result.document_ingestion_duration_ms))}<br>"
        f"候选表数量：{_escape(result.candidate_table_count)} | "
        f"主表 ID：{_escape(result.selected_table_id or 'N/A')} | "
        f"PDF 多表综合：{_escape(pdf_mode)}<br>"
        f"{_escape(result.document_ingestion_summary or '暂无文档解析摘要。')}"
        "</div>"
    )
    visual_block = (
        "<div class='empty-panel'>"
        f"视觉审稿：{_escape(vision_review_status_label(result.vision_review_status))} | "
        f"耗时：{_escape(format_duration(result.vision_review_duration_ms))}<br>"
        f"{_escape(result.vision_review_summary or '暂无视觉审稿摘要。')}"
        "</div>"
    )
    return (
        "<section class='trace-workbench'>"
        "<div class='section-heading'>诊断与轨迹</div>"
        f"{document_block}"
        f"{visual_block}"
        "<table class='trace-table'>"
        "<thead><tr>"
        "<th>步骤</th><th>阶段 / 工具</th><th>状态</th><th>决策</th><th>耗时</th><th>摘要</th>"
        "</tr></thead>"
        f"<tbody>{body}</tbody>"
        "</table>"
        "</section>"
    )


def build_gallery_items(result: AnalysisRunResult) -> list[tuple[str, str]]:
    items: list[tuple[str, str]] = []
    for figure_path in result.telemetry.figures_generated:
        path = Path(figure_path)
        resolved_path = path if path.is_absolute() else path.resolve()
        round_match = re.search(r"review_round_(\d+)", resolved_path.as_posix())
        round_label = f"第 {round_match.group(1)} 轮" if round_match else "图表"
        items.append((resolved_path.as_posix(), f"{round_label} | {resolved_path.name}"))
    return items


def build_download_paths(
    *,
    report_path: str | None = None,
    trace_path: str | None = None,
    bundle_path: str | None = None,
) -> tuple[str | None, str | None, str | None]:
    return report_path, trace_path, bundle_path
