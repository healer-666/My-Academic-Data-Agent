"""View-model helpers for the Gradio web demo."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

from ..agent_runner import AgentStepTrace, AnalysisRunResult


def default_max_reviews_for_quality(quality_mode: str) -> int:
    return {"draft": 0, "standard": 1, "publication": 2}.get(str(quality_mode).strip().lower(), 1)


def build_session_id(session_label: str | None = None) -> str:
    import uuid

    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(session_label or "").strip()).strip("-")
    return f"{(normalized[:32] or 'session')}-{uuid.uuid4().hex[:8]}"


def _escape(value: object) -> str:
    return html.escape(str(value))


def format_duration(duration_ms: int) -> str:
    return f"{max(0, int(duration_ms)) / 1000:.2f}s"


def quality_mode_label(quality_mode: str) -> str:
    return {
        "draft": "初稿 draft",
        "standard": "标准 standard",
        "publication": "高级 publication",
    }.get(quality_mode, quality_mode or "未知")


def latency_mode_label(latency_mode: str) -> str:
    return {
        "auto": "自适应 auto",
        "quality": "质量优先 quality",
        "fast": "极速 fast",
    }.get(latency_mode, latency_mode or "未知")


def review_status_label(status: str) -> str:
    return {
        "skipped": "已跳过",
        "accepted": "已通过",
        "rejected": "已拒绝",
        "max_reviews_reached": "达到最大返修轮次",
    }.get(status, status or "未知")


def review_decision_label(decision: str) -> str:
    return {"Accept": "通过", "Reject": "拒绝"}.get(decision, decision or "未知")


def vision_review_status_label(status: str) -> str:
    return {
        "completed": "已完成",
        "skipped": "已跳过",
        "unavailable": "不可用",
        "failed": "失败",
    }.get(status, status or "未知")


def ingestion_status_label(status: str) -> str:
    return {
        "not_needed": "无需解析",
        "completed": "已完成",
        "failed": "失败",
    }.get(status, status or "未知")


def input_kind_label(input_kind: str) -> str:
    return {"tabular": "结构化表格", "pdf": "PDF 文档"}.get(input_kind, input_kind or "未知")


def workflow_status_label(workflow_complete: bool) -> str:
    return "已完成" if workflow_complete else "未完成"


def rag_status_label(status: str) -> str:
    return {
        "disabled": "已关闭",
        "skipped": "已跳过",
        "retrieved": "已命中",
        "no_matches": "无命中",
        "empty": "知识库为空",
        "failed": "失败",
    }.get(status, status or "未知")


def format_event_line(event_type: str, payload: dict[str, object]) -> str:
    if event_type == "config_loading":
        return "[1/8] 正在加载运行配置..."
    if event_type == "config_loaded":
        model_id = payload.get("model_id", "unknown")
        tavily = "已配置" if payload.get("tavily_configured") else "未配置"
        embedding = "已配置" if payload.get("embedding_configured") else "未配置"
        vision = "已配置" if payload.get("vision_configured") else "未配置"
        latency_mode = latency_mode_label(str(payload.get("latency_mode", "auto")))
        return f"模型：{model_id} | Tavily：{tavily} | Embedding：{embedding} | 视觉审稿：{vision} | 延迟模式：{latency_mode}"
    if event_type == "run_directory_created":
        return f"已创建运行目录：{payload.get('run_dir', '')}"
    if event_type == "document_ingestion_started":
        return f"开始文档解析：input_kind={payload.get('input_kind', 'unknown')}"
    if event_type == "document_ingestion_completed":
        return f"文档解析完成 | status={payload.get('status', 'unknown')} | {payload.get('summary', '')}"
    if event_type == "document_ingestion_skipped":
        return "文档解析已跳过：当前输入已是结构化表格。"
    if event_type == "data_context_ready":
        shape = payload.get("shape", ("?", "?"))
        return f"数据上下文已准备：{shape[0]} 行 x {shape[1]} 列"
    if event_type == "knowledge_indexing_started":
        return f"RAG 正在写入知识文件：{payload.get('file_count', 0)} 个"
    if event_type == "knowledge_indexing_completed":
        return f"RAG 索引完成 | status={payload.get('status', 'unknown')} | indexed={payload.get('indexed_count', 0)}"
    if event_type == "knowledge_indexing_skipped":
        return f"RAG 索引跳过：{payload.get('reason', '')}"
    if event_type == "knowledge_structured_chunking_completed":
        return f"Structured chunking 完成 | chunks={payload.get('chunk_count', 0)} | enabled={payload.get('structured_chunking_enabled', False)}"
    if event_type == "knowledge_table_candidates_prepared":
        return f"PDF 表格候选已准备 | count={payload.get('table_candidate_count', 0)} | selected={payload.get('selected_table_id', '')}"
    if event_type == "knowledge_query_built":
        return "RAG 检索 query 已生成（dense + keyword）"
    if event_type == "knowledge_dense_retrieval_completed":
        return f"Dense 检索完成 | matches={payload.get('match_count', 0)}"
    if event_type == "knowledge_keyword_retrieval_completed":
        return f"Keyword 检索完成 | matches={payload.get('match_count', 0)}"
    if event_type == "knowledge_rerank_completed":
        return f"RAG 重排完成 | matches={payload.get('match_count', 0)} | strategy={payload.get('retrieval_strategy', 'unknown')}"
    if event_type == "knowledge_retrieval_started":
        return "开始检索本地知识库..."
    if event_type == "knowledge_retrieval_completed":
        return f"RAG 检索完成 | status={payload.get('status', 'unknown')} | matches={payload.get('match_count', 0)}"
    if event_type == "knowledge_retrieval_skipped":
        return f"RAG 检索跳过：{payload.get('reason', '')}"
    if event_type == "memory_retrieval_started":
        return f"开始回忆 Project Memory | scope={payload.get('scope_key', '')}"
    if event_type == "memory_retrieval_completed":
        return f"Project Memory 命中完成 | status={payload.get('status', 'unknown')} | matches={payload.get('match_count', 0)}"
    if event_type == "memory_retrieval_skipped":
        return f"Project Memory 跳过：{payload.get('reason', '')}"
    if event_type == "memory_writeback_started":
        return f"开始写回 Project Memory | scope={payload.get('scope_key', '')}"
    if event_type == "memory_writeback_completed":
        return f"Project Memory 写回完成 | status={payload.get('status', 'unknown')} | written={payload.get('written_count', 0)}"
    if event_type == "memory_writeback_skipped":
        return f"Project Memory 写回跳过：{payload.get('reason', payload.get('status', ''))}"
    if event_type == "tool_registry_ready":
        tools = ", ".join(payload.get("tools", [])) if isinstance(payload.get("tools"), list) else ""
        return f"工具已就绪：{tools} | fast_path={payload.get('fast_path_enabled', False)} | max_steps={payload.get('effective_max_steps', '?')}"
    if event_type == "analysis_started":
        return f"分析开始 | round={payload.get('analysis_round', '?')} | max_steps={payload.get('max_steps', '?')}"
    if event_type == "step_started":
        return f"Step {payload.get('step_index', '?')}/{payload.get('max_steps', '?')}：正在思考..."
    if event_type == "tool_call_started":
        return f"调用工具：{payload.get('tool_name', 'UnknownTool')} | {payload.get('decision', '')}"
    if event_type == "tool_call_completed":
        preview = str(payload.get("observation_preview", "")).strip()
        base = (
            f"工具完成：{payload.get('tool_name', 'UnknownTool')} | "
            f"status={payload.get('tool_status', 'unknown')} | "
            f"LLM={payload.get('llm_duration_ms', 0)} ms | Tool={payload.get('tool_duration_ms', 0)} ms"
        )
        return f"{base}\n{preview}" if preview else base
    if event_type == "step_parse_error":
        return f"协议解析警告：{payload.get('message', '')}"
    if event_type == "report_persisting":
        return "正在保存报告和 trace..."
    if event_type == "report_saved":
        return f"报告已保存：{payload.get('report_path', '')}"
    if event_type == "artifact_validation_completed":
        return "产物校验通过" if payload.get("workflow_complete") else "产物校验未通过"
    if event_type == "analysis_finished":
        return "分析完成，最终报告已生成。"
    if event_type == "analysis_max_steps":
        return "达到最大步数，已返回兜底报告。"
    if event_type == "vision_review_started":
        return f"视觉审稿开始 | round={payload.get('review_round', '?')}"
    if event_type == "vision_review_completed":
        return f"视觉审稿完成 | status={payload.get('status', 'unknown')} | decision={payload.get('decision', 'unknown')}"
    if event_type == "vision_review_skipped":
        return f"视觉审稿跳过：{payload.get('reason', '')}"
    if event_type == "review_started":
        return f"文本审稿开始 | round={payload.get('review_round', '?')}"
    if event_type == "review_rejected":
        return f"Reviewer 拒绝：{payload.get('critique', '')}"
    if event_type == "review_accepted":
        return "Reviewer 通过：当前报告满足质量要求。"
    if event_type == "review_max_reached":
        return "已达到最大返修轮次，报告未正式通过。"
    return f"{event_type}: {json.dumps(payload, ensure_ascii=False, default=str)}"


def build_status_markdown(status_text: str, level: str = "info") -> str:
    title = {
        "info": "运行中",
        "success": "运行完成",
        "warning": "运行提醒",
        "error": "运行失败",
    }.get(level, "运行中")
    description = html.escape(str(status_text or "").strip()).replace("\n", "<br>")
    return (
        f"<section class='status-shell status-{_escape(level)}'>"
        "<div class='status-eyebrow'>Academic Data Agent</div>"
        f"<div class='status-title'>{_escape(title)}</div>"
        f"<div class='status-copy'>{description}</div>"
        "</section>"
    )


def _build_ingestion_focus_block(result: AnalysisRunResult) -> str:
    if result.input_kind != "pdf":
        return (
            "<div class='review-highlight'>"
            "<div class='review-status-pill'>文档解析总览</div>"
            "<div class='review-highlight-body'>当前输入已是结构化表格，无需额外文档解析。</div>"
            "</div>"
        )
    table_shape = f"{result.selected_table_shape[0]} x {result.selected_table_shape[1]}" if result.selected_table_shape else "unknown"
    multi_table = "已启用" if result.pdf_multi_table_mode else "未启用"
    return (
        "<div class='review-highlight'>"
        "<div class='review-status-pill'>文档解析总览</div>"
        f"<div class='review-highlight-body'>输入类型：{_escape(input_kind_label(result.input_kind))}<br>"
        f"状态：{_escape(ingestion_status_label(result.document_ingestion_status))}<br>"
        f"候选表数量：{_escape(result.candidate_table_count)}<br>"
        f"主表 ID：{_escape(result.selected_table_id or 'unknown')}<br>"
        f"主表形状：{_escape(table_shape)}<br>"
        f"PDF 多表综合：{_escape(multi_table)}<br>"
        f"耗时：{_escape(format_duration(result.document_ingestion_duration_ms))}<br>"
        f"{_escape(result.document_ingestion_summary or '暂无文档解析摘要。')}</div>"
        "</div>"
    )


def _build_rag_focus_block(result: AnalysisRunResult) -> str:
    rag_sources = ", ".join(result.rag_sources_used) if result.rag_sources_used else "无"
    cited_sources = ", ".join(result.rag_cited_sources) if result.rag_cited_sources else "无"
    uncited_sections = ", ".join(result.rag_uncited_sections_detected) if result.rag_uncited_sections_detected else "无"
    memory_scope = result.memory_scope_key or "N/A"
    return (
        "<div class='review-highlight'>"
        "<div class='review-status-pill'>RAG 检索概览</div>"
        f"<div class='review-highlight-body'>状态：{_escape(rag_status_label(result.rag_status))}<br>"
        f"命中数：{_escape(result.rag_match_count)}<br>"
        f"策略：{_escape(result.rag_retrieval_strategy)}<br>"
        f"PDF 表格候选：{_escape(result.rag_table_candidate_count)}<br>"
        f"Chunk 类型：{_escape(', '.join(result.rag_final_chunk_kinds) if result.rag_final_chunk_kinds else 'none')}<br>"
        f"来源：{_escape(rag_sources)}<br>"
        f"引用数：{_escape(result.rag_citation_count)}<br>"
        f"已引用来源：{_escape(cited_sources)}<br>"
        f"证据覆盖：{_escape(result.rag_evidence_coverage_status)}<br>"
        f"未归因段落：{_escape(uncited_sections)}</div>"
        "</div>"
        "<div class='review-highlight'>"
        "<div class='review-status-pill'>Project Memory</div>"
        f"<div class='review-highlight-body'>启用：{_escape(result.memory_enabled)}<br>"
        f"scope：{_escape(memory_scope)}<br>"
        f"命中数：{_escape(result.memory_match_count)}<br>"
        f"写回状态：{_escape(result.memory_writeback_status)}<br>"
        f"写入条数：{_escape(result.memory_written_count)}</div>"
        "</div>"
    )


def build_overview_html(result: AnalysisRunResult) -> str:
    cards = [
        ("输入类型", input_kind_label(result.input_kind)),
        ("识别领域", result.detected_domain or "unknown"),
        ("质量档位", quality_mode_label(result.quality_mode)),
        ("延迟模式", latency_mode_label(result.latency_mode)),
        ("RAG", rag_status_label(result.rag_status)),
        ("Memory", "启用" if result.memory_enabled else "关闭"),
        ("检索策略", result.rag_retrieval_strategy),
        ("文本审稿", review_status_label(result.review_status)),
        ("视觉审稿", vision_review_status_label(result.vision_review_status)),
        ("总耗时", format_duration(result.total_duration_ms)),
        ("工作流", workflow_status_label(result.workflow_complete)),
    ]
    card_html = "".join(
        "<article class='metric-card'>"
        f"<div class='metric-label'>{_escape(label)}</div>"
        f"<div class='metric-value'>{_escape(value)}</div>"
        "</article>"
        for label, value in cards
    )
    return (
        "<section class='results-overview'>"
        "<div class='section-heading'>运行总览</div>"
        "<div class='section-subtitle'>这里汇总当前任务的输入类型、质量模式、RAG / Memory 状态、审稿结果和关键耗时。</div>"
        f"{_build_ingestion_focus_block(result)}"
        f"{_build_rag_focus_block(result)}"
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
                "critique": str(payload.get("critique", "")).strip() or "暂无审稿意见摘要。",
            }
        )
    return history


def build_summary_markdown(result: AnalysisRunResult) -> str:
    methods = ", ".join(result.methods_used) if result.methods_used else "unknown"
    tools = ", ".join(result.tools_used) if result.tools_used else "unknown"
    rag_sources = ", ".join(result.rag_sources_used) if result.rag_sources_used else "无"
    cited_sources = ", ".join(result.rag_cited_sources) if result.rag_cited_sources else "无"
    uncited_sections = ", ".join(result.rag_uncited_sections_detected) if result.rag_uncited_sections_detected else "无"
    warnings = "\n".join(f"- {item}" for item in result.workflow_warnings) if result.workflow_warnings else "- 无"
    ingestion_log = result.document_ingestion_log_path.as_posix() if result.document_ingestion_log_path else "无"
    pdf_mode = "启用" if result.pdf_multi_table_mode else "未启用"
    memory_scope = result.memory_scope_key or "N/A"
    return (
        "## 运行摘要\n\n"
        f"- 输入类型：`{input_kind_label(result.input_kind)}`\n"
        f"- 识别领域：`{result.detected_domain}`\n"
        f"- 方法：`{methods}`\n"
        f"- 工具：`{tools}`\n"
        f"- 报告质量：`{quality_mode_label(result.quality_mode)} ({result.quality_mode})`\n"
        f"- 延迟模式：`{latency_mode_label(result.latency_mode)} ({result.latency_mode})`\n"
        f"- 文档解析状态：`{ingestion_status_label(result.document_ingestion_status)}`\n"
        f"- 文档解析摘要：`{result.document_ingestion_summary or '无'}`\n"
        f"- 文档解析日志：`{ingestion_log}`\n"
        f"- PDF 多表模式：`{pdf_mode}`\n"
        f"- 候选表数量：`{result.candidate_table_count}`\n"
        f"- 主表 ID：`{result.selected_table_id or 'N/A'}`\n"
        f"- 主表形状：`{result.selected_table_shape or 'N/A'}`\n"
        f"- RAG：`{rag_status_label(result.rag_status)} ({result.rag_status})`\n"
        f"- RAG 命中数：`{result.rag_match_count}`\n"
        f"- Dense 命中数：`{result.rag_dense_match_count}`\n"
        f"- Keyword 命中数：`{result.rag_keyword_match_count}`\n"
        f"- 检索策略：`{result.rag_retrieval_strategy}`\n"
        f"- PDF 表格候选：`{result.rag_table_candidate_count}`\n"
        f"- 最终 Chunk 类型：`{', '.join(result.rag_final_chunk_kinds) if result.rag_final_chunk_kinds else 'none'}`\n"
        f"- 命中主表证据：`{result.rag_selected_table_hit}`\n"
        f"- RAG 来源：`{rag_sources}`\n"
        f"- 引用数量：`{result.rag_citation_count}`\n"
        f"- 已引用来源：`{cited_sources}`\n"
        f"- 证据覆盖状态：`{result.rag_evidence_coverage_status}`\n"
        f"- 未归因段落：`{uncited_sections}`\n"
        f"- Memory 启用：`{result.memory_enabled}`\n"
        f"- Memory scope：`{memory_scope}`\n"
        f"- Memory 命中数：`{result.memory_match_count}`\n"
        f"- Memory 写回状态：`{result.memory_writeback_status}`\n"
        f"- Memory 写入数：`{result.memory_written_count}`\n"
        f"- 视觉审稿：`{vision_review_status_label(result.vision_review_status)} ({result.vision_review_mode})`\n"
        f"- 文本审稿：`{review_status_label(result.review_status)}`\n"
        f"- 返修轮次：`{result.review_rounds_used}`\n"
        f"- 工作流完成：`{result.workflow_complete}`\n"
        f"- 运行目录：`{result.run_dir.as_posix()}`\n"
        f"- 清洗数据：`{result.cleaned_data_path.as_posix()}`\n"
        f"- Trace：`{result.trace_path.as_posix()}`\n\n"
        "### 耗时拆解\n"
        f"- 总耗时：`{format_duration(result.total_duration_ms)}`\n"
        f"- 文档解析：`{format_duration(result.document_ingestion_duration_ms)}`\n"
        f"- LLM：`{format_duration(result.llm_duration_ms)}`\n"
        f"- 工具调用：`{format_duration(result.tool_duration_ms)}`\n"
        f"- 文本审稿：`{format_duration(result.review_duration_ms)}`\n"
        f"- 视觉审稿：`{format_duration(result.vision_review_duration_ms)}`\n"
        f"- Tavily：`{format_duration(result.timing_breakdown.get('tavily_duration_ms', 0))}`\n"
        f"- Memory：`{format_duration(result.timing_breakdown.get('memory_retrieval_duration_ms', 0) + result.timing_breakdown.get('memory_writeback_duration_ms', 0))}`\n\n"
        "### 工作流告警\n"
        f"{warnings}"
    )


def build_review_markdown(result: AnalysisRunResult) -> str:
    latest_critique = result.review_critique or "暂无文本审稿摘要。"
    visual_summary = result.vision_review_summary or "暂无视觉审稿摘要。"
    history = _load_review_history(result)
    history_cards = "".join(
        "<article class='review-card'>"
        f"<div class='review-card-head'>第 {_escape(item['round_index'])} 轮 | {_escape(item['decision'])}</div>"
        f"<div class='review-card-body'>{_escape(item['critique'])}</div>"
        "</article>"
        for item in history
    ) or "<div class='empty-panel'>暂无可展示的审稿历史。</div>"
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
        "<div class='section-heading secondary'>返修记录</div>"
        f"<div class='review-history'>{history_cards}</div>"
        "</section>"
    )


def _tool_label(tool_name: str | None) -> str:
    if tool_name == "PythonInterpreterTool":
        return "本地 Python 分析"
    if tool_name == "TavilySearchTool":
        return "在线知识检索"
    return tool_name or "结束"


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
            "<tr>"
            f"<td>{_escape(trace.step_index)}</td>"
            f"<td>{_escape(_tool_label(trace.tool_name))}</td>"
            f"<td><span class='{_escape(status_class)}'>{_escape(trace.tool_status)}</span></td>"
            f"<td>{_escape(trace.decision or trace.action)}</td>"
            f"<td>{_escape(f'LLM={trace.llm_duration_ms} ms | Tool={trace.tool_duration_ms} ms')}</td>"
            f"<td>{_escape(trace.summary or _trace_observation(trace) or '无')}</td>"
            "</tr>"
        )
    body = "".join(rows) or "<tr><td colspan='6'><div class='empty-panel'>暂无可展示的执行轨迹。</div></td></tr>"
    pdf_mode = "启用" if result.pdf_multi_table_mode else "未启用"
    rag_sources = ", ".join(result.rag_sources_used) if result.rag_sources_used else "无"
    cited_sources = ", ".join(result.rag_cited_sources) if result.rag_cited_sources else "无"
    uncited_sections = ", ".join(result.rag_uncited_sections_detected) if result.rag_uncited_sections_detected else "无"
    memory_scope = result.memory_scope_key or "N/A"
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
    rag_block = (
        "<div class='empty-panel'>"
        f"RAG：{_escape(rag_status_label(result.rag_status))} | 命中数：{_escape(result.rag_match_count)} | 策略：{_escape(result.rag_retrieval_strategy)}<br>"
        f"Dense：{_escape(result.rag_dense_match_count)} | Keyword：{_escape(result.rag_keyword_match_count)} | 主表命中：{_escape(result.rag_selected_table_hit)}<br>"
        f"Chunk 类型：{_escape(', '.join(result.rag_final_chunk_kinds) if result.rag_final_chunk_kinds else 'none')}<br>"
        f"来源：{_escape(rag_sources)}<br>"
        f"引用数：{_escape(result.rag_citation_count)} | 覆盖状态：{_escape(result.rag_evidence_coverage_status)}<br>"
        f"已引用来源：{_escape(cited_sources)}<br>"
        f"未归因段落：{_escape(uncited_sections)}"
        "</div>"
    )
    memory_block = (
        "<div class='empty-panel'>"
        f"Memory：{_escape('启用' if result.memory_enabled else '关闭')} | "
        f"scope：{_escape(memory_scope)} | 命中数：{_escape(result.memory_match_count)}<br>"
        f"写回状态：{_escape(result.memory_writeback_status)} | 写入条数：{_escape(result.memory_written_count)}"
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
        f"{rag_block}"
        f"{memory_block}"
        f"{visual_block}"
        "<table class='trace-table'>"
        "<thead><tr><th>步骤</th><th>工具</th><th>状态</th><th>决策</th><th>耗时</th><th>摘要</th></tr></thead>"
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
