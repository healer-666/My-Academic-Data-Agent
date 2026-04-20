<div align="center">
<h1>Academic-Data-Agent</h1>

**面向科研与学术场景的结构化数据分析智能体工作台**

[![Python Version](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](#)

[特点](#-核心特点) · [架构](#-系统架构) · [快速开始](#-快速开始) · [使用指南](#-使用指南) · [项目结构](#-项目结构)
</div>

## 项目简介
**Academic-Data-Agent** 是一个基于 `hello-agents` 二次开发的分析型智能体项目。当前版本的正式主线已经收束为“**结构化表格数据分析 + 历史结果追问**”，目标不是做一个什么都能接的通用 Agent 平台，而是把一条真正可运行、可追溯、可复盘的分析流程打磨清楚。

当前项目重点解决的是这件事：

- 用户上传一份结构化表格数据
- 系统先理解数据，再补充外部参考资料和项目历史经验
- 进入受控分析循环，调用 Python 完成清洗、统计、绘图和报告生成
- 通过阶段执行审计，确保正式分析基于全量清洗后数据，而不是只靠摘要“脑补”
- 生成报告、图表、运行轨迹和审稿记录
- 把成功经验与失败教训分层沉淀，并支持对历史分析结果继续追问

当前项目支持：

- 表格数据输入：`csv / xls / xlsx`
- 受控分析工作流：工具调用、运行轨迹、异常回退与审稿返修
- 工程化 RAG：查询改写、混合检索、结构化切块、重排与证据登记
- 阶段执行审计：强校验 `cleaned_data.csv` 的生成与重读
- 成功经验 / 失败教训 / 外部参考资料分层存储
- 历史问答：围绕历史运行结果做单次追问或跨运行对比
- Gradio 工作台、历史回放与工件下载

### 适用场景

- 学术或科研表格数据的自动清洗、统计分析与报告生成
- 需要保留图表、轨迹、审稿记录和历史回放的分析任务
- 希望对历史分析结果继续提问、对比和复盘的项目型工作流

---

## 核心特点

### 1. 主线清晰：聚焦结构化表格分析

- 当前正式输入主线只面向结构化表格数据
- 上传后直接进入数据上下文构建、检索增强、分析执行与审稿流程
- 仓库中仍保留部分旧的 PDF 兼容代码，但 PDF 已不再是当前版本的正式入口主线

### 2. 受控分析，而不是自由聊天

- 分析主循环采用 **ReAct 风格**：逐步决策、调用工具、读取观察结果、继续推进
- 不是纯聊天式回答，也不是“先出完整计划再机械执行”的 plan-and-execute
- 外层还有审稿返修和阶段执行审计，因此整个系统更像“分析员 + 审稿人 + 质检员”

### 3. 真正基于全量数据分析

- `data_context` 只给模型提供字段、规模、样例等压缩摘要，负责“看懂这是什么数据”
- 正式统计分析和绘图必须通过 Python 工具重新读取本地文件完成
- 当前加入了**阶段执行审计**，会检查是否明确生成并重读 `cleaned_data.csv`
- 如果无法证明正式分析基于清洗后的全量数据，该轮会被硬拦截，不能通过审稿

### 4. RAG 负责外部依据，不负责“记住一切”

- 当前 RAG 的职责是提供外部参考资料、背景知识和证据片段
- 它服务于分析解释、报告引用和历史问答检索底座
- 它不直接存放运行失败经验，也不替代项目记忆

### 5. 记忆分层更清楚

- **成功经验**：只沉淀最终通过审稿、工作流完整的运行经验
- **失败教训**：单独沉淀完整失败运行中的负向约束和禁忌清单
- **外部参考资料**：单独进入知识库，用于 RAG 检索
- **运行档案**：每次运行都保留完整报告、轨迹、图表和审稿记录

### 6. 历史问答不是“重新分析一次”

- 历史问答读取的是历史运行工件，而不是重新执行新的数据分析代码
- 支持围绕某次运行解释方法、图表、结论和审稿意见
- 也支持跨多次运行做对比总结，并对非 `accepted` 的来源显式标注状态

### 7. 有工作台，不只是脚本

- Web 工作台支持发起分析、查看结果、浏览历史与继续追问
- 自动保存报告、图表、轨迹、审稿记录和知识库状态
- 支持历史记录浏览与工件下载，便于复盘和展示

---

## 系统架构

当前项目可以理解为五层结构：

### 1. 输入与数据上下文层

- 接收结构化表格输入
- 构建 `data_context`
- 提供字段、类型、规模、样例行和数据警告

### 2. 检索与记忆层

- 成功经验检索：提供正向做法、稳定偏好和已验证约束
- 失败教训检索：提供负向约束、常见错误和额外检查项
- RAG 检索：提供外部参考资料和证据片段

### 3. 分析执行层

- `run_analysis(...)` 串联整条主链路
- analyst loop 负责多步分析与工具调用
- Python 工具执行真实的数据清洗、统计和绘图

### 4. 治理与审计层

- 阶段执行审计：检查是否真的基于 `cleaned_data.csv` 做正式分析
- reviewer：检查结论、图表、证据与引用是否可靠
- artifact validation：检查关键工件是否完整

### 5. 展示与追问层

- CLI 负责命令行运行
- Gradio 工作台负责上传、结果展示、历史回放和历史问答

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

# 可选：联网搜索
TAVILY_API_KEY=your_tavily_api_key_here

# 可选：向量检索、成功经验、失败教训、历史问答检索
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
- `--vision-review-mode`
- `--vision-max-images`
- `--vision-max-image-side`

### 质量模式

- `draft`：不走审稿，直接输出草稿
- `standard`：默认允许 1 轮返修
- `publication`：默认允许 2 轮返修，并可自动启用视觉审稿

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
print(result.failure_memory_writeback_status)
```

### Web 工作台能力

- 上传结构化表格
- 上传可沉淀的参考资料
- 配置是否启用外部参考资料检索
- 配置是否启用成功经验 / 失败教训回忆
- 查看实时进度、结果摘要、图表和审稿状态
- 浏览历史记录并继续追问

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
├── memory/                        外部参考资料库、成功经验与失败教训
├── outputs/                       运行产物与 Web 上传缓存
├── src/
│   └── data_analysis_agent/
│       ├── agent_runner.py        主分析流程与编排入口
│       ├── artifact_service.py    工件落盘与运行元数据汇总
│       ├── config.py              运行配置
│       ├── data_context.py        数据上下文构建
│       ├── execution_audit.py     全量数据使用阶段审计
│       ├── history_qa.py          历史问答服务
│       ├── knowledge_context.py   记忆 / RAG / 证据注入层
│       ├── prompts.py             Analyst / Reviewer Prompt
│       ├── reporting.py           报告提取、引用解析与落盘
│       ├── review_service.py      审稿任务构建与日志落地
│       ├── rag/                   外部参考资料检索子系统
│       ├── memory/                成功经验与失败教训子系统
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
│   └── cleaned_data.csv
├── figures/
├── logs/
│   ├── agent_trace.json
│   ├── review_round_1_review.json
│   └── review_round_1_visual_review.json
├── review_round_1_report.md
└── final_report.md
```

`agent_trace.json` 当前会记录：

- 工作流状态与事件流
- analyst 每步工具调用摘要
- Python 工具的完整输入代码
- 阶段执行审计结果
- RAG 检索与证据登记摘要
- 成功经验 / 失败教训的检索与写回状态
- 审稿历史与最终结论

---

## 当前边界

- 当前默认正式入口只支持结构化表格数据，不再把 PDF 作为正式输入主线
- 历史问答只读取历史工件，不会重新执行新的数据分析代码
- 联网搜索、向量检索和视觉审稿依赖外部模型或 API 配置
- 当前更像“分析工作台 + 历史追问系统”，不是通用多工具智能体平台
