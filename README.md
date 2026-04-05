# Academic-Data-Agent

面向科研与学术数据分析场景的 `hello-agents` 二次开发项目。它不是通用聊天机器人，而是一套围绕“数据/文献输入 -> 分析执行 -> RAG 与证据归因 -> 审稿治理 -> 结果回放”的分析型 Agent 工作流系统。

当前文档已按 2026-04-05 的代码状态更新，和仓库中的 RAG、证据链、Project Memory、Web 工作台实现保持一致。

## 项目定位

这个项目最准确的定位是：

> 一个基于 `hello-agents` 底座、面向科研数据分析任务的受控 Agent workflow system。

这里的重点不是“用了多少模型”，而是：

- 用显式工作流而不是自由聊天式 Agent 做数据分析
- 用结构化工具协议约束模型行为
- 用 RAG、证据归因、reviewer、trace 提高可信度
- 用 Project Memory 复用已接受运行中的经验和偏好

## 当前能力概览

### 1. 双输入主线

- 支持 `csv / xls / xlsx`
- 支持 PDF 文档 ingestion
- PDF 路径可提取候选表、选择主表、生成 `parsed_document.json`

### 2. 受控分析工作流

- Analyst 主流程由 [`run_analysis(...)`](/C:/Users/pc/OneDrive/Desktop/agent/src/data_analysis_agent/agent_runner.py) 编排
- 外层状态机固定为 `ingest -> context -> analyze_round -> validate -> review -> finalize`
- 复杂逻辑已经从单体 runner 拆分到 `artifact_service / review_service / tooling_service / workflow_service`

### 3. RAG v3 早期版

- 本地 Chroma 持久化知识库
- OpenAI-compatible embeddings
- `query rewrite + hybrid retrieval + rule rerank`
- `text_section + table_summary` 结构化 chunk
- PDF 主表/候选表的临时检索增强
- Web 端支持知识文档上传

### 4. 证据归因

- 最终注入的 RAG chunk 会生成稳定 `evidence_id`
- Prompt 中包含 `<Retrieved_Evidence_Register>`
- 知识性解释要求带行内短引用
- Reviewer 会对缺失引用、无效引用、错配引用进行硬性检查

### 5. Project Memory

- 仅对 `accepted` 运行写回长期 memory
- 写回内容是精炼条目，不是整份旧报告全文
- 分析前和审稿前都能按 `memory_scope_key` 回忆项目经验
- Memory 和 RAG 证据层分开建模，不混淆角色

### 6. 可回放的工作台

- Gradio 单页工作台
- 历史运行记录与结果回看
- 实时日志、运行摘要、审稿结果、trace、下载工件
- History 页可查看旧 run 的高层状态

## 架构总览

```text
输入文件
  -> document_ingestion（仅 PDF）
  -> data_context / knowledge_context
  -> project memory recall
  -> RAG retrieval + rerank + evidence register
  -> ScientificReActRunner
  -> ToolRegistry / PythonInterpreterTool / TavilySearchTool
  -> report + telemetry + trace
  -> reviewer / visual reviewer
  -> accepted memory writeback
  -> CLI / Web / history
```

### 关键模块

- [`agent_runner.py`](/C:/Users/pc/OneDrive/Desktop/agent/src/data_analysis_agent/agent_runner.py)
  主编排入口，负责运行时 orchestration
- [`document_ingestion.py`](/C:/Users/pc/OneDrive/Desktop/agent/src/data_analysis_agent/document_ingestion.py)
  PDF 输入标准化
- [`knowledge_context.py`](/C:/Users/pc/OneDrive/Desktop/agent/src/data_analysis_agent/knowledge_context.py)
  用户意图、memory、reference、RAG、evidence register 的统一注入层
- [`rag/`](/C:/Users/pc/OneDrive/Desktop/agent/src/data_analysis_agent/rag)
  RAG 子系统
- [`memory/`](/C:/Users/pc/OneDrive/Desktop/agent/src/data_analysis_agent/memory)
  项目级经验记忆子系统
- [`review_service.py`](/C:/Users/pc/OneDrive/Desktop/agent/src/data_analysis_agent/review_service.py)
  文本审稿构造与日志落地
