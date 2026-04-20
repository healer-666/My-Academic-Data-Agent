"""Gradio application for Academic-Data-Agent."""

from __future__ import annotations

import argparse
from pathlib import Path

from ..prompts import DEFAULT_QUERY
from .history import build_history_choices, empty_history_outputs, load_history_record
from .service import (
    answer_history_question_ui,
    default_max_reviews_for_quality,
    load_knowledge_base_status,
    load_history_qa_runs,
    load_workspace_browser_state,
    stream_analysis_session,
)

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
        raise RuntimeError(
            f"{message} Please verify the active Python environment and install dependencies from requirements.txt."
        ) from _GRADIO_IMPORT_ERROR
    return gr


def build_demo():
    gradio = _require_gradio()
    theme = gradio.themes.Soft(
        primary_hue="blue",
        secondary_hue="teal",
        neutral_hue="slate",
        font=[
            gradio.themes.GoogleFont("Noto Sans SC"),
            gradio.themes.GoogleFont("Space Grotesk"),
            gradio.themes.GoogleFont("IBM Plex Sans"),
            "system-ui",
            "sans-serif",
        ],
    ).set(
        body_background_fill="#0a0e14",
        body_background_fill_dark="#0a0e14",
        block_background_fill="#0f1621",
        block_background_fill_dark="#0f1621",
        block_border_color="#223042",
        block_border_color_dark="#223042",
        block_radius="18px",
        input_background_fill="#0d141d",
        input_background_fill_dark="#0d141d",
        input_border_color="#2b3a4d",
        input_border_color_dark="#2b3a4d",
        input_border_color_focus="#3ba7ff",
        button_secondary_background_fill="#111b27",
        button_secondary_border_color="#2f4055",
        button_secondary_text_color="#e0e8f5",
        body_text_color="#e9eef8",
        body_text_color_subdued="#96a6bf",
        block_label_text_color="#dfe8f6",
    )
    custom_css = """
    :root{
      --bg:#0a0e14;
      --bg-soft:#0f1621;
      --panel:#121b28;
      --panel-2:#172131;
      --line:rgba(116,144,181,.18);
      --line-strong:rgba(116,144,181,.30);
      --text:#eaf1fb;
      --muted:#95a4ba;
      --blue:#3aa8ff;
      --teal:#18c5a8;
      --cyan:#65d8ff;
      --shadow:0 18px 48px rgba(0,0,0,.34);
    }
    footer{display:none!important}
    html,body,.gradio-container{
      background:
        radial-gradient(circle at 12% 18%, rgba(58,168,255,.13), transparent 24%),
        radial-gradient(circle at 88% 10%, rgba(24,197,168,.10), transparent 22%),
        linear-gradient(180deg,#091018 0%,#0b121a 46%,#0a0e14 100%)!important;
      color:var(--text)!important;
    }
    .gradio-container{
      max-width:min(1860px,calc(100vw - 28px))!important;
      margin:0 auto!important;
      padding:18px 18px 34px!important;
      min-height:700px;
    }
    .topbar,.hero-shell,.section-shell,.form-shell,.monitor-shell,.history-shell,.rail-shell{
      border:1px solid var(--line)!important;
      background:linear-gradient(180deg,rgba(17,24,36,.96),rgba(10,16,24,.98))!important;
      border-radius:20px!important;
      box-shadow:var(--shadow);
    }
    .topbar{padding:16px 20px!important;margin-bottom:18px;display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap}
    .hero-shell,.section-shell,.form-shell,.monitor-shell,.history-shell,.rail-shell{padding:22px!important}
    .brand-line,.pill-line{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
    .brand-mark{width:42px;height:42px;border-radius:14px;display:grid;place-items:center;background:linear-gradient(135deg,var(--blue),var(--teal));color:#04111c;font-weight:900;font-size:18px;box-shadow:0 10px 30px rgba(58,168,255,.28)}
    .brand-title{font-size:28px;font-weight:900;letter-spacing:-.04em;color:var(--text)}
    .brand-subtitle{font-size:13px;color:var(--muted);letter-spacing:.08em;text-transform:uppercase}
    .nav-chip,.pill-chip{padding:9px 14px;border-radius:999px;border:1px solid var(--line);background:rgba(255,255,255,.02);color:var(--muted);font-size:13px;font-weight:700}
    .nav-chip.active{background:rgba(58,168,255,.12);border-color:rgba(58,168,255,.32);color:#eef6ff}
    .page-shell{margin-top:10px}
    .hero-grid{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(340px,.9fr);gap:18px}
    .eyebrow{display:inline-flex;padding:8px 14px;border-radius:999px;background:rgba(58,168,255,.12);border:1px solid rgba(58,168,255,.24);color:#9cd7ff;font-size:11px;font-weight:800;letter-spacing:.12em;text-transform:uppercase}
    .hero-title{margin:18px 0 12px;font-size:clamp(34px,5vw,56px);line-height:1.06;font-weight:900;letter-spacing:-.05em;max-width:760px}
    .hero-title em{font-style:normal;color:#8fe6ff}
    .hero-copy,.section-copy,.rail-copy{color:var(--muted);font-size:15px;line-height:1.78;margin:0}
    .headline{font-size:24px;font-weight:900;letter-spacing:-.03em;margin:12px 0 10px;color:var(--text)}
    .summary-list,.workflow-list,.rail-list{display:grid;gap:12px;margin-top:18px}
    .summary-item,.workflow-item,.rail-item{padding:16px 18px;border-radius:16px;border:1px solid var(--line);background:rgba(255,255,255,.02)}
    .summary-kicker,.workflow-kicker,.rail-kicker{font-size:12px;color:var(--muted);font-weight:700;letter-spacing:.08em;text-transform:uppercase;margin-bottom:8px}
    .summary-value{font-size:24px;font-weight:900;letter-spacing:-.03em}
    .workspace-grid,.history-grid{gap:18px;align-items:flex-start}
    .form-head{display:grid;grid-template-columns:minmax(0,1.2fr) minmax(280px,.8fr);gap:18px;margin-bottom:18px}
    .soft-note{border-left:3px solid rgba(24,197,168,.7);padding-left:14px;color:var(--muted);font-size:14px;line-height:1.7}
    .form-grid,.control-grid,.button-grid{display:grid;gap:14px}
    .form-grid{grid-template-columns:repeat(2,minmax(0,1fr));margin-bottom:14px}
    .control-grid{grid-template-columns:repeat(3,minmax(0,1fr))}
    .button-grid{grid-template-columns:minmax(0,.9fr) minmax(0,1.1fr);margin-top:18px}
    .monitor-grid{display:grid;grid-template-columns:minmax(340px,.9fr) minmax(0,1.1fr);gap:18px;align-items:flex-start}
    .result-tabs .tabitem,.result-tabs [role=tabpanel]{min-height:680px}
    .live-log-box textarea{min-height:720px!important;max-height:720px!important;overflow:auto!important;background:#0b1118!important;border:1px solid var(--line)!important;color:#d9e3ef!important;font-family:ui-monospace,SFMono-Regular,Menlo,monospace!important;font-size:13px!important;line-height:1.6!important}
    .history-tip{margin-top:16px;padding-top:16px;border-top:1px solid var(--line)}
    .results-overview,.trace-workbench,.review-workbench{
      display:grid;
      gap:16px;
      padding:6px 2px;
    }
    .section-heading{
      font-size:22px;
      font-weight:900;
      color:var(--text);
      letter-spacing:-.03em;
    }
    .section-heading.secondary{
      margin-top:8px;
      font-size:18px;
    }
    .section-subtitle{
      color:var(--muted);
      font-size:14px;
      line-height:1.7;
    }
    .metric-grid{
      display:grid;
      grid-template-columns:repeat(2,minmax(0,1fr));
      gap:12px;
    }
    .metric-card{
      padding:16px 18px;
      border-radius:16px;
      border:1px solid var(--line);
      background:linear-gradient(180deg,rgba(22,32,46,.82),rgba(13,19,28,.96));
    }
    .metric-label{
      font-size:12px;
      color:var(--muted);
      font-weight:700;
      letter-spacing:.08em;
      text-transform:uppercase;
      margin-bottom:8px;
    }
    .metric-value{
      font-size:18px;
      line-height:1.45;
      color:var(--text);
      font-weight:800;
      word-break:break-word;
    }
    .review-highlight{
      padding:16px 18px;
      border-radius:16px;
      border:1px solid var(--line);
      background:rgba(255,255,255,.02);
    }
    .review-status-pill{
      display:inline-flex;
      align-items:center;
      min-height:30px;
      padding:0 12px;
      border-radius:999px;
      border:1px solid rgba(58,168,255,.22);
      background:rgba(58,168,255,.10);
      color:#9fd7ff;
      font-size:12px;
      font-weight:800;
      letter-spacing:.06em;
      text-transform:uppercase;
      margin-bottom:12px;
    }
    .review-highlight-body{
      color:var(--text);
      font-size:14px;
      line-height:1.7;
    }
    .review-history{
      display:grid;
      gap:12px;
    }
    .review-card{
      padding:15px 16px;
      border-radius:14px;
      border:1px solid var(--line);
      background:rgba(255,255,255,.02);
    }
    .review-card-head{
      color:var(--text);
      font-weight:800;
      margin-bottom:8px;
    }
    .review-card-body,.empty-panel{
      color:var(--muted);
      font-size:14px;
      line-height:1.7;
    }
    .inline-muted{color:var(--muted);font-size:12px}
    .trace-table{
      width:100%;
      border-collapse:collapse;
      border:1px solid var(--line);
      border-radius:16px;
      overflow:hidden;
      background:rgba(255,255,255,.02);
    }
    .trace-table th,.trace-table td{
      padding:12px 14px;
      border-bottom:1px solid var(--line);
      text-align:left;
      vertical-align:top;
      font-size:13px;
      line-height:1.6;
    }
    .trace-table th{
      color:var(--muted);
      font-weight:800;
      background:rgba(255,255,255,.03);
    }
    .gradio-container .tabs,.gradio-container .tabitem{background:transparent!important;border:none!important}
    .gradio-container .tab-nav{gap:10px!important;margin-bottom:14px!important}
    .gradio-container .tab-nav button{min-height:44px;border-radius:12px!important;border:1px solid var(--line)!important;background:rgba(255,255,255,.03)!important;color:var(--muted)!important;font-size:14px!important;font-weight:800!important}
    .gradio-container .tab-nav button.selected{background:linear-gradient(90deg,rgba(58,168,255,.95),rgba(24,197,168,.88))!important;border-color:transparent!important;color:#04111c!important;box-shadow:0 12px 30px rgba(58,168,255,.24)}
    .gradio-container textarea,.gradio-container input,.gradio-container select{border-radius:14px!important;border:1px solid var(--line)!important;background:#0d141d!important;color:#eef4ff!important;font-size:14px!important;padding:10px 12px!important}
    .gradio-container textarea:focus,.gradio-container input:focus,.gradio-container select:focus{border-color:rgba(58,168,255,.38)!important;box-shadow:0 0 0 3px rgba(58,168,255,.10)!important;background:#0f1721!important}
    .gradio-container button.primary,.gradio-container button[variant="primary"]{min-height:50px;border:none!important;border-radius:14px!important;background:linear-gradient(90deg,#3aa8ff,#18c5a8)!important;color:#04111c!important;font-weight:900!important;box-shadow:0 16px 34px rgba(58,168,255,.24)}
    .gradio-container button.secondary,.gradio-container button[variant="secondary"]{min-height:50px;border-radius:14px!important;border:1px solid var(--line)!important;background:#111b27!important;color:#e0e8f5!important;font-weight:800!important}
    .gradio-container .markdown-body,.gradio-container .markdown-body p,.gradio-container .markdown-body li,.gradio-container .md{color:#dce5f2!important;font-size:15px!important;line-height:1.72!important}
    .gradio-container .markdown-body code{color:#8fd9ff!important;background:rgba(58,168,255,.10)!important;border-radius:4px!important}
    .gradio-container .markdown-body pre{background:#0b1118!important;border:1px solid var(--line)!important;border-radius:14px!important}
    .gradio-container .markdown-body table,.gradio-container .markdown-body th,.gradio-container .markdown-body td,.gradio-container .gallery,.gradio-container .gallery-item,.gradio-container .file-preview,.gradio-container .file-preview-holder{border-color:var(--line)!important;background:rgba(255,255,255,.02)!important;color:#dce5f2!important}
    @media (max-width:1200px){.hero-grid,.form-head,.monitor-grid{grid-template-columns:1fr}.control-grid,.metric-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
    @media (max-width:960px){.gradio-container{max-width:calc(100vw - 16px)!important;padding:12px 10px 28px!important}.hero-grid,.form-grid,.control-grid,.button-grid,.metric-grid{grid-template-columns:1fr}.pill-line{display:none}.result-tabs .tabitem,.result-tabs [role=tabpanel]{min-height:auto}.live-log-box textarea{min-height:460px!important;max-height:460px!important}}
    """

    history_choices, history_default = build_history_choices()
    history_outputs = load_history_record(history_default) if history_default else empty_history_outputs()
    history_qa_choices, history_qa_default = load_history_qa_runs()
    knowledge_base_status_html = load_knowledge_base_status()

    def refresh_workspace_ui(output_dir):
        return load_workspace_browser_state(output_dir or "outputs")

    with gradio.Blocks(title="学术数据智能体交互工作台", theme=theme, css=custom_css) as demo:
        gradio.Markdown(
            """
            <section class="topbar">
                <div class="brand-line">
                  <div class="brand-mark">智</div>
                  <div>
                    <div class="brand-title">学术数据智能体工作台</div>
                    <div class="brand-subtitle">表格分析 · 参考资料 · 历史追问</div>
                  </div>
                </div>
                <div class="pill-line">
                <span class="pill-chip">自动分析</span>
                <span class="pill-chip">参考资料沉淀</span>
                <span class="pill-chip">历史追问</span>
                </div>
            </section>
            """
        )

        with gradio.Tabs(elem_classes=["result-tabs"]):
            with gradio.Tab("开始分析"):
                with gradio.Row(elem_classes=["workspace-grid", "page-shell"]):
                    with gradio.Column(scale=3, min_width=820):
                        with gradio.Group(elem_classes=["form-shell"]):
                            gradio.Markdown(
                                """
                                <div class="form-head">
                                  <div>
                                    <div class="eyebrow">第一步</div>
                                    <div class="headline">上传表格，告诉我你想解决什么问题</div>
                                    <p class="section-copy">主线只保留用户真正常用的操作：上传数据、补充参考资料、开始分析。</p>
                                  </div>
                                  <div class="soft-note">
                                    上传的参考资料会自动沉淀到本地知识库，之后的分析也可以继续使用。
                                  </div>
                                </div>
                                """
                            )
                            upload = gradio.File(label="上传表格数据", type="filepath", file_types=[".csv", ".xls", ".xlsx"])
                            query = gradio.Textbox(label="你希望我重点回答什么", value=DEFAULT_QUERY, lines=7, placeholder="例如：我想知道哪些变量最重要、是否存在显著差异、需要什么图表来支持结论。")
                            knowledge_uploads = gradio.File(label="可沉淀的参考资料（可选，多文件）", file_count="multiple", file_types=[".txt", ".md", ".pdf"])
                            with gradio.Row(elem_classes=["form-grid"]):
                                quality_mode = gradio.Dropdown(label="输出深度", choices=[("快速草稿", "draft"), ("标准分析", "standard"), ("深入分析", "publication")], value="standard")
                                latency_mode = gradio.Dropdown(label="速度 / 质量偏好", choices=[("自动平衡", "auto"), ("质量优先", "quality"), ("速度优先", "fast")], value="auto")
                            with gradio.Row(elem_classes=["form-grid"]):
                                vision_review_mode = gradio.Dropdown(label="检查图表表达", choices=[("关闭", "off"), ("自动", "auto"), ("始终检查", "on")], value="auto")
                            with gradio.Row(elem_classes=["form-grid"]):
                                use_rag = gradio.Checkbox(label="使用参考资料辅助分析", value=True)
                                use_memory = gradio.Checkbox(label="参考历史经验", value=True)
                            with gradio.Accordion("高级设置（一般不用改）", open=False):
                                with gradio.Row(elem_classes=["control-grid"]):
                                    max_steps = gradio.Slider(label="最多尝试多少步", minimum=2, maximum=12, step=1, value=6)
                                    max_reviews = gradio.Number(label="最多返修轮次", value=1, precision=0)
                                with gradio.Row(elem_classes=["control-grid"]):
                                    vision_max_images = gradio.Slider(label="最多检查多少张图表", minimum=1, maximum=6, step=1, value=3)
                                    vision_max_image_side = gradio.Slider(label="图表检查分辨率", minimum=512, maximum=2048, step=256, value=1024)
                                with gradio.Row(elem_classes=["control-grid"]):
                                    output_dir = gradio.Textbox(label="结果保存目录", value="outputs")
                                    agent_name = gradio.Textbox(label="分析角色名", value="Advanced Data Analyst")
                                    env_file = gradio.Textbox(label="环境文件路径", value="", placeholder="留空则使用默认环境")
                                with gradio.Row(elem_classes=["control-grid"]):
                                    session_label = gradio.Textbox(label="任务标签", value="", placeholder="用于区分当前任务")
                                    memory_scope_label = gradio.Textbox(label="历史经验分组标签", value="", placeholder="留空则默认复用任务标签或输入文件名")
                            with gradio.Row(elem_classes=["button-grid"]):
                                run_button = gradio.Button("开始分析", variant="primary")

                    with gradio.Column(scale=1, min_width=320):
                        gradio.Markdown(
                            """
                            <section class="rail-shell">
                              <div class="eyebrow">使用提示</div>
                              <div class="headline">更适合面向任务来操作</div>
                              <p class="rail-copy">先明确问题，再决定要不要补参考资料和历史经验。</p>
                              <div class="rail-list">
                                <article class="rail-item"><div class="rail-kicker">数据</div><div>当前主线专注 CSV / Excel 表格分析。</div></article>
                                <article class="rail-item"><div class="rail-kicker">参考资料</div><div>上传后会加入本地知识库，不是只用这一次。</div></article>
                                <article class="rail-item"><div class="rail-kicker">历史追问</div><div>分析完成后可在“历史与追问”里继续比较和追问。</div></article>
                              </div>
                            </section>
                            """
                        )
                        knowledge_base_status = gradio.HTML(knowledge_base_status_html)

            with gradio.Tab("查看结果"):
                with gradio.Row(elem_classes=["monitor-grid", "page-shell"]):
                    status = gradio.Markdown("<section class='monitor-shell'><div class='eyebrow'>任务状态</div><div class='headline'>等待任务开始</div><p class='section-copy'>开始分析后，这里会持续显示当前进度。</p></section>")
                    overview = gradio.HTML("<section class='monitor-shell'><div class='eyebrow'>结果概览</div><div class='headline'>暂无任务</div><p class='section-copy'>这里会汇总本次分析的关键结论和可信度信息。</p></section>")
                with gradio.Group(elem_classes=["monitor-shell"]):
                    with gradio.Tabs(elem_classes=["result-tabs"]):
                        with gradio.Tab("实时进度"):
                            logs = gradio.Textbox(label="实时进度", lines=30, interactive=False, elem_classes=["live-log-box"])
                        with gradio.Tab("结论摘要"):
                            summary = gradio.Markdown("## 运行摘要\n\n等待结果。")
                        with gradio.Tab("完整报告"):
                            report = gradio.Markdown("## 最终报告\n\n等待结果。")
                        with gradio.Tab("图表"):
                            gallery = gradio.Gallery(label="生成的图表与图片", columns=2, height="auto")
                        with gradio.Tab("可信度检查"):
                            review = gradio.HTML("<section class='section-shell'><div class='eyebrow'>可信度</div><div class='headline'>等待检查结果</div><p class='section-copy'>审稿和图表检查完成后会显示在这里。</p></section>")
                        with gradio.Tab("详细过程"):
                            diagnostics = gradio.HTML("<section class='section-shell'><div class='eyebrow'>详细过程</div><div class='headline'>等待运行轨迹</div><p class='section-copy'>这里会展示更完整的执行过程和诊断信息。</p></section>")
                        with gradio.Tab("下载结果"):
                            gradio.Markdown("<section class='section-shell'><div class='eyebrow'>结果文件</div><div class='headline'>下载产物</div><p class='section-copy'>报告、轨迹和完整压缩包会出现在这里。</p></section>")
                            report_file = gradio.File(label="下载 final_report.md")
                            trace_file = gradio.File(label="下载 agent_trace.json")
                            bundle_file = gradio.File(label="下载整套工件 ZIP")

            with gradio.Tab("历史与追问"):
                with gradio.Row(elem_classes=["history-grid", "page-shell"]):
                    with gradio.Column(scale=1, min_width=320):
                        gradio.Markdown(
                            """
                            <section class="history-shell">
                              <div class="eyebrow">第三步</div>
                              <div class="headline">回看历史结果，并继续追问</div>
                              <p class="rail-copy">这里把历史记录、对比追问和知识库刷新收在同一页里。</p>
                              <div class="history-tip">新的分析完成后，列表会自动刷新到这里。</div>
                            </section>
                            """
                        )
                        with gradio.Group(elem_classes=["history-shell"]):
                            refresh_history_button = gradio.Button("刷新历史与知识库", variant="secondary")
                            history_selector = gradio.Dropdown(label="选择历史分析", choices=history_choices, value=history_default, interactive=True)
                            history_overview = gradio.HTML(history_outputs[0])
                        with gradio.Group(elem_classes=["history-shell"]):
                            history_qa_run_ids = gradio.Dropdown(
                                label="追问范围",
                                choices=history_qa_choices,
                                value=history_qa_default,
                                multiselect=True,
                                interactive=True,
                            )
                            history_qa_mode = gradio.Dropdown(
                                label="追问方式",
                                choices=[("单次追问", "single"), ("跨运行对比", "compare")],
                                value="single",
                            )
                            history_qa_question = gradio.Textbox(
                                label="继续追问",
                                lines=6,
                                placeholder="例如：上次为什么使用非参数检验？哪次报告被审稿拒绝，原因是什么？",
                            )
                            history_qa_button = gradio.Button("开始追问", variant="primary")
                    with gradio.Column(scale=3, min_width=820):
                        with gradio.Group(elem_classes=["history-shell"]):
                            with gradio.Tabs(elem_classes=["result-tabs"]):
                                with gradio.Tab("历史报告"):
                                    history_report = gradio.Markdown(history_outputs[1])
                                with gradio.Tab("历史图表"):
                                    history_gallery = gradio.Gallery(label="历史图表", columns=2, height="auto", value=history_outputs[2])
                                with gradio.Tab("历史过程"):
                                    history_diagnostics = gradio.HTML(history_outputs[3])
                                with gradio.Tab("历史文件"):
                                    history_report_file = gradio.File(label="下载 final_report.md", value=history_outputs[4])
                                    history_trace_file = gradio.File(label="下载 agent_trace.json", value=history_outputs[5])
                                    history_cleaned_file = gradio.File(label="下载 cleaned_data.csv", value=history_outputs[6])
                                with gradio.Tab("追问结果"):
                                    history_qa_answer = gradio.Markdown("## 历史问答结果\n\n等待提问。")
                                    history_qa_sources = gradio.HTML(
                                        "<section class='results-overview'><div class='section-heading'>历史问答来源</div><div class='empty-panel'>提交问题后显示来源切片。</div></section>"
                                    )

        quality_mode.change(fn=default_max_reviews_for_quality, inputs=quality_mode, outputs=max_reviews, api_name=False, show_api=False)
        run_button.click(
            fn=stream_analysis_session,
            inputs=[upload, query, quality_mode, latency_mode, vision_review_mode, max_steps, max_reviews, vision_max_images, vision_max_image_side, output_dir, agent_name, env_file, session_label, knowledge_uploads, use_rag, use_memory, memory_scope_label],
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
                history_selector,
                history_overview,
                history_report,
                history_gallery,
                history_diagnostics,
                history_report_file,
                history_trace_file,
                history_cleaned_file,
                history_qa_run_ids,
                knowledge_base_status,
            ],
            api_name=False,
            show_api=False,
        )
        history_selector.change(fn=load_history_record, inputs=history_selector, outputs=[history_overview, history_report, history_gallery, history_diagnostics, history_report_file, history_trace_file, history_cleaned_file], api_name=False, show_api=False)
        refresh_history_button.click(
            fn=refresh_workspace_ui,
            inputs=[output_dir],
            outputs=[
                history_selector,
                history_overview,
                history_report,
                history_gallery,
                history_diagnostics,
                history_report_file,
                history_trace_file,
                history_cleaned_file,
                history_qa_run_ids,
                knowledge_base_status,
            ],
            api_name=False,
            show_api=False,
        )
        history_qa_button.click(
            fn=answer_history_question_ui,
            inputs=[history_qa_question, history_qa_run_ids, history_qa_mode, output_dir, env_file],
            outputs=[history_qa_answer, history_qa_sources],
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
