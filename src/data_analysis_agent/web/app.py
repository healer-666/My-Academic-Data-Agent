"""Gradio application for Academic-Data-Agent."""

from __future__ import annotations

import argparse
from pathlib import Path

from ..prompts import DEFAULT_QUERY
from .history import build_history_choices, empty_history_outputs, load_history_record
from .service import (
    default_max_reviews_for_quality,
    preview_pdf_candidates,
    stream_analysis_session,
)

_GRADIO_IMPORT_ERROR: Exception | None = None

try:
    import gradio as gr
except Exception as exc:  # pragma: no cover - import guard
    gr = None
    _GRADIO_IMPORT_ERROR = exc


def _require_gradio():
    if gr is None:
        message = "gradio could not be imported."
        if _GRADIO_IMPORT_ERROR is not None:
            message = f"{message} Root cause: {_GRADIO_IMPORT_ERROR!r}"
        message = f"{message} Please verify the active Python environment and install dependencies from requirements.txt."
        raise RuntimeError(message) from _GRADIO_IMPORT_ERROR
    return gr


def build_demo():
    gradio = _require_gradio()

    theme = gradio.themes.Soft(
        primary_hue="indigo",
        secondary_hue="slate",
        neutral_hue="slate",
        font=[
            gradio.themes.GoogleFont("Inter"),
            "ui-sans-serif",
            "system-ui",
            "sans-serif",
        ],
    ).set(
        body_background_fill="#05070b",
        body_background_fill_dark="#05070b",
        block_background_fill="#0f131a",
        block_background_fill_dark="#0f131a",
        block_border_width="1px",
        block_border_color="#202938",
        block_border_color_dark="#202938",
        block_radius="10px",
        button_primary_background_fill="*primary_600",
        button_primary_background_fill_hover="*primary_500",
        button_primary_text_color="white",
        button_secondary_background_fill="#141a23",
        button_secondary_border_color="#273244",
        button_secondary_text_color="#e5edf7",
        input_background_fill="#0b1017",
        input_background_fill_dark="#0b1017",
        input_border_color="#2b3546",
        input_border_color_dark="#2b3546",
        input_border_color_focus="#5b8def",
        body_text_color="#f3f6fb",
        body_text_color_subdued="#a9b4c4",
        block_label_text_color="#d8e0eb",
    )

    custom_css = """
    footer { display: none !important; }
    html, body, .gradio-container {
      background:
        radial-gradient(circle at top left, rgba(91, 141, 239, 0.12), transparent 26%),
        linear-gradient(180deg, #05070b 0%, #0a0e14 100%) !important;
    }
    .gradio-container {
      max-width: min(1680px, calc(100vw - 32px)) !important;
      margin: 0 auto !important;
      padding: 24px 0 36px !important;
    }
    .workspace-row {
      align-items: flex-start;
      gap: 18px;
    }
    .control-column, .results-column {
      gap: 16px;
    }
    .control-card {
      border: 1px solid #202938 !important;
      border-radius: 14px !important;
      padding: 16px !important;
      background: #0f131a !important;
      box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.25);
    }
    .results-column {
      display: flex;
      flex-direction: column;
      min-height: calc(100vh - 170px);
    }
    .results-tabs {
      min-height: 760px;
    }
    .results-tabs .tabitem,
    .results-tabs [role="tabpanel"] {
      min-height: 640px;
    }
    .live-log-box textarea {
      min-height: 700px !important;
      max-height: 700px !important;
      overflow: auto !important;
    }
    .overview-card {
      border: 1px solid #202938;
      border-radius: 14px;
      background: #11161f;
      padding: 16px;
      box-shadow: 0 1px 2px rgb(0 0 0 / 0.20);
    }
    .section-title { margin: 0 0 6px; font-size: 16px; font-weight: 700; color: #f8fbff; }
    .section-copy, .section-subtitle { margin: 0; font-size: 13px; line-height: 1.7; color: #aeb9ca; }
    .app-title { margin: 0; font-size: 30px; font-weight: 800; color: #f8fbff; }
    .app-subtitle { margin: 10px 0 0; max-width: 960px; font-size: 14px; line-height: 1.8; color: #aeb9ca; }
    .metric-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 12px;
      margin-top: 14px;
    }
    .metric-card {
      border: 1px solid #273244;
      border-radius: 12px;
      background: linear-gradient(180deg, #161d27 0%, #121821 100%);
      padding: 14px;
    }
    .metric-label { font-size: 12px; color: #8fa0b7; margin-bottom: 6px; }
    .metric-value { font-size: 18px; font-weight: 800; color: #f8fbff; word-break: break-word; }
    .results-overview, .trace-workbench, .review-workbench { display: grid; gap: 12px; }
    .section-heading { font-size: 16px; font-weight: 700; color: #f8fbff; }
    .section-heading.secondary { font-size: 14px; margin-top: 4px; }
    .empty-panel {
      border: 1px dashed #314055;
      border-radius: 12px;
      background: #0f131a;
      color: #c8d2e0;
      padding: 14px;
    }
    .review-highlight, .history-trace-card {
      border: 1px solid #273244;
      border-radius: 12px;
      background: #11161f;
      padding: 14px;
      min-height: 0;
    }
    .review-status-pill {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 30px;
      padding: 0 12px;
      border-radius: 999px;
      background: rgba(91, 141, 239, 0.15);
      color: #dbe7ff;
      font-weight: 700;
      font-size: 12px;
      margin-bottom: 10px;
    }
    .review-highlight-body, .review-card-body {
      color: #dde6f2;
      line-height: 1.7;
      white-space: pre-wrap;
      word-break: break-word;
    }
    .review-history, .history-trace-grid { display: grid; gap: 12px; }
    .review-card {
      border: 1px solid #273244;
      border-radius: 12px;
      background: #11161f;
      padding: 14px;
    }
    .review-card-head, .history-trace-title {
      margin-bottom: 8px;
      font-size: 13px;
      font-weight: 700;
      color: #f8fbff;
    }
    .history-trace-grid { grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); }
    .history-scroll-area { max-height: 360px; overflow: auto; padding-right: 4px; }
    .history-scroll-area::-webkit-scrollbar { width: 8px; height: 8px; }
    .history-scroll-area::-webkit-scrollbar-thumb { background: #314055; border-radius: 999px; }
    .history-scroll-area::-webkit-scrollbar-track { background: #11161f; }
    .trace-table {
      width: 100%;
      border-collapse: collapse;
      overflow: hidden;
      border-radius: 10px;
      border: 1px solid #273244;
    }
    .trace-table th, .trace-table td {
      padding: 10px 12px;
      border-bottom: 1px solid #273244;
      text-align: left;
      vertical-align: top;
      color: #e5edf7;
      font-size: 13px;
      line-height: 1.6;
    }
    .trace-table th { background: #141a23; color: #f8fbff; font-weight: 700; }
    .trace-table.compact th, .trace-table.compact td { font-size: 12px; padding: 8px 10px; }
    .trace-status {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 64px;
      min-height: 28px;
      padding: 0 10px;
      border-radius: 999px;
      font-weight: 700;
      font-size: 12px;
    }
    .trace-status.ok { background: rgba(16, 185, 129, 0.15); color: #c9f7e6; }
    .trace-status.warn { background: rgba(245, 158, 11, 0.16); color: #fde8c2; }
    .trace-status.error { background: rgba(239, 68, 68, 0.16); color: #ffd4d4; }
    .gradio-container .tabs, .gradio-container .tabitem {
      background: #0f131a !important;
      border-color: #202938 !important;
    }
    .gradio-container .tab-nav button {
      border-radius: 10px !important;
      font-weight: 700;
      min-height: 38px;
      background: #11161f !important;
      border: 1px solid #202938 !important;
      color: #d8e0eb !important;
    }
    .gradio-container .tab-nav button.selected {
      background: #1b2431 !important;
      border-color: #5b8def !important;
      color: #ffffff !important;
      box-shadow: 0 0 0 1px rgba(91, 141, 239, 0.18);
    }
    .gradio-container textarea, .gradio-container input, .gradio-container select {
      font-size: 14px !important;
      color: #f8fbff !important;
      background: #0b1017 !important;
      border: 1px solid #2b3546 !important;
    }
    .gradio-container textarea::placeholder, .gradio-container input::placeholder { color: #74839a !important; }
    .gradio-container button.primary, .gradio-container button[variant="primary"] {
      width: 100%;
      min-height: 44px;
      font-weight: 700;
      box-shadow: 0 10px 20px rgb(79 70 229 / 0.20);
    }
    .gradio-container .markdown-body, .gradio-container .markdown-body p,
    .gradio-container .markdown-body li, .gradio-container .markdown-body strong,
    .gradio-container .prose, .gradio-container .md { color: #e8eef6 !important; }
    .gradio-container .markdown-body h1, .gradio-container .markdown-body h2,
    .gradio-container .markdown-body h3 { color: #f8fbff !important; }
    .gradio-container .markdown-body pre {
      background: #0b1017 !important;
      border: 1px solid #273244;
      color: #e8eef6 !important;
    }
    .gradio-container .markdown-body code {
      color: #e8eef6 !important;
      background: rgba(91, 141, 239, 0.10) !important;
    }
    .gradio-container .markdown-body table,
    .gradio-container .markdown-body th,
    .gradio-container .markdown-body td {
      border-color: #273244 !important;
      color: #e8eef6 !important;
    }
    .gradio-container .gallery,
    .gradio-container .gallery-item,
    .gradio-container .file-preview,
    .gradio-container .file-preview-holder {
      background: #0f131a !important;
      color: #e8eef6 !important;
      border-color: #202938 !important;
    }
    @media (max-width: 960px) {
      .gradio-container {
        max-width: calc(100vw - 20px) !important;
        padding: 18px 0 28px !important;
      }
      .results-tabs,
      .results-tabs .tabitem,
      .results-tabs [role="tabpanel"] {
        min-height: auto;
      }
      .live-log-box textarea {
        min-height: 420px !important;
        max-height: 420px !important;
      }
    }
    """

    history_choices, history_default = build_history_choices()
    history_outputs = load_history_record(history_default) if history_default else empty_history_outputs()

    def refresh_history_ui():
        choices, selected = build_history_choices()
        values = load_history_record(selected) if selected else empty_history_outputs()
        return (gradio.update(choices=choices, value=selected), *values)

    def preview_pdf_ui(uploaded_file, output_dir, session_label, max_pdf_pages, max_candidate_tables):
        status_text, choices, selected, summary_html = preview_pdf_candidates(
            uploaded_file,
            output_dir,
            session_label,
            max_pdf_pages,
            max_candidate_tables,
        )
        return status_text, gradio.update(choices=choices, value=selected), summary_html

    def auto_preview_pdf_ui(uploaded_file, output_dir, session_label, max_pdf_pages, max_candidate_tables):
        if not uploaded_file:
            return (
                gradio.update(),
                gradio.update(choices=[], value=None),
                "<section class='overview-card'><h2 class='section-title'>候选表摘要</h2><p class='section-copy'>上传 PDF 后可自动预览候选表，并手动覆盖默认主表。</p></section>",
            )
        suffix = Path(str(uploaded_file)).suffix.lower()
        if suffix != ".pdf":
            return (
                gradio.update(),
                gradio.update(choices=[], value=None),
                "<section class='overview-card'><h2 class='section-title'>候选表摘要</h2><p class='section-copy'>当前输入不是 PDF，无需主表选择；系统会直接按结构化表格路径分析。</p></section>",
            )
        return preview_pdf_ui(uploaded_file, output_dir, session_label, max_pdf_pages, max_candidate_tables)

    with gradio.Blocks(title="Academic-Data-Agent 交互工作台", theme=theme, css=custom_css) as demo:
        gradio.Markdown(
            """
            <div class="overview-card">
              <h1 class="app-title">Academic-Data-Agent 交互工作台</h1>
              <p class="app-subtitle">
                面向科研数据分析、报告生成、文档解析、文本审稿与视觉审稿的现代化工作台。左侧配置任务，右侧集中查看实时日志、运行总览、最终报告、图表、审稿结果和历史记录。
              </p>
            </div>
            """
        )

        with gradio.Row(elem_classes=["workspace-row"]):
            with gradio.Column(scale=1, min_width=320, elem_classes=["control-column"]):
                gradio.Markdown(
                    """
                    <div class="overview-card">
                      <h2 class="section-title">任务配置</h2>
                      <p class="section-copy">上传数据文件，配置质量、延迟、文档解析与视觉审稿策略，然后启动分析任务。</p>
                    </div>
                    """
                )
                with gradio.Group(elem_classes=["control-card"]):
                    upload = gradio.File(label="数据文件", type="filepath", file_types=[".csv", ".xls", ".xlsx", ".pdf"])
                    query = gradio.Textbox(label="分析任务描述", value=DEFAULT_QUERY, lines=7)
                    quality_mode = gradio.Dropdown(
                        label="报告质量档位",
                        choices=[
                            ("初稿 draft（不审稿）", "draft"),
                            ("标准 standard（默认 1 次返修）", "standard"),
                            ("高级 publication（默认 2 次返修）", "publication"),
                        ],
                        value="standard",
                    )
                    latency_mode = gradio.Dropdown(
                        label="延迟优化模式",
                        choices=[
                            ("自适应 auto（默认推荐）", "auto"),
                            ("质量优先 quality", "quality"),
                            ("极速 fast", "fast"),
                        ],
                        value="auto",
                    )
                    document_ingestion_mode = gradio.Dropdown(
                        label="文档解析模式",
                        choices=[
                            ("自动 auto（V1 走保守文本解析）", "auto"),
                            ("仅文本表格 text_only", "text_only"),
                            ("视觉兜底 vision_fallback（预留）", "vision_fallback"),
                        ],
                        value="auto",
                    )
                    preview_pdf_button = gradio.Button("预览候选表", variant="secondary")
                    selected_table_id = gradio.Dropdown(
                        label="主表选择",
                        choices=[],
                        value=None,
                        interactive=True,
                        allow_custom_value=False,
                    )
                    pdf_candidate_summary = gradio.HTML(
                        "<section class='overview-card'><h2 class='section-title'>候选表摘要</h2><p class='section-copy'>上传 PDF 后可先预览候选表，并手动覆盖默认主表。系统会用主表做定量分析，并结合其他候选表与文献背景生成综合报告。</p></section>"
                    )
                    vision_review_mode = gradio.Dropdown(
                        label="视觉审稿",
                        choices=[
                            ("关闭 off", "off"),
                            ("自动 auto（仅 publication 默认启用）", "auto"),
                            ("开启 on", "on"),
                        ],
                        value="auto",
                    )
                    max_reviews = gradio.Number(label="最大返修次数", value=1, precision=0)
                    with gradio.Accordion("高级设置", open=False):
                        max_steps = gradio.Slider(label="最大控制步数", minimum=2, maximum=12, step=1, value=6)
                        max_pdf_pages = gradio.Slider(label="PDF 最大解析页数", minimum=1, maximum=50, step=1, value=20)
                        max_candidate_tables = gradio.Slider(label="候选表摘要上限", minimum=1, maximum=12, step=1, value=5)
                        vision_max_images = gradio.Slider(label="视觉审稿图片上限", minimum=1, maximum=6, step=1, value=3)
                        vision_max_image_side = gradio.Slider(label="视觉审稿图片最长边", minimum=512, maximum=2048, step=256, value=1024)
                        output_dir = gradio.Textbox(label="输出目录前缀", value="outputs")
                        agent_name = gradio.Textbox(label="Agent 名称", value="Advanced Data Analyst")
                        env_file = gradio.Textbox(label="环境变量文件", value="", placeholder="可选，例如 .env")
                        session_label = gradio.Textbox(label="会话标签", value="", placeholder="可选，用于区分上传会话")
                run_button = gradio.Button("开始分析", variant="primary")

            with gradio.Column(scale=3, min_width=600, elem_classes=["results-column"]):
                status = gradio.Markdown(
                    """
                    <div class="overview-card status-card">
                      <h2 class="section-title">当前状态</h2>
                      <p class="section-copy">等待开始。</p>
                    </div>
                    """
                )
                overview = gradio.HTML(
                    """
                    <section class="overview-card">
                      <h2 class="section-title">运行总览</h2>
                      <p class="section-copy">任务启动后，这里会显示识别领域、质量档位、输入类型、文档解析、文本审稿、视觉审稿和总耗时。</p>
                      <div class="metric-grid">
                        <article class="metric-card"><div class="metric-label">识别领域</div><div class="metric-value">等待运行</div></article>
                        <article class="metric-card"><div class="metric-label">报告质量</div><div class="metric-value">等待运行</div></article>
                        <article class="metric-card"><div class="metric-label">输入类型</div><div class="metric-value">等待运行</div></article>
                        <article class="metric-card"><div class="metric-label">文档解析</div><div class="metric-value">等待运行</div></article>
                        <article class="metric-card"><div class="metric-label">文本审稿</div><div class="metric-value">等待运行</div></article>
                        <article class="metric-card"><div class="metric-label">视觉审稿</div><div class="metric-value">等待运行</div></article>
                      </div>
                    </section>
                    """
                )

                with gradio.Tabs(elem_classes=["results-tabs"]):
                    with gradio.Tab("实时日志"):
                        logs = gradio.Textbox(label="运行事件流", lines=30, interactive=False, elem_classes=["live-log-box"])
                    with gradio.Tab("运行摘要"):
                        summary = gradio.Markdown("## 运行摘要\n\n尚未开始。")
                    with gradio.Tab("最终报告"):
                        report = gradio.Markdown("## 最终报告\n\n尚未生成。")
                    with gradio.Tab("图表画廊"):
                        gallery = gradio.Gallery(label="生成的图表", columns=2, height="auto")
                    with gradio.Tab("审稿结果"):
                        review = gradio.HTML(
                            "<section class='overview-card'><h2 class='section-title'>审稿工作台</h2><p class='section-copy'>尚未开始审稿。</p></section>"
                        )
                    with gradio.Tab("诊断与轨迹"):
                        diagnostics = gradio.HTML(
                            "<section class='overview-card'><h2 class='section-title'>诊断与轨迹</h2><p class='section-copy'>暂无执行轨迹。</p></section>"
                        )
                    with gradio.Tab("下载工件"):
                        gradio.Markdown(
                            """
                            <div class="overview-card">
                              <h2 class="section-title">下载工件</h2>
                              <p class="section-copy">运行完成后，可在这里下载最终报告、Agent 运行轨迹以及运行目录 ZIP 压缩包。</p>
                            </div>
                            """
                        )
                        report_file = gradio.File(label="下载 final_report.md")
                        trace_file = gradio.File(label="下载 agent_trace.json")
                        bundle_file = gradio.File(label="下载运行目录 ZIP")
                    with gradio.Tab("历史记录"):
                        with gradio.Row():
                            refresh_history_button = gradio.Button("刷新历史记录", variant="secondary")
                            history_selector = gradio.Dropdown(
                                label="历史运行记录",
                                choices=history_choices,
                                value=history_default,
                                interactive=True,
                            )
                        history_overview = gradio.HTML(history_outputs[0])
                        history_report = gradio.Markdown(history_outputs[1])
                        history_gallery = gradio.Gallery(label="历史图表", columns=2, height="auto", value=history_outputs[2])
                        history_diagnostics = gradio.HTML(history_outputs[3])
                        history_report_file = gradio.File(label="历史 final_report.md", value=history_outputs[4])
                        history_trace_file = gradio.File(label="历史 agent_trace.json", value=history_outputs[5])
                        history_cleaned_file = gradio.File(label="历史 cleaned_data.csv", value=history_outputs[6])

        quality_mode.change(
            fn=default_max_reviews_for_quality,
            inputs=quality_mode,
            outputs=max_reviews,
            api_name=False,
            show_api=False,
        )

        upload.change(
            fn=auto_preview_pdf_ui,
            inputs=[upload, output_dir, session_label, max_pdf_pages, max_candidate_tables],
            outputs=[status, selected_table_id, pdf_candidate_summary],
            api_name=False,
            show_api=False,
        )

        preview_pdf_button.click(
            fn=preview_pdf_ui,
            inputs=[upload, output_dir, session_label, max_pdf_pages, max_candidate_tables],
            outputs=[status, selected_table_id, pdf_candidate_summary],
            api_name=False,
            show_api=False,
        )

        run_button.click(
            fn=stream_analysis_session,
            inputs=[
                upload,
                query,
                quality_mode,
                latency_mode,
                document_ingestion_mode,
                vision_review_mode,
                max_steps,
                max_reviews,
                max_pdf_pages,
                max_candidate_tables,
                vision_max_images,
                vision_max_image_side,
                selected_table_id,
                output_dir,
                agent_name,
                env_file,
                session_label,
            ],
            outputs=[
                status,
                logs,
                overview,
                summary,
                report,
                gallery,
                review,
                diagnostics,
                report_file,
                trace_file,
                bundle_file,
            ],
            api_name=False,
            show_api=False,
        )

        refresh_history_button.click(
            fn=refresh_history_ui,
            inputs=[],
            outputs=[
                history_selector,
                history_overview,
                history_report,
                history_gallery,
                history_diagnostics,
                history_report_file,
                history_trace_file,
                history_cleaned_file,
            ],
            api_name=False,
            show_api=False,
        )

        history_selector.change(
            fn=load_history_record,
            inputs=history_selector,
            outputs=[
                history_overview,
                history_report,
                history_gallery,
                history_diagnostics,
                history_report_file,
                history_trace_file,
                history_cleaned_file,
            ],
            api_name=False,
            show_api=False,
        )

    demo.queue()
    return demo


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch the Academic-Data-Agent Gradio web demo.")
    parser.add_argument("--server-name", default="127.0.0.1", help="Server host for Gradio.")
    parser.add_argument("--server-port", type=int, default=7860, help="Server port for Gradio.")
    parser.add_argument("--share", action="store_true", help="Whether to enable a public Gradio share link.")
    args = parser.parse_args()

    demo = build_demo()
    allowed_paths = [(Path.cwd() / "outputs").resolve().as_posix()]
    try:
        demo.launch(
            server_name=args.server_name,
            server_port=args.server_port,
            share=args.share,
            show_api=False,
            allowed_paths=allowed_paths,
        )
    except ValueError as exc:
        if not args.share and "localhost is not accessible" in str(exc):
            print("Localhost accessibility check failed. Retrying with share=True...")
            demo.launch(
                server_name=args.server_name,
                server_port=args.server_port,
                share=True,
                show_api=False,
                allowed_paths=allowed_paths,
            )
        else:
            raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
