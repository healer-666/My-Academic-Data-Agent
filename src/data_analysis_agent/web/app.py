"""Gradio application for Academic-Data-Agent."""

from __future__ import annotations

import argparse
from pathlib import Path

from ..prompts import DEFAULT_QUERY
from .history import build_history_choices, empty_history_outputs, load_history_record
from .service import (
    answer_history_question_ui,
    default_max_reviews_for_quality,
    load_history_qa_runs,
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

    def refresh_history_ui():
        choices, selected = build_history_choices()
        values = load_history_record(selected) if selected else empty_history_outputs()
        return (gradio.update(choices=choices, value=selected), *values)

    def refresh_history_qa_ui(output_dir):
        choices, defaults = load_history_qa_runs(output_dir or "outputs")
        return gradio.update(choices=choices, value=defaults)

    with gradio.Blocks(title="学术数据智能体交互工作台", theme=theme, css=custom_css) as demo:
        gradio.Markdown(
            """
            <section class="topbar">
              <div class="brand-line">
                <div class="brand-mark">智</div>
                <div>
                  <div class="brand-title">学术数据智能体工作台</div>
                  <div class="brand-subtitle">分析 · 证据 · 记忆</div>
                </div>
              </div>
              <div class="pill-line">
                <span class="pill-chip">RAG v3</span>
                <span class="pill-chip">Project Memory</span>
                <span class="pill-chip">证据归因</span>
              </div>
            </section>
            """
        )

        with gradio.Tabs(elem_classes=["result-tabs"]):
            with gradio.Tab("总览"):
                gradio.Markdown(
                    """
                    <section class="hero-grid page-shell">
                      <section class="hero-shell">
                        <div class="eyebrow">控制台首页</div>
                        <h1 class="hero-title">面向 <em>结构化表格数据</em> 的分析与历史问答工作台。</h1>
                        <p class="hero-copy">上传、分析、审稿、回看、追问。</p>
                        <div class="workflow-list">
                          <article class="workflow-item"><div class="workflow-kicker">工作流</div><div>上传 → 分析 → 报告 → 审稿 → 历史问答</div></article>
                          <article class="workflow-item"><div class="workflow-kicker">输入</div><div>Excel、CSV、知识文档</div></article>
                        </div>
                      </section>
                      <section class="hero-shell">
                        <div class="eyebrow">当前能力</div>
                        <div class="summary-list">
                          <article class="summary-item"><div class="summary-kicker">检索层</div><div class="summary-value">混合检索 + 结构化重排</div></article>
                          <article class="summary-item"><div class="summary-kicker">分析层</div><div class="summary-value">受控分析 + 审稿返修</div></article>
                          <article class="summary-item"><div class="summary-kicker">可信度层</div><div class="summary-value">行内短引用 + Reviewer 校验</div></article>
                          <article class="summary-item"><div class="summary-kicker">历史层</div><div class="summary-value">项目级 Memory + 历史问答</div></article>
                        </div>
                      </section>
                    </section>
                    <section class="section-shell page-shell">
                      <div class="eyebrow">导航</div>
                      <div class="headline">总览 / 发起分析 / 运行结果 / 历史记录 / 历史问答</div>
                    </section>
                    """
                )

            with gradio.Tab("发起分析"):
                with gradio.Row(elem_classes=["workspace-grid", "page-shell"]):
                    with gradio.Column(scale=3, min_width=820):
                        with gradio.Group(elem_classes=["form-shell"]):
                            gradio.Markdown(
                                """
                                <div class="form-head">
                                  <div>
                                    <div class="eyebrow">新建任务</div>
                                    <div class="headline">在这里组织一次完整分析</div>
                                    <p class="section-copy">填写输入和策略后直接开始。</p>
                                  </div>
                                  <div class="soft-note">
                                    结果请到“运行结果”页面查看。
                                  </div>
                                </div>
                                """
                            )
                            upload = gradio.File(label="数据文件", type="filepath", file_types=[".csv", ".xls", ".xlsx"])
                            knowledge_uploads = gradio.File(label="知识文档（可选，多文件）", file_count="multiple", file_types=[".txt", ".md", ".pdf"])
                            query = gradio.Textbox(label="分析目标", value=DEFAULT_QUERY, lines=7, placeholder="请描述你希望系统重点回答的问题、关注的指标、报告偏好与输出风格。")
                            with gradio.Row(elem_classes=["form-grid"]):
                                quality_mode = gradio.Dropdown(label="报告质量档位", choices=[("快速草稿（draft）", "draft"), ("标准分析（standard）", "standard"), ("高标准投稿风格（publication）", "publication")], value="standard")
                                latency_mode = gradio.Dropdown(label="延迟策略", choices=[("自动平衡（auto）", "auto"), ("质量优先（quality）", "quality"), ("速度优先（fast）", "fast")], value="auto")
                            with gradio.Row(elem_classes=["form-grid"]):
                                vision_review_mode = gradio.Dropdown(label="视觉审稿", choices=[("关闭", "off"), ("自动", "auto"), ("始终开启", "on")], value="auto")
                            with gradio.Row(elem_classes=["form-grid"]):
                                use_rag = gradio.Checkbox(label="启用 RAG 检索增强", value=True)
                                use_memory = gradio.Checkbox(label="启用 Project Memory 回忆", value=True)
                            with gradio.Accordion("高级参数", open=False):
                                with gradio.Row(elem_classes=["control-grid"]):
                                    max_steps = gradio.Slider(label="最大分析步数", minimum=2, maximum=12, step=1, value=6)
                                    max_reviews = gradio.Number(label="最大返修轮次", value=1, precision=0)
                                with gradio.Row(elem_classes=["control-grid"]):
                                    vision_max_images = gradio.Slider(label="视觉审稿图片数", minimum=1, maximum=6, step=1, value=3)
                                    vision_max_image_side = gradio.Slider(label="视觉图片边长", minimum=512, maximum=2048, step=256, value=1024)
                                with gradio.Row(elem_classes=["control-grid"]):
                                    output_dir = gradio.Textbox(label="输出目录", value="outputs")
                                    agent_name = gradio.Textbox(label="Agent 名称", value="Advanced Data Analyst")
                                    env_file = gradio.Textbox(label="环境文件路径", value="", placeholder="留空则使用默认环境")
                                with gradio.Row(elem_classes=["control-grid"]):
                                    session_label = gradio.Textbox(label="会话标签", value="", placeholder="用于区分当前任务")
                                    memory_scope_label = gradio.Textbox(label="Memory scope 标签", value="", placeholder="留空则默认复用会话标签或输入文件名")
                            with gradio.Row(elem_classes=["button-grid"]):
                                run_button = gradio.Button("开始分析", variant="primary")

                    with gradio.Column(scale=1, min_width=320):
                        gradio.Markdown(
                            """
                            <section class="rail-shell">
                              <div class="eyebrow">提示</div>
                              <div class="headline">历史与导航</div>
                              <p class="rail-copy">只保留当前任务最常用的提醒。</p>
                              <div class="rail-list">
                                <article class="rail-item"><div class="rail-kicker">输入</div><div>仅支持结构化表格数据主线。</div></article>
                                <article class="rail-item"><div class="rail-kicker">连续项目</div><div>建议开启 Project Memory。</div></article>
                                <article class="rail-item"><div class="rail-kicker">追问</div><div>完成分析后可到历史问答页继续提问。</div></article>
                              </div>
                            </section>
                            """
                        )
                        input_summary = gradio.HTML("<section class='section-shell'><div class='eyebrow'>数据入口</div><div class='headline'>结构化表格主线</div><p class='section-copy'>上传 CSV 或 Excel 后即可直接进入分析。</p></section>")

            with gradio.Tab("运行结果"):
                with gradio.Row(elem_classes=["monitor-grid", "page-shell"]):
                    status = gradio.Markdown("<section class='monitor-shell'><div class='eyebrow'>运行状态</div><div class='headline'>等待任务开始</div><p class='section-copy'>开始分析后显示实时状态。</p></section>")
                    overview = gradio.HTML("<section class='monitor-shell'><div class='eyebrow'>运行总览</div><div class='headline'>暂无任务</div><p class='section-copy'>这里显示本次任务概览。</p></section>")
                with gradio.Group(elem_classes=["monitor-shell"]):
                    with gradio.Tabs(elem_classes=["result-tabs"]):
                        with gradio.Tab("运行事件流"):
                            logs = gradio.Textbox(label="运行事件流", lines=30, interactive=False, elem_classes=["live-log-box"])
                        with gradio.Tab("运行摘要"):
                            summary = gradio.Markdown("## 运行摘要\n\n等待结果。")
                        with gradio.Tab("最终报告"):
                            report = gradio.Markdown("## 最终报告\n\n等待结果。")
                        with gradio.Tab("图表产物"):
                            gallery = gradio.Gallery(label="生成的图表与图片", columns=2, height="auto")
                        with gradio.Tab("审稿结果"):
                            review = gradio.HTML("<section class='section-shell'><div class='eyebrow'>Reviewer</div><div class='headline'>等待审稿</div><p class='section-copy'>审稿结果会显示在这里。</p></section>")
                        with gradio.Tab("诊断与轨迹"):
                            diagnostics = gradio.HTML("<section class='section-shell'><div class='eyebrow'>Trace</div><div class='headline'>等待运行轨迹</div><p class='section-copy'>这里显示详细轨迹。</p></section>")
                        with gradio.Tab("下载产物"):
                            gradio.Markdown("<section class='section-shell'><div class='eyebrow'>Artifacts</div><div class='headline'>下载产物</div><p class='section-copy'>报告、轨迹和归档包。</p></section>")
                            report_file = gradio.File(label="下载 final_report.md")
                            trace_file = gradio.File(label="下载 agent_trace.json")
                            bundle_file = gradio.File(label="下载整套工件 ZIP")

            with gradio.Tab("历史记录"):
                with gradio.Row(elem_classes=["history-grid", "page-shell"]):
                    with gradio.Column(scale=1, min_width=320):
                        gradio.Markdown(
                            """
                            <section class="history-shell">
                              <div class="eyebrow">回看与复盘</div>
                              <div class="headline">历史运行记录</div>
                              <p class="rail-copy">选择记录后查看报告、图表和轨迹。</p>
                              <div class="history-tip">用于回看已完成任务。</div>
                            </section>
                            """
                        )
                        with gradio.Group(elem_classes=["history-shell"]):
                            refresh_history_button = gradio.Button("刷新历史记录", variant="secondary")
                            history_selector = gradio.Dropdown(label="历史运行记录", choices=history_choices, value=history_default, interactive=True)
                            history_overview = gradio.HTML(history_outputs[0])
                    with gradio.Column(scale=3, min_width=820):
                        with gradio.Group(elem_classes=["history-shell"]):
                            with gradio.Tabs(elem_classes=["result-tabs"]):
                                with gradio.Tab("历史报告"):
                                    history_report = gradio.Markdown(history_outputs[1])
                                with gradio.Tab("历史图表"):
                                    history_gallery = gradio.Gallery(label="历史图表", columns=2, height="auto", value=history_outputs[2])
                                with gradio.Tab("历史诊断"):
                                    history_diagnostics = gradio.HTML(history_outputs[3])
                                with gradio.Tab("历史文件"):
                                    history_report_file = gradio.File(label="下载 final_report.md", value=history_outputs[4])
                                    history_trace_file = gradio.File(label="下载 agent_trace.json", value=history_outputs[5])
                                    history_cleaned_file = gradio.File(label="下载 cleaned_data.csv", value=history_outputs[6])

            with gradio.Tab("历史问答"):
                with gradio.Row(elem_classes=["history-grid", "page-shell"]):
                    with gradio.Column(scale=1, min_width=320):
                        gradio.Markdown(
                            """
                            <section class="history-shell">
                              <div class="eyebrow">历史智能体</div>
                              <div class="headline">对历史分析结果继续追问</div>
                              <p class="rail-copy">围绕已完成运行，解释结论、方法、图表、审稿意见和来源。</p>
                              <div class="history-tip">支持单次追问和多次运行对比。</div>
                            </section>
                            """
                        )
                        with gradio.Group(elem_classes=["history-shell"]):
                            refresh_history_qa_button = gradio.Button("刷新问答运行列表", variant="secondary")
                            history_qa_run_ids = gradio.Dropdown(
                                label="问答运行范围",
                                choices=history_qa_choices,
                                value=history_qa_default,
                                multiselect=True,
                                interactive=True,
                            )
                            history_qa_mode = gradio.Dropdown(
                                label="问答模式",
                                choices=[("单次追问", "single"), ("跨运行对比", "compare")],
                                value="single",
                            )
                    with gradio.Column(scale=3, min_width=820):
                        with gradio.Group(elem_classes=["history-shell"]):
                            history_qa_question = gradio.Textbox(
                                label="问题",
                                lines=6,
                                placeholder="例如：上次为什么使用非参数检验？哪次报告被审稿拒绝，原因是什么？",
                            )
                            history_qa_button = gradio.Button("开始追问", variant="primary")
                            history_qa_answer = gradio.Markdown("## 历史问答结果\n\n等待提问。")
                            history_qa_sources = gradio.HTML(
                                "<section class='results-overview'><div class='section-heading'>历史问答来源</div><div class='empty-panel'>提交问题后显示来源切片。</div></section>"
                            )

        quality_mode.change(fn=default_max_reviews_for_quality, inputs=quality_mode, outputs=max_reviews, api_name=False, show_api=False)
        run_button.click(
            fn=stream_analysis_session,
            inputs=[upload, query, quality_mode, latency_mode, vision_review_mode, max_steps, max_reviews, vision_max_images, vision_max_image_side, output_dir, agent_name, env_file, session_label, knowledge_uploads, use_rag, use_memory, memory_scope_label],
            outputs=[status, logs, overview, summary, report, gallery, review, diagnostics, report_file, trace_file, bundle_file],
            api_name=False,
            show_api=False,
        )
        refresh_history_button.click(fn=refresh_history_ui, inputs=[], outputs=[history_selector, history_overview, history_report, history_gallery, history_diagnostics, history_report_file, history_trace_file, history_cleaned_file], api_name=False, show_api=False)
        history_selector.change(fn=load_history_record, inputs=history_selector, outputs=[history_overview, history_report, history_gallery, history_diagnostics, history_report_file, history_trace_file, history_cleaned_file], api_name=False, show_api=False)
        refresh_history_qa_button.click(fn=refresh_history_qa_ui, inputs=[output_dir], outputs=[history_qa_run_ids], api_name=False, show_api=False)
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
