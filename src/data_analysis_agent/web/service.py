"""Backend services for the Gradio web demo."""

from __future__ import annotations

import html
import queue
import shutil
import threading
import traceback
from pathlib import Path
from typing import Generator

from ..agent_runner import AnalysisRunResult, run_analysis
from ..document_ingestion import preview_pdf_tables
from ..reporting import convert_markdown_images_to_gradio_urls
from .viewmodels import (
    build_download_paths,
    build_gallery_items,
    build_overview_html,
    build_review_markdown,
    build_session_id,
    build_status_markdown,
    build_summary_markdown,
    build_trace_html,
    default_max_reviews_for_quality,
    format_event_line,
)


def copy_uploaded_file(uploaded_file: str | Path, *, uploads_root: str | Path, session_id: str) -> Path:
    source = Path(uploaded_file)
    if not source.exists():
        raise FileNotFoundError(f"Uploaded file does not exist: {source}")
    destination_dir = Path(uploads_root) / session_id
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / source.name
    shutil.copy2(source, destination)
    return destination


def copy_uploaded_knowledge_files(
    uploaded_files: str | Path | list[str] | list[Path] | tuple[str | Path, ...] | None,
    *,
    uploads_root: str | Path,
    session_id: str,
) -> tuple[Path, ...]:
    if not uploaded_files:
        return ()
    if isinstance(uploaded_files, (str, Path)):
        file_list = [uploaded_files]
    else:
        file_list = list(uploaded_files)
    copied: list[Path] = []
    destination_dir = Path(uploads_root) / session_id / "knowledge"
    destination_dir.mkdir(parents=True, exist_ok=True)
    for item in file_list:
        source = Path(item)
        if not source.exists():
            raise FileNotFoundError(f"Knowledge file does not exist: {source}")
        destination = destination_dir / source.name
        shutil.copy2(source, destination)
        copied.append(destination)
    return tuple(copied)


def create_run_bundle(run_dir: str | Path) -> Path:
    run_path = Path(run_dir)
    archive_base = run_path.parent / f"{run_path.name}_artifacts"
    archive_path = shutil.make_archive(
        str(archive_base),
        "zip",
        root_dir=run_path.parent,
        base_dir=run_path.name,
    )
    return Path(archive_path)


def _empty_overview(title: str, body: str) -> str:
    return (
        "<section class='results-overview'>"
        f"<div class='section-heading'>{title}</div>"
        f"<div class='empty-panel'>{body}</div>"
        "</section>"
    )


def _error_outputs(message: str, logs: list[str]) -> tuple[object, ...]:
    return (
        build_status_markdown(message, level="error"),
        "\n\n".join(logs),
        _empty_overview("运行总览", "任务在生成结果前失败，请先查看实时日志定位问题。"),
        "## 运行摘要\n\n任务在生成完整结果前失败了。",
        "## 最终报告\n\n尚未生成报告。",
        [],
        "## 审稿结果\n\n由于运行失败，审稿结果不可用。",
        "<section class='trace-workbench'><div class='section-heading'>诊断与轨迹</div><div class='empty-panel'>运行失败，请查看实时日志。</div></section>",
        None,
        None,
        None,
    )


def _empty_preview_outputs(message: str) -> tuple[str, list[tuple[str, str]], str | None, str]:
    summary = (
        "<section class='overview-card'>"
        "<h2 class='section-title'>候选表摘要</h2>"
        f"<p class='section-copy'>{html.escape(message)}</p>"
        "</section>"
    )
    return build_status_markdown(message, level="warning"), [], None, summary


