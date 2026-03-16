# Academic-Data-Agent

Academic-Data-Agent 是一个面向科研与学术场景的数据分析 Agent 项目。它既支持传统的 `csv/xls/xlsx` 表格分析，也支持对文本型 PDF 文献进行前置解析：提取论文背景、识别候选表格、选择主表进入正式定量分析，并结合其他候选表摘要与文献上下文生成结构化报告。

当前项目已经形成一套相对完整的分析工作流：数据接入、清洗、统计分析、图表生成、多轮审稿、运行追踪、Gradio Web 工作台与历史记录回看都已经接通，适合作为科研数据分析 Agent 的实验平台和可演示原型。

## 适用场景

- 表格型科研数据的自动清洗、分析与报告生成
- 学术论文 PDF 中表格数据的提取与结构化分析
- 需要保留完整运行轨迹、图表工件和审稿记录的分析任务
- 希望通过 Web 工作台查看历史运行结果、下载工件并快速复盘的场景

## 核心能力

- 表格分析主链：支持 `csv`、`xls`、`xlsx` 的清洗、统计分析、图表生成和 Markdown 报告输出
- PDF 前置解析：支持文本型 PDF 的正文提取、候选表格抽取、主表选择与背景上下文注入
- 多表综合语义：PDF 场景下，主表做正式定量分析，其他候选表作为上下文参与结果解释
- 自定义 ReAct 控制流：通过结构化 JSON 协议驱动分析步骤，而不是依赖脆弱的文本解析
- 学术统计治理：对小样本、效应量、置信区间、相关与因果表述做约束
- 多轮审稿机制：支持 `draft / standard / publication` 三档质量模式
- 可选视觉审稿：在高质量模式下可对生成图表进行独立视觉检查
- Gradio Web 工作台：支持文件上传、PDF 主表预览、实时日志、结果展示、历史运行浏览

## 系统结构

项目当前可以理解为四层结构：

1. 输入标准化层  
   负责区分表格文件与 PDF。表格直接进入分析主链；PDF 先做 `document_ingestion`，提取背景文本和候选表。

2. 分析执行层  
   由 `run_analysis(...)` 驱动，完成数据上下文构建、工具调度、本地 Python 分析、报告生成与工件落盘。

3. 审稿治理层  
   由文本 Reviewer 和可选视觉 Reviewer 组成，用于检查报告的图表、统计汇报与论证一致性。

4. 展示与交互层  
   提供 CLI 与 Gradio Web UI 两种入口，支持实时查看、历史记录浏览和工件下载。

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

项目使用 OpenAI-compatible 接口。你可以在根目录创建 `.env` 文件：

```env
LLM_MODEL_ID=deepseek-chat
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=your_api_key_here
LLM_TIMEOUT=120

# 可选：在线检索
TAVILY_API_KEY=your_tavily_api_key_here

# 可选：视觉审稿
VISION_LLM_MODEL_ID=your_vision_model
VISION_LLM_BASE_URL=https://your-vision-endpoint/v1
VISION_LLM_API_KEY=your_vision_api_key
VISION_LLM_TIMEOUT=120
```

### 3. 命令行运行

分析普通表格：

```bash
python main.py --data data/simple_data.xls
```

分析 PDF 文献：

```bash
python main.py --data your_paper.pdf --quality-mode publication
```

常用参数示例：

```bash
python main.py ^
  --data your_paper.pdf ^
  --quality-mode publication ^
  --latency-mode auto ^
  --document-ingestion-mode auto ^
  --vision-review-mode auto
```

### 4. 启动 Web 工作台

```bash
python gradio_app.py
```

启动后可在浏览器中上传表格或 PDF，查看实时日志、图表、报告、审稿结果与历史记录。

## 使用方式

### CLI

当前命令行入口支持的关键参数包括：

- `--data`
- `--output-dir`
- `--query`
- `--quality-mode`
- `--latency-mode`
- `--document-ingestion-mode`
- `--selected-table-id`
- `--vision-review-mode`

其中：

