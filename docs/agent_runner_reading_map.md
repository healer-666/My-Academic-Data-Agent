# agent_runner.py 阅读地图

这份文档只解决一个问题：`agent_runner.py` 很长，第一次读时应该从哪里下手。

建议不要从第 1 行硬读到最后一行。更好的方式是先把它当成一个端到端 orchestration 文件：它不负责某一个算法细节，而是把配置、数据上下文、记忆、RAG、工具执行、审计、审稿、持久化串成一条主链路。

## 一句话主线

```text
配置与运行目录 -> 数据上下文 -> memory/RAG -> ReAct 分析 -> 执行审计与报告契约 -> 审稿返修 -> 记忆写回 -> 最终结果
```

## 先读哪些函数

1. `run_analysis(...)`
   - 主入口，负责串联完整工作流。
   - 面试时可以把它称为 orchestration function。

2. `ScientificReActRunner.run_with_messages(...)`
   - 真正驱动 analyst ReAct 循环。
   - 重点看它如何调用 LLM、解析 tool call、执行工具、记录 trace。

3. `_validate_artifacts(...)`
   - 检查最终工件状态。
   - 它影响 workflow completion、trace、summary 和 memory writeback。

4. `_save_agent_trace(...)`
   - 把一次运行的关键证据写入 trace。
   - 这是理解可复现性和调试能力的入口。

5. `_build_reviewer_task(...)`
   - 构造审稿人看到的上下文。
   - 重点看 report、trace、artifact validation、evidence register、memory、execution audit、report contract 是如何汇总的。

6. `build_revision_brief(...)`
   - 把硬验证或 reviewer 的拒绝意见转成下一轮 analyst 的修复指令。
   - 这是 self-revision loop 的关键连接点。

## run_analysis 的阅读分段

### 1. Config Stage

位置：`run_analysis(...)` 开头到 `run_context` 构建。

这一段主要做：

- 加载 `.env` 和 runtime config。
- 解析 `quality_mode`、`latency_mode`、`vision_review_mode`、`symbolic_profile`。
- 判断 reviewer 是否启用。
- 创建 run directory、data/log/figure/trace 路径。

读这一段时只要记住：它决定本轮运行的“模式”和“产物落在哪里”。

### 2. Context Stage

位置：输入标准化、document ingestion、`build_data_context(...)`。

这一段主要做：

- 确认输入数据路径和格式。
- 对表格输入做标准化。
- 构建 `DataContextSummary`。
- 判断是否启用 fast path 和在线搜索。

这里的重点是：`data_context` 只是让模型理解数据结构，不是正式统计计算。正式计算必须由 Python 工具读取完整数据完成。

### 3. Memory Stage

位置：`ProjectMemoryService` 和 `FailureMemoryService` retrieval。

这一段主要做：

- 检索历史成功经验。
- 检索历史失败教训。
- 把两类 memory 格式化为 prompt context。

面试时可以强调：成功记忆和失败记忆分开，是为了避免把失败模式误当作可复用经验。

### 4. Retrieval Stage

位置：`KnowledgeContextProvider`、`RagService.index_files(...)`、`RagService.retrieve(...)`。

这一段主要做：

- 如果用户上传知识资料，先索引到本地知识库。
- 根据数据上下文和用户问题构造检索 query。
- 做 dense + keyword + rerank。
- 生成 evidence register，并注入 analyst prompt。

注意：RAG 发生在 analyst 正式分析之前。检索结果不是直接当结论，而是作为可引用证据进入 prompt。

### 5. Analysis Stage

位置：`for review_round in range(...)` 内，构建 system prompt 到 `current_runner.run_with_messages(...)`。

这一段主要做：

- 为当前轮构造 analyst system prompt。
- 注入 query、knowledge bundle、data context、run context。
- 运行 ReAct loop。
- 收集每一步 tool trace。
- 从模型输出中抽取 report 和 telemetry。

这是模型真正“做分析”的地方。

### 6. Verification Stage

位置：分析输出之后到 reviewer 之前。

这一段主要做：

- `audit_stage_execution(...)` 检查阶段执行是否合规。
- `check_report_contract(...)` 检查报告契约。
- 保存 round report 和 trace。
- `_validate_artifacts(...)` 检查清洗数据、报告、trace、telemetry、stage audit 状态。

关键点：三种 `symbolic_profile` 都会跑 verifier 作为 posthoc metrics；只有 `full` 会把失败转成 blocking rejection 和 revision brief。

### 7. Review Stage

位置：`workflow_tracker.transition(WorkflowState.REVIEW)` 之后。

这一段主要做：

- 可选执行视觉审稿。
- 构造 reviewer prompt。
- 让 reviewer 判断 Accept/Reject。
- 如果 Reject，用 `build_revision_brief(...)` 生成下一轮修复指令。

这里是 LLM reviewer 层；在它之前，执行审计和报告契约已经先做了硬检查。

### 8. Persistence Stage

位置：review loop 结束后。

这一段主要做：

- 如果接受且 workflow complete，写入成功 memory。
- 如果完整失败，写入 failure memory。
- 保存最终 trace。
- 生成 `AnalysisRunResult`。
- 写 `run_summary.json`。

面试时可以说：持久化不是简单保存报告，而是保存报告、trace、telemetry、审计结果、审稿记录和 memory 写回状态。

## 推荐阅读顺序

第一次读：

1. 只读 `run_analysis` 的 stage 注释和每段开头。
2. 再读 `ScientificReActRunner.run_with_messages(...)`。
3. 再读 `audit_stage_execution(...)` 和 `check_report_contract(...)` 的调用位置。
4. 最后读 memory/RAG 的细节。

第二次读：

1. 跟一条真实 trace。
2. 对照 `agent_trace.json` 看每个字段在哪里写入。
3. 对照 `run_summary.json` 看哪些字段面向展示和评测。

第三次读：

1. 专门读 `symbolic_profile` 三组消融。
2. 对照 `symbolic_rules.py`。
3. 对照 `eval/scripts/run_symbolic_ablation.py`。

## 面试表达模板

如果老师问 `agent_runner.py` 为什么这么长，可以这样答：

> 这个文件目前承担的是端到端 orchestration：它把配置、数据上下文、记忆检索、RAG、ReAct 分析、symbolic verification、review loop 和结果持久化串起来。为了保证实验行为稳定，我没有优先做大规模拆分，而是先用 stage 注释和阅读地图明确边界。后续更适合按 stage context 做行为保持型重构。

如果老师问神经符号部分在哪里，可以这样答：

> Neural 部分主要是 LLM、embedding、RAG 和 memory；symbolic 部分主要是统计规则、report contract、AST execution audit、blocking check 和 revision brief。`full` profile 会把 symbolic verifier 的失败反馈给 LLM 进入下一轮修正，`prompt_only` 和 `none` 只做 posthoc evaluation，用来做消融对照。
