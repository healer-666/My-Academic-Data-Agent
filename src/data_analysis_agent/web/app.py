"""Gradio application for Academic-Data-Agent."""

from __future__ import annotations

import argparse
from pathlib import Path

from ..prompts import DEFAULT_QUERY
from .history import build_history_choices, empty_history_outputs, load_history_record
from .service import default_max_reviews_for_quality, preview_pdf_candidates, stream_analysis_session

_GRADIO_IMPORT_ERROR: Exception | None = None

try:
    import gradio as gr
except Exception as exc:  # pragma: no cover
    gr = None
    _GRADIO_IMPORT_ERROR = exc


def _require_gradio():
    if gr is None:
        message = "gradio could not be imported."
        if _GRADIO_IMPORT_ERROR is not None:
            message = f"{message} Root cause: {_GRADIO_IMPORT_ERROR!r}"
        raise RuntimeError(f"{message} Please verify the active Python environment and install dependencies from requirements.txt.") from _GRADIO_IMPORT_ERROR
    return gr


def build_demo():
    gradio = _require_gradio()
    theme = gradio.themes.Soft(
        primary_hue="blue",
        secondary_hue="amber",
        neutral_hue="stone",
        font=[gradio.themes.GoogleFont("Space Grotesk"), gradio.themes.GoogleFont("IBM Plex Sans"), "system-ui", "sans-serif"],
    ).set(
        body_background_fill="#f5efe3",
        body_background_fill_dark="#f5efe3",
        block_background_fill="#fdf9f2",
        block_background_fill_dark="#fdf9f2",
        block_border_color="#d6c7b2",
        block_border_color_dark="#d6c7b2",
        block_radius="16px",
        button_secondary_background_fill="#f7f0e3",
        button_secondary_border_color="#d0b48c",
        button_secondary_text_color="#1f3655",
        input_background_fill="#fffdfa",
        input_background_fill_dark="#fffdfa",
        input_border_color="#ccb99b",
        input_border_color_dark="#ccb99b",
        input_border_color_focus="#2e5b8a",
        body_text_color="#1f2d3d",
        body_text_color_subdued="#6c7685",
        block_label_text_color="#173454",
    )
    custom_css = """
    footer{display:none!important}
    html,body,.gradio-container{background:radial-gradient(circle at top left,rgba(49,96,149,.16),transparent 30%),radial-gradient(circle at bottom right,rgba(198,144,78,.14),transparent 32%),linear-gradient(180deg,#f6efe3 0%,#efe4d1 100%)!important}
    .gradio-container{max-width:min(1680px,calc(100vw - 32px))!important;margin:0 auto!important;padding:28px 0 40px!important}
    .workspace-grid{align-items:flex-start;gap:20px}.sidebar-column,.main-column{gap:16px}.main-column{min-height:calc(100vh - 150px)}
    .hero-panel,.sidebar-card,.composer-shell,.results-shell,.support-card,.overview-card,.status-shell{border:1px solid #d6c7b2!important;border-radius:18px!important;background:linear-gradient(180deg,rgba(255,251,245,.96) 0%,rgba(248,240,228,.98) 100%)!important;box-shadow:0 18px 40px rgba(106,79,46,.1)}
    .hero-panel{padding:24px 26px!important}.sidebar-card,.composer-shell,.support-card,.results-shell,.overview-card,.status-shell{padding:16px!important}
    .hero-eyebrow,.status-eyebrow,.empty-state-badge{display:inline-flex;width:fit-content;padding:6px 10px;border-radius:999px;font-size:12px;font-weight:700;letter-spacing:.05em;text-transform:uppercase}
    .hero-eyebrow,.status-eyebrow{background:rgba(46,91,138,.1);color:#244a74}.empty-state-badge{background:rgba(198,144,78,.14);color:#9a5a19}
    .hero-title{margin:16px 0 12px;font-size:clamp(32px,4vw,48px);line-height:1.08;font-weight:800;color:#173454;max-width:760px}
    .hero-copy,.sidebar-copy,.composer-copy,.section-copy,.section-subtitle,.status-copy{margin:0;color:#5f6774;line-height:1.75}
    .hero-grid,.metric-grid,.sidebar-meta-list{display:grid;gap:12px}.hero-grid{grid-template-columns:repeat(auto-fit,minmax(180px,1fr));margin-top:18px}.metric-grid{grid-template-columns:repeat(auto-fit,minmax(150px,1fr));margin-top:14px}
    .hero-chip,.metric-card,.sidebar-meta-item,.review-highlight,.history-trace-card,.review-card{border:1px solid rgba(46,91,138,.12);border-radius:14px;background:rgba(255,255,255,.72);padding:14px}
    .hero-chip-label,.metric-label,.sidebar-meta-label{font-size:12px;color:#7a756d;margin-bottom:6px}.hero-chip-value,.metric-value,.sidebar-meta-value{font-size:16px;font-weight:700;color:#173454;line-height:1.5}
    .composer-shell{position:relative;overflow:hidden}.composer-shell:before{content:"";position:absolute;inset:0 auto auto 0;width:180px;height:180px;background:radial-gradient(circle,rgba(46,91,138,.1),transparent 72%);pointer-events:none}
    .composer-title,.sidebar-title,.section-title,.section-heading,.status-title{margin:0 0 6px;color:#173454;font-weight:800}.composer-title,.sidebar-title{font-size:18px}.section-title,.section-heading{font-size:16px}.status-title{font-size:20px}
    .button-cluster{display:grid;grid-template-columns:minmax(0,.95fr) minmax(0,1.05fr);gap:10px}.results-tabs{min-height:760px}.results-tabs .tabitem,.results-tabs [role=tabpanel]{min-height:640px}
    .live-log-box textarea{min-height:700px!important;max-height:700px!important;overflow:auto!important}
    .empty-panel{border:1px dashed #c7b18c;border-radius:14px;background:rgba(255,255,255,.56);color:#5f6774;padding:14px}
    .review-status-pill,.trace-status{display:inline-flex;align-items:center;justify-content:center;border-radius:999px;font-weight:700;font-size:12px}.review-status-pill{min-height:30px;padding:0 12px;background:rgba(46,91,138,.12);color:#244a74;margin-bottom:10px}
    .review-highlight-body,.review-card-body{color:#415062;line-height:1.7;white-space:pre-wrap;word-break:break-word}.review-history,.history-trace-grid,.results-overview,.trace-workbench,.review-workbench{display:grid;gap:12px}
    .history-trace-grid{grid-template-columns:repeat(auto-fit,minmax(260px,1fr))}.history-scroll-area{max-height:360px;overflow:auto;padding-right:4px}
    .history-scroll-area::-webkit-scrollbar{width:8px;height:8px}.history-scroll-area::-webkit-scrollbar-thumb{background:#c3a985;border-radius:999px}.history-scroll-area::-webkit-scrollbar-track{background:#f3ebde}
    .trace-table{width:100%;border-collapse:collapse;overflow:hidden;border-radius:12px;border:1px solid #d8c7b1}.trace-table th,.trace-table td{padding:10px 12px;border-bottom:1px solid #e4d7c5;text-align:left;vertical-align:top;color:#344558;font-size:13px;line-height:1.6}.trace-table th{background:#efe1cc;color:#173454;font-weight:700}.trace-table.compact th,.trace-table.compact td{font-size:12px;padding:8px 10px}
    .trace-status{min-width:64px;min-height:28px;padding:0 10px}.trace-status.ok{background:rgba(52,131,104,.13);color:#235b48}.trace-status.warn{background:rgba(198,144,78,.16);color:#9a5a19}.trace-status.error{background:rgba(180,79,69,.14);color:#8f2b22}
    .gradio-container .tabs,.gradio-container .tabitem{background:transparent!important;border-color:#d6c7b2!important}
    .gradio-container .tab-nav button{border-radius:999px!important;font-weight:700;min-height:40px;background:rgba(255,251,245,.82)!important;border:1px solid #d6c7b2!important;color:#4b5b6d!important}
    .gradio-container .tab-nav button.selected{background:#244a74!important;border-color:#244a74!important;color:#fffdf9!important;box-shadow:0 10px 20px rgba(36,74,116,.18)}
    .gradio-container textarea,.gradio-container input,.gradio-container select{font-size:14px!important;color:#223447!important;background:rgba(255,255,255,.92)!important;border:1px solid #ccb99b!important;border-radius:14px!important}
    .gradio-container textarea::placeholder,.gradio-container input::placeholder{color:#8390a2!important}
    .gradio-container button.primary,.gradio-container button[variant="primary"]{width:100%;min-height:46px;font-weight:700;border-radius:14px!important;box-shadow:0 16px 28px rgba(36,74,116,.22)}
    .gradio-container button.secondary,.gradio-container button[variant="secondary"]{border-radius:14px!important}
    .gradio-container .markdown-body,.gradio-container .markdown-body p,.gradio-container .markdown-body li,.gradio-container .markdown-body strong,.gradio-container .prose,.gradio-container .md{color:#314254!important}
    .gradio-container .markdown-body h1,.gradio-container .markdown-body h2,.gradio-container .markdown-body h3{color:#173454!important}
    .gradio-container .markdown-body pre{background:#fffdfa!important;border:1px solid #d8c7b1;color:#314254!important}.gradio-container .markdown-body code{color:#244a74!important;background:rgba(46,91,138,.1)!important}
    .gradio-container .markdown-body table,.gradio-container .markdown-body th,.gradio-container .markdown-body td,.gradio-container .gallery,.gradio-container .gallery-item,.gradio-container .file-preview,.gradio-container .file-preview-holder{border-color:#d8c7b1!important;color:#314254!important;background:rgba(255,251,245,.9)!important}
    @media (max-width:960px){.gradio-container{max-width:calc(100vw - 20px)!important;padding:18px 0 28px!important}.hero-title{font-size:30px}.button-cluster{grid-template-columns:1fr}.results-tabs,.results-tabs .tabitem,.results-tabs [role=tabpanel]{min-height:auto}.live-log-box textarea{min-height:420px!important;max-height:420px!important}}
    """

    history_choices, history_default = build_history_choices()
    history_outputs = load_history_record(history_default) if history_default else empty_history_outputs()

    def refresh_history_ui():
        choices, selected = build_history_choices()
        values = load_history_record(selected) if selected else empty_history_outputs()
        return (gradio.update(choices=choices, value=selected), *values)

    def preview_pdf_ui(uploaded_file, output_dir, session_label, max_pdf_pages, max_candidate_tables):
        status_text, choices, selected, summary_html = preview_pdf_candidates(uploaded_file, output_dir, session_label, max_pdf_pages, max_candidate_tables)
        return status_text, gradio.update(choices=choices, value=selected), summary_html

    def auto_preview_pdf_ui(uploaded_file, output_dir, session_label, max_pdf_pages, max_candidate_tables):
        if not uploaded_file:
            return gradio.update(), gradio.update(choices=[], value=None), "<section class='overview-card'><h2 class='section-title'>候选表摘要</h2><p class='section-copy'>上传 PDF 后会自动预览候选表，并允许手动覆盖主表选择。</p></section>"
        if Path(str(uploaded_file)).suffix.lower() != ".pdf":
            return gradio.update(), gradio.update(choices=[], value=None), "<section class='overview-card'><h2 class='section-title'>候选表摘要</h2><p class='section-copy'>当前输入不是 PDF，无需主表选择；系统会直接按结构化数据路径分析。</p></section>"
        return preview_pdf_ui(uploaded_file, output_dir, session_label, max_pdf_pages, max_candidate_tables)

    with gradio.Blocks(title="Academic-Data-Agent 交互工作台", theme=theme, css=custom_css) as demo:
        gradio.Markdown(
            """
            <section class="hero-panel">
              <div class="hero-eyebrow">Academic Data Agent</div>
              <h1 class="hero-title">把数据分析、文献理解、审稿回路和运行轨迹放进同一张工作台。</h1>
              <p class="hero-copy">左侧负责会话回看和任务导航，右侧专注当前分析。空态下它像一张欢迎工作台，进入任务后就会切换成可追踪、可复盘、适合长链路 Agent 的执行界面。</p>
              <div class="hero-grid">
                <article class="hero-chip"><div class="hero-chip-label">任务入口</div><div class="hero-chip-value">数据文件、知识文档、主表选择围绕一个输入区域组织</div></article>
                <article class="hero-chip"><div class="hero-chip-label">运行反馈</div><div class="hero-chip-value">状态、事件流、审稿结果和轨迹各自有清晰展示协议</div></article>
                <article class="hero-chip"><div class="hero-chip-label">可回顾</div><div class="hero-chip-value">历史运行记录、图表和工件下载集中在同一工作区</div></article>
              </div>
            </section>
            """
        )
        with gradio.Row(elem_classes=["workspace-grid"]):
            with gradio.Column(scale=1, min_width=300, elem_classes=["sidebar-column"]):
                gradio.Markdown(
                    """
                    <section class="sidebar-card">
                      <h2 class="sidebar-title">历史与导航</h2>
                      <p class="sidebar-copy">先把最近的运行和当前工作重点放在左侧，方便你在分析中途随时切回历史记录，或者快速继续上一次实验。</p>
                      <div class="sidebar-meta-list">
                        <article class="sidebar-meta-item"><div class="sidebar-meta-label">适合的工作方式</div><div class="sidebar-meta-value">先预览主表，再开始完整分析</div></article>
                        <article class="sidebar-meta-item"><div class="sidebar-meta-label">推荐体验</div><div class="sidebar-meta-value">先看状态与摘要，再回到最终报告和诊断轨迹</div></article>
                      </div>
                    </section>
                    """
                )
                with gradio.Group(elem_classes=["sidebar-card"]):
                    refresh_history_button = gradio.Button("刷新历史记录", variant="secondary")
                    history_selector = gradio.Dropdown(label="历史运行记录", choices=history_choices, value=history_default, interactive=True)
                    history_overview = gradio.HTML(history_outputs[0])
                gradio.Markdown(
                    """
                    <section class="support-card">
                      <h2 class="sidebar-title">使用提示</h2>
                      <p class="sidebar-copy">如果是 PDF，建议先点“预览候选表”；如果是结构化数据，直接描述你想要的分析重点，系统会生成报告、图表、审稿结果和运行工件。</p>
                    </section>
                    """
                )
            with gradio.Column(scale=3, min_width=720, elem_classes=["main-column"]):
                with gradio.Group(elem_classes=["composer-shell"]):
                    gradio.Markdown("<div><h2 class='composer-title'>开始一次新的分析</h2><p class='composer-copy'>输入区围绕“数据文件 + 任务描述 + 模式控制”组织，既保留研究场景需要的细粒度控制，也尽量降低第一次上手的心智负担。</p></div>")
                    upload = gradio.File(label="数据文件", type="filepath", file_types=[".csv", ".xls", ".xlsx", ".pdf"])
                    knowledge_uploads = gradio.File(label="知识文档（可选，可多选）", file_count="multiple", file_types=[".txt", ".md", ".pdf"])
                    query = gradio.Textbox(label="分析任务描述", value=DEFAULT_QUERY, lines=7, placeholder="例如：请结合数据分布、异常点、关键变量关系和潜在局限，生成一份适合研究讨论的分析报告。")
                    quality_mode = gradio.Dropdown(label="报告质量档位", choices=[("初稿 draft（不审稿）", "draft"), ("标准 standard（默认 1 次返修）", "standard"), ("高级 publication（默认 2 次返修）", "publication")], value="standard")
                    latency_mode = gradio.Dropdown(label="延迟优化模式", choices=[("自适应 auto（默认推荐）", "auto"), ("质量优先 quality", "quality"), ("极速 fast", "fast")], value="auto")
                    document_ingestion_mode = gradio.Dropdown(label="文档解析模式", choices=[("自动 auto（V1 走保守文本解析）", "auto"), ("仅文本表格 text_only", "text_only"), ("视觉兜底 vision_fallback（预留）", "vision_fallback")], value="auto")
                    if hasattr(gradio, "Checkbox"):
                        use_rag = gradio.Checkbox(label="启用本地 RAG 知识增强", value=True)
                        use_memory = gradio.Checkbox(label="启用 Project Memory 回忆", value=True)
                    else:  # pragma: no cover
                        use_rag = gradio.Dropdown(label="启用本地 RAG 知识增强", choices=[("开启", True), ("关闭", False)], value=True)
                        use_memory = gradio.Dropdown(label="启用 Project Memory 回忆", choices=[("开启", True), ("关闭", False)], value=True)
                    selected_table_id = gradio.Dropdown(label="主表选择", choices=[], value=None, interactive=True, allow_custom_value=False)
                    pdf_candidate_summary = gradio.HTML("<section class='overview-card'><h2 class='section-title'>候选表摘要</h2><p class='section-copy'>上传 PDF 后可先预览候选表，并手动覆盖默认主表。系统会用主表做定量分析，并结合其他候选表与文献背景生成综合报告。</p></section>")
                    vision_review_mode = gradio.Dropdown(label="视觉审稿", choices=[("关闭 off", "off"), ("自动 auto（仅 publication 默认启用）", "auto"), ("开启 on", "on")], value="auto")
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
                        memory_scope_label = gradio.Textbox(
                            label="Memory scope 标签",
                            value="",
                            placeholder="可选，默认复用会话标签或输入文件名",
                        )
                    with gradio.Row(elem_classes=["button-cluster"]):
                        preview_pdf_button = gradio.Button("预览候选表", variant="secondary")
                        run_button = gradio.Button("开始分析", variant="primary")
                status = gradio.Markdown("<section class='status-shell status-warning'><div class='status-eyebrow'>Academic Data Agent</div><div class='status-title'>等待开始</div><div class='status-copy'>上传数据或 PDF，补充任务描述后即可启动分析。页面会在运行过程中持续更新状态、事件流和结果概览。</div></section>")
                overview = gradio.HTML(
                    "<section class='overview-card'><h2 class='section-title'>运行总览</h2><p class='section-copy'>任务启动后，这里会显示识别领域、质量档位、输入类型、文档解析、文本审稿、视觉审稿以及总耗时。空态时保持欢迎工作台，进入任务后再切换成执行视图。</p><div class='metric-grid'><article class='metric-card'><div class='metric-label'>识别领域</div><div class='metric-value'>等待运行</div></article><article class='metric-card'><div class='metric-label'>报告质量</div><div class='metric-value'>等待运行</div></article><article class='metric-card'><div class='metric-label'>输入类型</div><div class='metric-value'>等待运行</div></article><article class='metric-card'><div class='metric-label'>文档解析</div><div class='metric-value'>等待运行</div></article><article class='metric-card'><div class='metric-label'>文本审稿</div><div class='metric-value'>等待运行</div></article><article class='metric-card'><div class='metric-label'>视觉审稿</div><div class='metric-value'>等待运行</div></article></div></section>"
                )
                with gradio.Group(elem_classes=["results-shell"]):
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
                            review = gradio.HTML("<section class='overview-card'><h2 class='section-title'>审稿工作台</h2><p class='section-copy'>尚未开始审稿。</p></section>")
                        with gradio.Tab("诊断与轨迹"):
                            diagnostics = gradio.HTML("<section class='overview-card'><h2 class='section-title'>诊断与轨迹</h2><p class='section-copy'>暂无执行轨迹。</p></section>")
                        with gradio.Tab("下载工件"):
                            gradio.Markdown("<div class='overview-card'><h2 class='section-title'>下载工件</h2><p class='section-copy'>运行完成后，可在这里下载最终报告、Agent 运行轨迹以及运行目录 ZIP 压缩包。</p></div>")
                            report_file = gradio.File(label="下载 final_report.md")
                            trace_file = gradio.File(label="下载 agent_trace.json")
                            bundle_file = gradio.File(label="下载运行目录 ZIP")
                        with gradio.Tab("历史记录"):
                            history_report = gradio.Markdown(history_outputs[1])
                            history_gallery = gradio.Gallery(label="历史图表", columns=2, height="auto", value=history_outputs[2])
                            history_diagnostics = gradio.HTML(history_outputs[3])
                            history_report_file = gradio.File(label="历史 final_report.md", value=history_outputs[4])
                            history_trace_file = gradio.File(label="历史 agent_trace.json", value=history_outputs[5])
                            history_cleaned_file = gradio.File(label="历史 cleaned_data.csv", value=history_outputs[6])

        quality_mode.change(fn=default_max_reviews_for_quality, inputs=quality_mode, outputs=max_reviews, api_name=False, show_api=False)
        upload.change(fn=auto_preview_pdf_ui, inputs=[upload, output_dir, session_label, max_pdf_pages, max_candidate_tables], outputs=[status, selected_table_id, pdf_candidate_summary], api_name=False, show_api=False)
        preview_pdf_button.click(fn=preview_pdf_ui, inputs=[upload, output_dir, session_label, max_pdf_pages, max_candidate_tables], outputs=[status, selected_table_id, pdf_candidate_summary], api_name=False, show_api=False)
        run_button.click(
            fn=stream_analysis_session,
            inputs=[upload, query, quality_mode, latency_mode, document_ingestion_mode, vision_review_mode, max_steps, max_reviews, max_pdf_pages, max_candidate_tables, vision_max_images, vision_max_image_side, selected_table_id, output_dir, agent_name, env_file, session_label, knowledge_uploads, use_rag, use_memory, memory_scope_label],
            outputs=[status, logs, overview, summary, report, gallery, review, diagnostics, report_file, trace_file, bundle_file],
            api_name=False,
            show_api=False,
        )
        refresh_history_button.click(fn=refresh_history_ui, inputs=[], outputs=[history_selector, history_overview, history_report, history_gallery, history_diagnostics, history_report_file, history_trace_file, history_cleaned_file], api_name=False, show_api=False)
        history_selector.change(fn=load_history_record, inputs=history_selector, outputs=[history_overview, history_report, history_gallery, history_diagnostics, history_report_file, history_trace_file, history_cleaned_file], api_name=False, show_api=False)
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
        demo.launch(server_name=args.server_name, server_port=args.server_port, share=args.share, show_api=False, allowed_paths=allowed_paths)
    except ValueError as exc:
        if not args.share and "localhost is not accessible" in str(exc):
            print("Localhost accessibility check failed. Retrying with share=True...")
            demo.launch(server_name=args.server_name, server_port=args.server_port, share=True, show_api=False, allowed_paths=allowed_paths)
        else:
            raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