- `draft`：不审稿，直接输出初版结果
- `standard`：默认允许 1 次返修
- `publication`：默认允许 2 次返修，并可自动启用视觉审稿

### Python API

```python
from data_analysis_agent.agent_runner import run_analysis

result = run_analysis(
    data_path="data/simple_data.xls",
    quality_mode="standard",
    latency_mode="auto",
)

print(result.report_path)
print(result.cleaned_data_path)
print(result.trace_path)
print(result.review_status)
```

### Web 工作台

Gradio 前端当前支持：

- 文件上传
- PDF 候选表预览
- 主表手动覆盖选择
- 实时日志
- 运行总览
- 最终报告
- 图表画廊
- 审稿结果
- 历史记录回看

## PDF 分析的当前策略

当前版本对 PDF 的处理是保守而实用的：

- 优先支持文本型 PDF，不处理扫描件 OCR
- 从正文中提取摘要或前文，作为论文背景注入分析上下文
- 抽取多个候选表格，并记录页码、列头、数值列等摘要
- 默认按启发式选择一张主表进入正式定量分析
- 其他候选表不会再被忽略，而是作为上下文辅助解释主表结果

换句话说，PDF 场景下生成的是一份“文献背景 + 候选表摘要 + 主表分析”的综合报告，而不是单纯对一张表做孤立统计。

## 项目结构

```text
.
├─ data/                          示例数据
├─ outputs/                       运行产物与 Web 上传缓存
├─ src/
│  └─ data_analysis_agent/
│     ├─ agent_runner.py          主分析流程与审稿控制
│     ├─ config.py                运行配置
│     ├─ data_context.py          数据上下文构建
│     ├─ document_ingestion.py    PDF 文档解析与主表选择
│     ├─ prompts.py               Analyst / Reviewer Prompt
│     ├─ reporting.py             报告提取与落盘
│     ├─ vision_review.py         视觉审稿
│     └─ web/                     Gradio 工作台
├─ tests/                         单元测试
├─ gradio_app.py                  Web 启动入口
├─ main.py                        CLI 入口
├─ requirements.txt
└─ README.md
```

## 运行产物

每次运行都会在 `outputs/run_YYYYMMDD_HHMMSS/` 下生成独立工件，常见内容包括：

```text
outputs/run_YYYYMMDD_HHMMSS/
├─ data/
│  ├─ cleaned_data.csv
│  ├─ parsed_document.json
│  └─ extracted_tables/
├─ figures/
│  └─ review_round_1/
├─ logs/
│  ├─ agent_trace.json
│  ├─ document_ingestion.json
│  ├─ review_round_1_review.json
│  └─ review_round_1_visual_review.json
├─ review_round_1_report.md
└─ final_report.md
```

这些产物既用于调试与复盘，也会被前端历史记录页面自动读取。

## 当前边界

当前项目已经可以用于真实的表格与文本 PDF 分析演示，但仍然有一些明确边界：

- PDF 目前优先支持文本型文献，不处理扫描件 OCR
- 多表综合当前仍然只有“一张主表做正式定量分析”
- 视觉审稿是辅助审查，不是重新做一遍分析
- 在线检索与视觉模型依赖外部 API 配置
- 部分目录会产生较多运行产物，适合定期手动清理

## 测试与当前状态

当前项目已经覆盖：

- 文档解析
- 数据上下文
- 主分析流程
- Web 工作台
- 历史记录
- 审稿与视觉审稿

当前本地全量测试通过数为 **76**。

运行测试：

```bash
python -m unittest discover -s tests -v
```

## 贡献与使用建议

- 如果你主要分析表格数据，直接上传 `csv/xls/xlsx` 即可，路径最稳定、耗时也最短
- 如果你分析 PDF，建议先在 Web 前端预览候选表，再决定主表
- 如果你更重视速度，优先使用 `latency_mode=auto` 或 `fast`
- 如果你更重视报告质量与审稿约束，优先使用 `publication`

这个项目更适合作为一个持续演进的科研数据分析 Agent 平台，而不是单次脚本。它的价值不仅在于“跑出结果”，也在于能把中间过程、图表、审稿意见和运行痕迹完整保留下来。