def preview_pdf_candidates(
    uploaded_file: str | None,
    output_dir: str,
    session_label: str,
    max_pdf_pages: float | int,
    max_candidate_tables: float | int,
) -> tuple[str, list[tuple[str, str]], str | None, str]:
    if not uploaded_file:
        return _empty_preview_outputs("请先上传 PDF 文件，然后再预览候选表。")

    source_path = Path(uploaded_file)
    if source_path.suffix.lower() != ".pdf":
        return _empty_preview_outputs("当前文件不是 PDF，无需候选表预览。")

    session_id = build_session_id(f"{session_label or 'pdf-preview'}-preview")
    uploads_root = Path(output_dir) / "web_uploads"
    copied_file = copy_uploaded_file(source_path, uploads_root=uploads_root, session_id=session_id)
    preview = preview_pdf_tables(
        copied_file,
        max_pdf_pages=max(1, int(max_pdf_pages)),
        max_candidate_tables=max(1, int(max_candidate_tables)),
    )

    if not preview.candidate_tables:
        warning_text = "；".join(preview.warnings) if preview.warnings else "当前 PDF 未提取到可用结构化表格。"
        return _empty_preview_outputs(warning_text)

    choices: list[tuple[str, str]] = []
    rows: list[str] = []
    for record in preview.candidate_tables:
        label = (
            f"{record.table_id} | 第 {record.page_number} 页 | "
            f"{record.rows}x{record.cols} | 数值列 {len(record.numeric_columns)}"
        )
        choices.append((label, record.table_id))
        default_badge = " <strong>默认主表</strong>" if record.table_id == preview.default_table_id else ""
        headers = "、".join(record.headers[:6]) if record.headers else "无列头"
        numeric_cols = "、".join(record.numeric_columns[:6]) if record.numeric_columns else "无"
        content_hint = html.escape(record.content_hint or "无")
        rows.append(
            "<tr>"
            f"<td>{html.escape(record.table_id)}</td>"
            f"<td>{record.page_number}</td>"
            f"<td>{record.rows} x {record.cols}</td>"
            f"<td>{html.escape(headers)}</td>"
            f"<td>{html.escape(numeric_cols)}</td>"
            f"<td>{content_hint}</td>"
            f"<td>{default_badge or '候选表'}</td>"
            "</tr>"
        )

    warnings_html = ""
    if preview.warnings:
        warnings_html = (
            "<div class='empty-panel'>"
            "<strong>预览提示：</strong>"
            f"{html.escape('；'.join(preview.warnings))}"
            "</div>"
        )
    background_excerpt = preview.background_literature_context[:320].strip()
    background_html = ""
    if background_excerpt:
        background_html = (
            "<div class='empty-panel'>"
            "<strong>正文背景摘录：</strong><br>"
            f"{html.escape(background_excerpt)}"
            "</div>"
        )
    summary = (
        "<section class='results-overview'>"
        "<div class='section-heading'>候选表摘要</div>"
        "<div class='section-subtitle'>系统会以所选主表做定量分析，并结合其他候选表与文献背景生成综合报告。</div>"
        "<table class='trace-table compact'>"
        "<thead><tr><th>table_id</th><th>页码</th><th>形状</th><th>列头摘要</th><th>数值列</th><th>内容提示</th><th>状态</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
        f"{background_html}{warnings_html}"
        "</section>"
    )
    status_text = (
        f"已提取 {len(preview.candidate_tables)} 张候选表，默认主表为 "
        f"{preview.default_table_id or '未识别'}。"
    )
    return build_status_markdown(status_text, level="info"), choices, preview.default_table_id or None, summary


def _running_outputs(status_text: str, logs: list[str]) -> tuple[object, ...]:
    return (
        build_status_markdown(status_text),
        "\n\n".join(logs),
        _empty_overview("运行总览", "任务正在运行中，关键指标会在结束后自动汇总到这里。"),
        "## 运行摘要\n\n任务正在运行中，请先查看实时日志了解进度。",
        "## 最终报告\n\n报告仍在生成中。",
        [],
        "## 审稿结果\n\n等待最终审稿结论。",
        "<section class='trace-workbench'><div class='section-heading'>诊断与轨迹</div><div class='empty-panel'>任务正在执行，完整轨迹会在结束后显示。</div></section>",
        None,
        None,
        None,
    )


def _result_outputs(
    result: AnalysisRunResult,
    logs: list[str],
    bundle_path: Path | None,
) -> tuple[object, ...]:
    status_level = "success" if result.workflow_complete else "warning"
    status_text = (
        f"运行完成。质量档位：{result.quality_mode}；"
        f"文档解析状态：{result.document_ingestion_status}；"
        f"RAG：{result.rag_status}；"
        f"文本审稿状态：{result.review_status}；"
        f"视觉审稿状态：{result.vision_review_status}；"
        f"返修轮次：{result.review_rounds_used}。"
    )
    report_download, trace_download, bundle_download = build_download_paths(
        report_path=result.report_path.as_posix(),
        trace_path=result.trace_path.as_posix(),
        bundle_path=bundle_path.as_posix() if bundle_path is not None else None,
    )
    report_markdown = convert_markdown_images_to_gradio_urls(
        result.report_markdown,
        project_root=Path.cwd(),
        base_dir=result.report_path.parent,
    )
    return (
        build_status_markdown(status_text, level=status_level),
        "\n\n".join(logs),
        build_overview_html(result),
        build_summary_markdown(result),
        report_markdown,
        build_gallery_items(result),
        build_review_markdown(result),
        build_trace_html(result),
        report_download,
        trace_download,
        bundle_download,
    )


