"""History question-answering services built on completed run artifacts."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .config import RuntimeConfig, load_runtime_config
from .llm import build_llm
from .memory import FailureMemoryService, ProjectMemoryService, SuccessMemoryService
from .rag.embeddings import OpenAIEmbeddingClient
from .reporting import _iter_markdown_sections
from .web.history import scan_run_history


@dataclass(frozen=True)
class HistoryKnowledgeRecord:
    run_id: str
    timestamp: str
    review_status: str
    workflow_complete: bool
    detected_domain: str
    quality_mode: str
    methods_used: tuple[str, ...]
    source_data_path: str
    report_summary: str
    review_summary: str
    figure_summaries: tuple[str, ...]
    trace_summary: str
    success_memory_snippets: tuple[str, ...]
    failure_memory_snippets: tuple[str, ...]


@dataclass(frozen=True)
class HistoryKnowledgeSlice:
    slice_id: str
    run_id: str
    timestamp: str
    review_status: str
    workflow_complete: bool
    detected_domain: str
    quality_mode: str
    source_type: str
    title: str
    text: str
    source_path: str = ""
    reference_hint: str = ""


@dataclass(frozen=True)
class HistoryQaRetrievalResult:
    records: tuple[HistoryKnowledgeRecord, ...]
    slices: tuple[HistoryKnowledgeSlice, ...]
    mode: str
    query: str
    selected_run_ids: tuple[str, ...] = ()
    retrieval_strategy: str = "keyword"


@dataclass(frozen=True)
class HistoryQaAnswerResult:
    answer_markdown: str
    retrieval: HistoryQaRetrievalResult
    sources: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def index_completed_runs(
    outputs_root: str | Path = "outputs",
    *,
    memory_base_dir: str | Path | None = None,
) -> tuple[HistoryKnowledgeRecord, ...]:
    entries = scan_run_history(outputs_root)
    completed_entries = [entry for entry in entries if entry.report_path is not None and entry.trace_path is not None]
    records: list[HistoryKnowledgeRecord] = []
    for entry in completed_entries:
        records.append(_build_history_record(entry, memory_base_dir=memory_base_dir))
    return tuple(records)


def retrieve_history_context(
    query: str,
    run_ids: Iterable[str] | None = None,
    *,
    mode: str = "single",
    outputs_root: str | Path = "outputs",
    env_file: str | Path | None = None,
    memory_base_dir: str | Path | None = None,
    top_k: int = 8,
) -> HistoryQaRetrievalResult:
    normalized_mode = _normalize_mode(mode)
    records = index_completed_runs(outputs_root, memory_base_dir=memory_base_dir)
    selected_run_ids = tuple(str(item).strip() for item in (run_ids or ()) if str(item).strip())
    if selected_run_ids:
        records = tuple(record for record in records if record.run_id in selected_run_ids)

    slices = _build_history_slices(records)
    if not slices:
        return HistoryQaRetrievalResult(records=records, slices=(), mode=normalized_mode, query=query, selected_run_ids=selected_run_ids)

    keyword_ranked = _rank_slices_by_keyword(query, slices)
    retrieval_strategy = "keyword"
    final_slices = keyword_ranked[: max(1, int(top_k))]

    embedding_slices = _rank_slices_by_embedding(
        query,
        slices,
        env_file=env_file,
    )
    if embedding_slices:
        retrieval_strategy = "hybrid"
        merged: dict[str, HistoryKnowledgeSlice] = {}
        for item in (*embedding_slices[: max(1, int(top_k))], *keyword_ranked[: max(1, int(top_k))]):
            merged.setdefault(item.slice_id, item)
        final_slices = tuple(merged.values())[: max(1, int(top_k))]

    return HistoryQaRetrievalResult(
        records=records,
        slices=final_slices,
        mode=normalized_mode,
        query=query,
        selected_run_ids=selected_run_ids,
        retrieval_strategy=retrieval_strategy,
    )


def answer_history_question(
    query: str,
    run_ids: Iterable[str] | None = None,
    *,
    mode: str = "single",
    outputs_root: str | Path = "outputs",
    env_file: str | Path | None = None,
    memory_base_dir: str | Path | None = None,
) -> HistoryQaAnswerResult:
    retrieval = retrieve_history_context(
        query,
        run_ids=run_ids,
        mode=mode,
        outputs_root=outputs_root,
        env_file=env_file,
        memory_base_dir=memory_base_dir,
    )
    if not retrieval.records:
        return HistoryQaAnswerResult(
            answer_markdown="## 历史问答结果\n\n当前没有可供问答的已完成历史运行记录。",
            retrieval=retrieval,
            warnings=("No completed runs were indexed.",),
        )
    if not retrieval.slices:
        return HistoryQaAnswerResult(
            answer_markdown="## 历史问答结果\n\n未检索到与问题相关的历史上下文，请尝试缩小运行范围或改写问题。",
            retrieval=retrieval,
            warnings=("No matching history context was retrieved.",),
        )

    warnings: list[str] = []
    try:
        runtime_config: RuntimeConfig = load_runtime_config(env_file=env_file)
        llm = build_llm(runtime_config)
        prompt = _build_history_qa_prompt(query=query, retrieval=retrieval)
        raw_answer = str(llm.invoke([{"role": "user", "content": prompt}])).strip()
        answer_markdown = _normalize_answer(raw_answer, retrieval)
    except Exception as exc:
        warnings.append(f"LLM unavailable for history QA, used deterministic fallback: {exc}")
        answer_markdown = _build_fallback_answer(query=query, retrieval=retrieval)

    sources = tuple(_build_source_line(item) for item in retrieval.slices)
    return HistoryQaAnswerResult(
        answer_markdown=answer_markdown,
        retrieval=retrieval,
        sources=sources,
        warnings=tuple(warnings),
    )


def _normalize_mode(mode: str) -> str:
    normalized = str(mode or "single").strip().lower()
    if normalized not in {"single", "compare"}:
        raise ValueError(f"Unsupported history QA mode: {mode}")
    return normalized


def _build_history_record(entry, *, memory_base_dir: str | Path | None = None) -> HistoryKnowledgeRecord:
    payload = entry.trace_payload
    run_metadata = payload.get("run_metadata", {}) if isinstance(payload, dict) else {}
    telemetry = payload.get("telemetry", {}) if isinstance(payload, dict) else {}
    review_history = payload.get("review_history", []) if isinstance(payload, dict) else []
    step_traces = payload.get("step_traces", []) if isinstance(payload, dict) else []
    report_text = entry.report_path.read_text(encoding="utf-8") if entry.report_path and entry.report_path.exists() else ""
    methods_used = ()
    if isinstance(telemetry, dict):
        methods_used = tuple(str(item).strip() for item in telemetry.get("methods", []) if str(item).strip())
    report_summary = _summarize_report(report_text)
    review_summary = _summarize_reviews(review_history)
    figure_summaries = tuple(_summarize_figure(path, report_text) for path in entry.figure_paths[:6])
    trace_summary = _summarize_trace(step_traces)
    source_data_path = ""
    if isinstance(run_metadata, dict):
        source_data_path = str(run_metadata.get("data_path", "")).strip()
    success_memory_snippets = _load_success_memory_snippets(
        payload.get("success_memory", payload.get("memory", {})) if isinstance(payload, dict) else {},
        memory_scope_key=str(run_metadata.get("memory_scope_key", "") or ""),
        memory_base_dir=memory_base_dir,
    )
    failure_memory_snippets = _load_failure_memory_snippets(
        payload.get("failure_memory", {}) if isinstance(payload, dict) else {},
        memory_scope_key=str(run_metadata.get("memory_scope_key", "") or ""),
        memory_base_dir=memory_base_dir,
    )
    return HistoryKnowledgeRecord(
        run_id=entry.run_dir.name,
        timestamp=entry.timestamp,
        review_status=entry.review_status,
        workflow_complete=entry.workflow_complete,
        detected_domain=entry.domain,
        quality_mode=entry.quality_mode,
        methods_used=methods_used,
        source_data_path=source_data_path,
        report_summary=report_summary,
        review_summary=review_summary,
        figure_summaries=figure_summaries,
        trace_summary=trace_summary,
        success_memory_snippets=success_memory_snippets,
        failure_memory_snippets=failure_memory_snippets,
    )


def _summarize_report(report_text: str) -> str:
    parts: list[str] = []
    for title, body in _iter_markdown_sections(report_text):
        snippet = " ".join(str(body or "").split()).strip()
        if not snippet:
            continue
        parts.append(f"{title}: {snippet[:180]}")
        if len(parts) >= 3:
            break
    return " | ".join(parts) if parts else "暂无报告摘要。"


def _summarize_reviews(review_history: Any) -> str:
    if not isinstance(review_history, list) or not review_history:
        return "暂无文本审稿记录。"
    parts: list[str] = []
    for item in review_history[:3]:
        if not isinstance(item, dict):
            continue
        decision = str(item.get("decision", "unknown")).strip() or "unknown"
        critique = " ".join(str(item.get("critique", "")).split()).strip()
        if critique:
            parts.append(f"{decision}: {critique[:160]}")
    return " | ".join(parts) if parts else "暂无文本审稿记录。"


def _summarize_trace(step_traces: Any) -> str:
    if not isinstance(step_traces, list) or not step_traces:
        return "暂无运行轨迹摘要。"
    parts: list[str] = []
    for item in step_traces[:6]:
        if not isinstance(item, dict):
            continue
        summary = " ".join(str(item.get("summary", "")).split()).strip()
        tool_name = str(item.get("tool_name", "") or item.get("action", "unknown")).strip()
        if summary:
            parts.append(f"{tool_name}: {summary[:140]}")
    return " | ".join(parts) if parts else "暂无运行轨迹摘要。"


def _summarize_figure(path: Path, report_text: str) -> str:
    escaped = re.escape(path.name)
    match = re.search(rf"!\[(?P<alt>[^\]]*)\]\((?P<target>[^)]*{escaped}[^)]*)\)", report_text or "", flags=re.IGNORECASE)
    alt_text = match.group("alt").strip() if match else ""
    if alt_text:
        return f"{path.name}: {alt_text}"
    return f"{path.name}: 图表产物"


def _load_success_memory_snippets(
    memory_payload: Any,
    *,
    memory_scope_key: str,
    memory_base_dir: str | Path | None = None,
) -> tuple[str, ...]:
    if isinstance(memory_payload, dict):
        retrieved = memory_payload.get("retrieved_records", [])
        if isinstance(retrieved, list) and retrieved:
            snippets = []
            for item in retrieved[:4]:
                if not isinstance(item, dict):
                    continue
                excerpt = str(item.get("text_excerpt", "")).strip()
                memory_type = str(item.get("memory_type", "")).strip()
                if excerpt:
                    snippets.append(f"{memory_type}: {excerpt}")
            if snippets:
                return tuple(snippets)
    if not memory_scope_key:
        return ()
    try:
        runtime_config = RuntimeConfig(
            model_id="history-qa-memory",
            api_key="unused",
            base_url="https://unused",
            embedding_model_id="",
            embedding_api_key="",
            embedding_base_url="",
        )
        service = SuccessMemoryService(runtime_config=runtime_config, memory_base_dir=memory_base_dir)
        collection = service._get_collection()
        payload = collection.get(where={"memory_scope_key": memory_scope_key}, include=["documents", "metadatas"])
    except Exception:
        return ()
    documents = payload.get("documents", [[]]) if isinstance(payload, dict) else [[]]
    metadatas = payload.get("metadatas", [[]]) if isinstance(payload, dict) else [[]]
    snippets: list[str] = []
    for index, document in enumerate(documents[0] if documents else []):
        metadata = (metadatas[0] if metadatas else [])[index] if metadatas else {}
        if not isinstance(metadata, dict):
            metadata = {}
        memory_type = str(metadata.get("memory_type", "")).strip() or "memory"
        text = " ".join(str(document or "").split()).strip()
        if text:
            snippets.append(f"{memory_type}: {text[:180]}")
        if len(snippets) >= 4:
            break
    return tuple(snippets)


def _load_failure_memory_snippets(
    memory_payload: Any,
    *,
    memory_scope_key: str,
    memory_base_dir: str | Path | None = None,
) -> tuple[str, ...]:
    if isinstance(memory_payload, dict):
        retrieved = memory_payload.get("retrieved_records", [])
        if isinstance(retrieved, list) and retrieved:
            snippets = []
            for item in retrieved[:4]:
                if not isinstance(item, dict):
                    continue
                excerpt = str(item.get("text_excerpt", "")).strip()
                failure_type = str(item.get("failure_type", "")).strip() or "failure"
                if excerpt:
                    snippets.append(f"{failure_type}: {excerpt}")
            if snippets:
                return tuple(snippets)
    if not memory_scope_key:
        return ()
    try:
        runtime_config = RuntimeConfig(
            model_id="history-qa-failure-memory",
            api_key="unused",
            base_url="https://unused",
            embedding_model_id="",
            embedding_api_key="",
            embedding_base_url="",
        )
        service = FailureMemoryService(runtime_config=runtime_config, memory_base_dir=memory_base_dir)
        collection = service._get_collection()
        payload = collection.get(where={"memory_scope_key": memory_scope_key}, include=["documents", "metadatas"])
    except Exception:
        return ()
    documents = payload.get("documents", [[]]) if isinstance(payload, dict) else [[]]
    metadatas = payload.get("metadatas", [[]]) if isinstance(payload, dict) else [[]]
    snippets: list[str] = []
    for index, document in enumerate(documents[0] if documents else []):
        metadata = (metadatas[0] if metadatas else [])[index] if metadatas else {}
        if not isinstance(metadata, dict):
            metadata = {}
        failure_type = str(metadata.get("failure_type", "")).strip() or "failure"
        text = " ".join(str(document or "").split()).strip()
        if text:
            snippets.append(f"{failure_type}: {text[:180]}")
        if len(snippets) >= 4:
            break
    return tuple(snippets)


def _build_history_slices(records: Iterable[HistoryKnowledgeRecord]) -> tuple[HistoryKnowledgeSlice, ...]:
    slices: list[HistoryKnowledgeSlice] = []
    for record in records:
        slices.append(
            HistoryKnowledgeSlice(
                slice_id=f"{record.run_id}:report",
                run_id=record.run_id,
                timestamp=record.timestamp,
                review_status=record.review_status,
                workflow_complete=record.workflow_complete,
                detected_domain=record.detected_domain,
                quality_mode=record.quality_mode,
                source_type="report",
                title="报告摘要",
                text=record.report_summary,
            )
        )
        slices.append(
            HistoryKnowledgeSlice(
                slice_id=f"{record.run_id}:review",
                run_id=record.run_id,
                timestamp=record.timestamp,
                review_status=record.review_status,
                workflow_complete=record.workflow_complete,
                detected_domain=record.detected_domain,
                quality_mode=record.quality_mode,
                source_type="review",
                title="审稿摘要",
                text=record.review_summary,
            )
        )
        slices.append(
            HistoryKnowledgeSlice(
                slice_id=f"{record.run_id}:trace",
                run_id=record.run_id,
                timestamp=record.timestamp,
                review_status=record.review_status,
                workflow_complete=record.workflow_complete,
                detected_domain=record.detected_domain,
                quality_mode=record.quality_mode,
                source_type="trace",
                title="轨迹摘要",
                text=record.trace_summary,
            )
        )
        for index, summary in enumerate(record.figure_summaries, start=1):
            slices.append(
                HistoryKnowledgeSlice(
                    slice_id=f"{record.run_id}:figure:{index}",
                    run_id=record.run_id,
                    timestamp=record.timestamp,
                    review_status=record.review_status,
                    workflow_complete=record.workflow_complete,
                    detected_domain=record.detected_domain,
                    quality_mode=record.quality_mode,
                    source_type="figure",
                    title=f"图表 {index}",
                    text=summary,
                )
            )
        for index, snippet in enumerate(record.success_memory_snippets, start=1):
            slices.append(
                HistoryKnowledgeSlice(
                    slice_id=f"{record.run_id}:success_memory:{index}",
                    run_id=record.run_id,
                    timestamp=record.timestamp,
                    review_status=record.review_status,
                    workflow_complete=record.workflow_complete,
                    detected_domain=record.detected_domain,
                    quality_mode=record.quality_mode,
                    source_type="success_memory",
                    title=f"项目记忆 {index}",
                    text=snippet,
                )
            )
        for index, snippet in enumerate(record.failure_memory_snippets, start=1):
            slices.append(
                HistoryKnowledgeSlice(
                    slice_id=f"{record.run_id}:failure_memory:{index}",
                    run_id=record.run_id,
                    timestamp=record.timestamp,
                    review_status=record.review_status,
                    workflow_complete=record.workflow_complete,
                    detected_domain=record.detected_domain,
                    quality_mode=record.quality_mode,
                    source_type="failure_memory",
                    title=f"失败教训 {index}",
                    text=snippet,
                )
            )
    return tuple(slices)


def _rank_slices_by_keyword(query: str, slices: tuple[HistoryKnowledgeSlice, ...]) -> tuple[HistoryKnowledgeSlice, ...]:
    tokens = _tokenize(query)
    if not tokens:
        return slices
    scored: list[tuple[float, HistoryKnowledgeSlice]] = []
    for item in slices:
        haystack = " ".join(
            [
                item.run_id,
                item.detected_domain,
                item.title,
                item.text,
                item.review_status,
                item.quality_mode,
            ]
        ).lower()
        score = sum(haystack.count(token) for token in tokens)
        if score <= 0:
            continue
        if item.review_status == "accepted":
            score += 0.5
        if item.workflow_complete:
            score += 0.25
        scored.append((score, item))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return tuple(item for _, item in scored) or slices


def _rank_slices_by_embedding(
    query: str,
    slices: tuple[HistoryKnowledgeSlice, ...],
    *,
    env_file: str | Path | None = None,
) -> tuple[HistoryKnowledgeSlice, ...]:
    try:
        runtime_config = load_runtime_config(env_file=env_file)
    except Exception:
        return ()
    if not runtime_config.embedding_configured:
        return ()
    try:
        client = OpenAIEmbeddingClient(
            model_id=runtime_config.embedding_model_id or "",
            api_key=runtime_config.embedding_api_key or "",
            base_url=runtime_config.embedding_base_url or "",
            timeout=runtime_config.embedding_timeout,
        )
        texts = [query, *[item.text for item in slices]]
        embeddings = client.embed_texts(texts)
    except Exception:
        return ()
    if len(embeddings) != len(texts):
        return ()
    query_embedding = embeddings[0]
    scored: list[tuple[float, HistoryKnowledgeSlice]] = []
    for slice_item, embedding in zip(slices, embeddings[1:]):
        score = _cosine_similarity(query_embedding, embedding)
        if score <= 0:
            continue
        scored.append((score, slice_item))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return tuple(item for _, item in scored)


def _tokenize(text: str) -> list[str]:
    normalized = " ".join(str(text or "").split()).strip().lower()
    if not normalized:
        return []
    return re.findall(r"[a-z0-9_\-/+]+|[\u4e00-\u9fff]{2,}", normalized)


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm <= 0 or right_norm <= 0:
        return 0.0
    return float(dot / (left_norm * right_norm))


def _build_history_qa_prompt(*, query: str, retrieval: HistoryQaRetrievalResult) -> str:
    record_lines = []
    for record in retrieval.records[:12]:
        methods = ", ".join(record.methods_used) if record.methods_used else "unknown"
        record_lines.append(
            f"- run_id={record.run_id} | time={record.timestamp} | review_status={record.review_status} | "
            f"workflow_complete={record.workflow_complete} | domain={record.detected_domain} | "
            f"quality={record.quality_mode} | methods={methods}"
        )
    slice_lines = []
    for item in retrieval.slices:
        slice_lines.append(
            f"- [{item.run_id} | {item.source_type} | review_status={item.review_status}] {item.title}: {item.text}"
        )
    mode_hint = "聚焦单次历史分析解释" if retrieval.mode == "single" else "聚焦多次历史运行对比"
    return (
        "你是一个历史分析问答助手，只能基于给定的历史运行材料回答问题。\n"
        "不要编造未提供的分析结论，不要把项目记忆当作事实证据。\n"
        "如果引用未通过审稿的运行，必须明确写出其 review_status。\n"
        "回答最后必须包含“来源”小节，并显式列出涉及的 run_id。\n\n"
        f"问答模式：{retrieval.mode}（{mode_hint}）\n"
        f"用户问题：{query}\n\n"
        "候选运行：\n"
        f"{chr(10).join(record_lines)}\n\n"
        "检索到的上下文：\n"
        f"{chr(10).join(slice_lines)}\n"
    )


def _normalize_answer(raw_answer: str, retrieval: HistoryQaRetrievalResult) -> str:
    answer = raw_answer.strip() or _build_fallback_answer(query=retrieval.query, retrieval=retrieval)
    if "来源" not in answer:
        source_lines = "\n".join(f"- {item.run_id}（{item.source_type}，review_status={item.review_status}）" for item in retrieval.slices)
        answer = answer.rstrip() + "\n\n## 来源\n" + source_lines
    return answer


def _build_fallback_answer(*, query: str, retrieval: HistoryQaRetrievalResult) -> str:
    lines = ["## 历史问答结果", "", f"问题：{query}", ""]
    if retrieval.mode == "compare":
        lines.append("已基于多次历史运行整理对比信息：")
    else:
        lines.append("已基于历史运行整理相关信息：")
    for item in retrieval.slices[:6]:
        lines.append(
            f"- `{item.run_id}` | `{item.source_type}` | `review_status={item.review_status}`：{item.text}"
        )
    lines.extend(["", "## 来源"])
    seen: set[str] = set()
    for item in retrieval.slices:
        key = f"{item.run_id}|{item.source_type}|{item.review_status}"
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"- {item.run_id}（{item.source_type}，review_status={item.review_status}）")
    return "\n".join(lines)


def _build_source_line(item: HistoryKnowledgeSlice) -> str:
    return f"{item.run_id} | {item.source_type} | review_status={item.review_status} | {item.title}"
