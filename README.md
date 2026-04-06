<div align="center">
<h1>Academic-Data-Agent</h1>

**面向科研与学术场景的数据分析 Agent 工作台**

[![Python Version](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](#)

[特点](#-核心特点) · [架构](#-系统架构) · [快速开始](#-快速开始) · [使用指南](#-使用指南) · [项目结构](#-项目结构)
</div>

## 项目简介

**Academic-Data-Agent** 是一个基于 `hello-agents` 二次开发的学术数据分析 Agent 项目，目标是把“输入接入、分析执行、证据归因、审稿治理、结果回放”串成一条可复现、可追踪、可展示的完整流程。

当前项目支持：

- 表格数据输入：`csv / xls / xlsx`
- 文本型 PDF 的背景提取、候选表识别与主表选择
- 工程化 RAG：`query rewrite + hybrid retrieval + structured chunking + rerank`
- evidence register 与报告行内短引用
- 文本 reviewer 与可选 visual reviewer
- Project Memory：accepted run 的项目级经验记忆
- Gradio 工作台、历史记录回放与工件下载

### 适用场景

- 学术表格数据的自动清洗、统计分析与报告生成
- 论文 PDF 中表格数据的抽取与结构化分析
- 需要保留 trace、图表、审稿记录与历史回放的分析任务

---

## 核心特点

### 1. 两类输入统一接入

- 表格文件可直接进入结构化分析
- PDF 会先做文档解析，再进入正式分析主链

### 2. PDF 多表综合分析

- 自动识别候选表并选择主表
- 主表负责正式定量分析
- 其他候选表作为背景证据参与解释

### 3. 受控分析工作流

- 通过结构化协议驱动分析循环
- 支持本地 Python 工具、图表生成与中间工件落盘
- 有 reviewer 治理，不是单轮自由聊天

### 4. 工程化 RAG 与证据归因

- 本地知识库
- hybrid retrieval
- structured chunking
- PDF 表格增强
- evidence register
- 行内短引用

### 5. Project Memory

- 只对 accepted run 写入长期 memory
- 分析前与审稿前可回忆项目级偏好与约束

### 6. 完整工作台与历史记录

- Web 工作台支持上传、预览、运行、回看
- 自动保存报告、图表、trace、review logs
- 支持历史记录浏览与工件下载

---

## 系统架构

当前项目可以理解为五层结构：

### 1. 输入标准化层

- 区分表格输入与 PDF 输入
- PDF 先进入 `document_ingestion`
- 输出主表、候选表摘要和背景信息

### 2. 分析执行层

- `run_analysis(...)` 驱动主流程
- analyst loop 负责多步分析与工具调用

### 3. RAG 与证据层

- 检索知识文档
- 生成 evidence register
- 约束报告中的知识性引用

### 4. 审稿治理层

- 文本 reviewer
- 可选 visual reviewer
- 证据一致性检查

### 5. 展示交互层

- CLI 负责命令行运行
- Gradio 工作台负责上传、预览、结果展示与历史回放

---

## 快速开始

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

# 可选：RAG embedding
EMBEDDING_MODEL_ID=text-embedding-3-small
EMBEDDING_BASE_URL=https://api.openai.com/v1
EMBEDDING_API_KEY=your_embedding_api_key
EMBEDDING_TIMEOUT=120

# 可选：视觉审稿
VISION_LLM_MODEL_ID=your_vision_model
VISION_LLM_BASE_URL=https://your-vision-endpoint/v1
VISION_LLM_API_KEY=your_vision_api_key
VISION_LLM_TIMEOUT=120
```

### 命令行运行

分析表格：

```bash
python main.py --data data/simple_data.xlsx
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

## 使用指南

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

- `draft`：不审稿，直接输出草稿
- `standard`：默认允许 1 次返修
- `publication`：默认允许 2 次返修，并可自动启用视觉审稿

### Python API

```python
from pathlib import Path

from data_analysis_agent.agent_runner import run_analysis

result = run_analysis(
    Path("data/simple_data.xlsx"),
    quality_mode="standard",
    latency_mode="auto",
    use_rag=True,
    use_memory=True,
    memory_scope_key="demo-project",
)

print(result.report_path)
print(result.trace_path)
print(result.review_status)
print(result.rag_status)
print(result.memory_writeback_status)
```

### Web 工作台能力

- 文件上传
- 知识文档上传
- PDF 候选表预览
- 主表手动覆盖选择
- `use_rag` 开关
- `use_memory` 开关
- `memory_scope_label`
- 实时日志
- 运行总览
- 最终报告
- 图表展示
- 审稿结果
- 历史记录回看

### 文档索引

- [核心代码学习手册](./docs/核心代码学习手册.md)
- [项目概念审计](./docs/项目概念审计.md)
- [项目改进路线图](./docs/项目改进路线图.md)
- [项目主链路拆解](./docs/项目主链路拆解.md)
- [令牌、上下文与审稿说明](./docs/令牌、上下文与审稿说明.md)

---

## 项目结构

```text
.
├── data/                          示例数据
├── docs/                          技术说明与学习文档
├── memory/                        本地知识库与项目记忆
├── outputs/                       运行产物与 Web 上传缓存
├── src/
│   └── data_analysis_agent/
│       ├── agent_runner.py        主分析流程与审稿控制
│       ├── config.py              运行配置
│       ├── data_context.py        数据上下文构建
│       ├── document_ingestion.py  PDF 文档解析与主表选择
│       ├── knowledge_context.py   Memory / RAG / Evidence 注入层
│       ├── prompts.py             Analyst / Reviewer Prompt
│       ├── reporting.py           报告提取、引用解析与落盘
│       ├── review_service.py      审稿任务构建与日志落地
│       ├── rag/                   RAG 子系统
│       ├── memory/                Project Memory 子系统
│       ├── vision_review.py       视觉审稿
│       └── web/                   Gradio 工作台
├── tests/                         单元测试
├── gradio_app.py                  Web 启动入口
├── main.py                        CLI 入口
├── requirements.txt
└── README.md
```

---

## 运行产物

每次运行都会在 `outputs/run_YYYYMMDD_HHMMSS/` 下生成独立工件，常见内容包括：

```text
outputs/run_YYYYMMDD_HHMMSS/
├── data/
│   ├── cleaned_data.csv
│   ├── parsed_document.json
│   └── extracted_tables/
├── figures/
├── logs/
│   ├── agent_trace.json
│   ├── document_ingestion.json
│   ├── review_round_1_review.json
│   └── review_round_1_visual_review.json
├── review_round_1_report.md
└── final_report.md
```

`agent_trace.json` 当前会记录：

- workflow 状态
- event stream
- RAG payload
- evidence coverage
- memory retrieval / writeback
- review history

---

## 当前边界

- PDF 当前优先支持文本型文献，不处理复杂 OCR
- PDF 多表综合目前仍然是“一张主表做正式定量分析”
- visual reviewer 是辅助审查，不是重新执行整套分析
- 在线检索、embedding 与视觉模型依赖外部 API 配置