def stream_analysis_session(
    uploaded_file: str | None,
    query: str,
    quality_mode: str,
    latency_mode: str,
    document_ingestion_mode: str,
    vision_review_mode: str,
    max_steps: float | int,
    max_reviews: float | int | None,
    max_pdf_pages: float | int,
    max_candidate_tables: float | int,
    vision_max_images: float | int,
    vision_max_image_side: float | int,
    selected_table_id: str | None,
    output_dir: str,
    agent_name: str,
    env_file: str,
    session_label: str,
    knowledge_uploads: str | Path | list[str] | list[Path] | tuple[str | Path, ...] | None = None,
    use_rag: bool = True,
) -> Generator[tuple[object, ...], None, None]:
    logs: list[str] = []
    if not uploaded_file:
        yield _error_outputs("请先上传一个 Excel、CSV 或 PDF 数据文件。", logs)
        return

    session_id = build_session_id(session_label)
    uploads_root = Path(output_dir) / "web_uploads"
    try:
        copied_file = copy_uploaded_file(uploaded_file, uploads_root=uploads_root, session_id=session_id)
    except Exception as exc:
        yield _error_outputs(f"上传文件处理失败：{exc}", logs)
        return

    logs.append(f"上传文件已复制到：{copied_file.as_posix()}")
    copied_knowledge_files: tuple[Path, ...] = ()
    if knowledge_uploads:
        try:
            copied_knowledge_files = copy_uploaded_knowledge_files(
                knowledge_uploads,
                uploads_root=uploads_root,
                session_id=session_id,
            )
        except Exception as exc:
            yield _error_outputs(f"知识文件处理失败：{exc}", logs)
            return
        if copied_knowledge_files:
            logs.append(f"知识文件已准备：{len(copied_knowledge_files)} 个")
    yield _running_outputs("文件已接收，正在启动分析任务。", logs)

    event_queue: queue.Queue[tuple[str, object]] = queue.Queue()

    def handle_event(event_type: str, payload: dict[str, object]) -> None:
        event_queue.put(("event", (event_type, payload)))

    def run_target() -> None:
        try:
            result = run_analysis(
                copied_file,
                query=query,
                output_dir=output_dir,
                env_file=env_file or None,
                agent_name=agent_name or "Advanced Data Analyst",
                max_steps=int(max_steps),
                max_reviews=None if max_reviews in ("", None) else int(max_reviews),
                quality_mode=quality_mode,
                latency_mode=latency_mode,
                document_ingestion_mode=document_ingestion_mode,
                max_pdf_pages=max(1, int(max_pdf_pages)),
                max_candidate_tables=max(1, int(max_candidate_tables)),
                selected_table_id=str(selected_table_id).strip() or None,
                vision_review_mode=vision_review_mode,
                vision_max_images=max(1, int(vision_max_images)),
                vision_max_image_side=max(256, min(int(vision_max_image_side), 2048)),
                event_handler=handle_event,
                knowledge_paths=copied_knowledge_files,
                use_rag=bool(use_rag),
            )
            event_queue.put(("result", result))
        except Exception as exc:
            event_queue.put(
                (
                    "error",
                    {
                        "message": str(exc),
                        "traceback": traceback.format_exc(),
                    },
                )
            )

    worker = threading.Thread(target=run_target, daemon=True)
    worker.start()

    finished = False
    while True:
        try:
            kind, payload = event_queue.get(timeout=0.1)
        except queue.Empty:
            if finished and not worker.is_alive():
                break
            continue

        if kind == "event":
            event_type, event_payload = payload
            logs.append(format_event_line(event_type, event_payload))
            yield _running_outputs(f"任务运行中：{event_type}", logs)
            continue

        if kind == "error":
            error_payload = payload
            logs.append(f"执行失败：{error_payload['message']}")
            logs.append(error_payload["traceback"])
            yield _error_outputs(f"分析失败：{error_payload['message']}", logs)
            finished = True
            continue

        if kind == "result":
            result = payload
            bundle_path = create_run_bundle(result.run_dir)
            logs.append(f"工件压缩包已生成：{bundle_path.as_posix()}")
            yield _result_outputs(result, logs, bundle_path)
            finished = True


__all__ = [
    "copy_uploaded_file",
    "copy_uploaded_knowledge_files",
    "create_run_bundle",
    "default_max_reviews_for_quality",
    "preview_pdf_candidates",
    "stream_analysis_session",
]
