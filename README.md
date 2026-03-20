<div align="center">
<h1>Academic-Data-Agent</h1>

**面向科研与学术场景的数据分析 Agent 工作台**

[![Python Version](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](#)

[特性](#-核心特性) • [架构](#-系统架构) • [快速开始](#-快速开始) • [使用指南](#-使用指南) • [项目结构](#-项目结构)
</div>

## 📝 项目简介

**Academic-Data-Agent** 是一个基于 HelloAgents 思路构建的科研数据分析 Agent 项目，目标是把“数据接入、分析执行、审稿治理、结果展示”串成一条可复现、可追踪、可演示的完整工作流。

它既支持传统的 `csv / xls / xlsx` 表格数据，也支持文本型 PDF 文献的前置解析：提取论文背景、识别候选表格、选择主表进入正式定量分析，并结合其他候选表摘要与文献上下文生成结构化报告。

### 适用场景

- 科研表格数据的自动清洗、统计分析与报告生成
- 学术论文 PDF 中表格数据的抽取与结构化分析
- 需要保留运行轨迹、图表工件、审稿记录的分析任务
- 希望通过 Web 工作台快速查看历史运行结果与工件的场景

---

## ✨ 核心特性

### 1. 两类输入统一接入

- **表格输入**：直接分析 `csv / xls / xlsx`
- **PDF 输入**：先做文档解析，再进入正式分析主链

### 2. PDF 多表综合分析

- 自动抽取候选表格并选择主表
- 主表负责正式定量分析
- 其他候选表作为上下文证据参与报告解释
- 自动注入论文摘要或前文背景，增强变量与任务语义理解

### 3. 自定义分析控制流

- 使用结构化 JSON 协议驱动分析步骤
- 避免纯文本 Agent 在工具调用和结果解析上的脆弱性
- 支持本地 Python 分析、图表生成与中间工件落盘

### 4. 学术治理与审稿机制

- 内置小样本与统计汇报约束
- 支持 `draft / standard / publication` 三档质量模式
- 支持文本 Reviewer
- 支持可选视觉 Reviewer，对图表可读性进行额外检查

### 5. 完整的工作台与历史记录

- Gradio Web UI 支持上传、预览、运行、回看
- 自动保存 `cleaned_data.csv`、报告、图表、trace、review logs
- 支持历史记录浏览与工件下载

---

## 🏗️ 系统架构

当前项目可以理解为四层结构：

### 1. 输入标准化层

- 区分表格文件与 PDF
- PDF 先进入 `document_ingestion`
- 输出主表、候选表摘要和文献背景

### 2. 分析执行层

- 由 `run_analysis(...)` 驱动主流程
- 构建数据上下文
- 调用本地 Python 工具完成清洗、分析、绘图与报告生成

### 3. 审稿治理层

- 文本 Reviewer 检查报告逻辑、统计表述与工件一致性
- 可选视觉 Reviewer 检查图表展示质量

### 4. 展示交互层

- CLI 负责命令行运行与摘要展示
- Gradio Web UI 负责文件上传、候选表预览、实时日志、结果回看与历史记录浏览

---

## 🚀 快速开始

### 环境要求

- Python 3.10+
- 建议使用虚拟环境

### 安装依赖

```bash
pip install -r requirements.txt
```

### 配置环境变量

在项目根目录创建 `.env` 文件：

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

### 命令行运行

分析表格：

```bash
python main.py --data data/simple_data.xls
```

分析 PDF：

```bash
python main.py --data your_paper.pdf --quality-mode publication
```

### 启动 Web 工作台

```bash
python gradio_app.py
```

---

## 📖 使用指南

### CLI 常用参数

- `--data`
- `--output-dir`
- `--query`
- `--quality-mode`
- `--latency-mode`
- `--document-ingestion-mode`
- `--selected-table-id`
- `--vision-review-mode`

### 质量模式

- `draft`：不审稿，直接输出初版
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

### Web 工作台能力

- 文件上传
- PDF 候选表预览
- 主表手动覆盖选择
- 实时日志
- 运行总览
- 最终报告
- 图表画廊
- 审稿结果
- 历史记录回看

---

## 🖼️ 界面展示

![主界面](images/image1.png)
---
![历史记录](images/image2.png)
---
![运行日志记录](images/image3.png)

---

## 📂 项目结构

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

---

## 📦 运行产物

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

---

## 📌 当前边界

- PDF 当前优先支持文本型文献，不处理扫描件 OCR
- PDF 多表综合目前仍然是“一张主表做正式定量分析”
- 视觉审稿是辅助审查，不是重新执行整套分析
- 在线检索与视觉模型依赖外部 API 配置

---

## 🧪 测试状态

当前项目已经覆盖：

- 文档解析
- 数据上下文
- 主分析流程
- Web 工作台
- 历史记录
- 审稿与视觉审稿

当前本地全量测试通过数为 **76**。

```bash
python -m unittest discover -s tests -v
```

---

## 🤝 使用建议

- 表格任务优先直接上传 `csv/xls/xlsx`，路径最稳定、耗时也最短
- PDF 任务建议先在 Web 前端预览候选表，再决定主表
- 更重视速度时优先使用 `latency_mode=auto` 或 `fast`
- 更重视报告质量与审稿约束时优先使用 `publication`

Academic-Data-Agent 更适合作为一个持续演进的科研数据分析 Agent 平台，而不是一次性脚本。它不仅追求“跑出结果”，也重视中间过程、图表、审稿意见与运行痕迹的完整保留。

👥 致谢

### 特别鸣谢

* **Datawhale 社区**：提供学习资源与支持
* **Hello-Agents 项目**：提供框架基础
* **OpenAI & DeepSeek & Qwen**：LLM 技术支持

* * *