- [`web/`](/C:/Users/pc/OneDrive/Desktop/agent/src/data_analysis_agent/web)
  Gradio 工作台和历史回看

## 快速开始

### 1. 环境要求

- Python 3.10+
- 建议使用虚拟环境

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置 `.env`

至少需要主模型配置：

```env
LLM_MODEL_ID=deepseek-chat
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_API_KEY=your_api_key
LLM_TIMEOUT=120
```

可选能力：

```env
TAVILY_API_KEY=your_tavily_key

EMBEDDING_MODEL_ID=text-embedding-3-small
EMBEDDING_BASE_URL=https://api.openai.com/v1
EMBEDDING_API_KEY=your_embedding_key
EMBEDDING_TIMEOUT=120

VISION_LLM_MODEL_ID=your_vision_model
VISION_LLM_BASE_URL=https://your-vision-endpoint/v1
VISION_LLM_API_KEY=your_vision_key
VISION_LLM_TIMEOUT=120
```

### 4. 命令行运行

分析表格：

```bash
python main.py --data data/simple_data.xlsx --quality-mode standard
```

分析 PDF：

```bash
python main.py --data data/your_paper.pdf --quality-mode publication --document-ingestion-mode text_only
```

### 5. 启动 Web 工作台

```bash
python gradio_app.py
```

## Python API

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

## Web 端当前可用能力

- 数据文件上传
- 知识文档上传
- `use_rag` 开关
- `use_memory` 开关
- `memory_scope_label`
- PDF 候选表预览与主表选择
- 实时日志
- 运行摘要
- 最终报告
- 图表画廊
- 审稿结果
- Trace / 诊断
- 工件下载
- 历史记录回看

## RAG 与 Memory 的当前边界

### RAG 当前已实现

- 本地知识库
- Hybrid retrieval
- Structured chunking
- PDF / 表格增强
- 证据归因与 reviewer 校验

### Memory 当前已实现

- 项目级 scope
- accepted run 写回
- 分析前回忆
- 审稿前回忆

### 当前还没做的

- 独立知识问答模式
- 多跳动态检索
- Cross-encoder / LLM reranker
- 正式长期会话记忆网络
- 完整离线 RAG 评测平台

## 运行产物

每次运行都会生成独立目录：

```text
outputs/run_YYYYMMDD_HHMMSS/
├─ data/
│  ├─ cleaned_data.csv
│  ├─ parsed_document.json
│  └─ extracted_tables/
├─ figures/
│  └─ review_round_*/
├─ logs/
│  ├─ agent_trace.json
│  ├─ document_ingestion.json
│  ├─ review_round_*_review.json
│  └─ review_round_*_visual_review.json
├─ final_report.md
└─ review_round_*_report.md
```

其中 [`agent_trace.json`](/C:/Users/pc/OneDrive/Desktop/agent/outputs) 现在会记录：

- workflow states
- event stream
- RAG payload
- evidence coverage
- memory retrieval / writeback
- review history

## 测试

当前仓库测试基线已更新到：

```bash
python -m unittest discover -s tests -q
```

最近一次全量结果为 `104` 个测试通过。

覆盖重点包括：

- agent runner
- document ingestion
- RAG services
- memory services
- reviewer / evidence attribution
- web service / web app
- history / runtime helpers

## 文档索引

- [核心代码学习手册](/C:/Users/pc/OneDrive/Desktop/agent/docs/core-code-learning-manual.md)
- [项目概念审计](/C:/Users/pc/OneDrive/Desktop/agent/docs/project-concept-audit.md)
- [项目改进路线图](/C:/Users/pc/OneDrive/Desktop/agent/docs/project-improvement-roadmap.md)
- [主链路拆解](/C:/Users/pc/OneDrive/Desktop/agent/docs/project-mainline-analysis.md)
- [Token / Context / Review 说明](/C:/Users/pc/OneDrive/Desktop/agent/docs/token-context-review-explainer.md)

## 一句话总结

这个项目现在最合适的描述不是“做了个数据分析聊天机器人”，而是：

> 基于 `hello-agents` 做了一个带有 PDF ingestion、工程化 RAG、证据归因、审稿治理和项目级 memory 的科研数据分析 Agent 工作台。
