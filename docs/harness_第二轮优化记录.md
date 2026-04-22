# Harness 第二轮优化记录

## 1. 背景

本次优化直接基于第一轮 partial eval 复盘结果展开，复盘文档见：

- [harness_第一轮评测复盘报告.md](/C:/Users/pc/OneDrive/Desktop/agent/docs/harness_第一轮评测复盘报告.md)

第一轮结果暴露出的核心问题不是“系统不会分析”，而是：

1. `run_eval.py` 在长时间执行时几乎没有中途反馈，容易让人误以为程序卡住。
2. `TaskSpec` 中已经写了 `manual_expectations`，但原始 `run_eval.py` 只把 `task.question` 原样传给主链，等于任务级护栏没有真正参与分析。
3. 第一轮高频失败集中在：
   - `cleaning_contract_failure`
   - `citation_evidence_failure`
   - `chart_quality_failure`
   - `review_rejection`
4. 当前 analyst prompt 对“后续步骤显式重读 cleaned_data.csv”“图表必须有文字解释”“配对结构/异常值/缺失值处理必须说清”这几类要求，还不够硬。

因此，这一轮优化的目标不是扩展新功能，而是让第二轮评测更容易：

- 跑得可观测
- 题目护栏真正注入主链
- 更少因为执行契约和表达问题被 reviewer 卡住

## 2. 本轮改动概览

### 2.1 `run_eval.py`：从“黑盒批量跑”改成“可观测批量跑”

本轮对 [`eval/scripts/run_eval.py`](/C:/Users/pc/OneDrive/Desktop/agent/eval/scripts/run_eval.py) 做了 4 类改动：

1. **增加实时进度输出**
   - 脚本启动时立即打印当前 `report_dir`
   - 每个任务开始时打印：
     - 当前进度 `i / N`
     - `task_id`
     - 是否启用 `rag`
     - 是否启用 `memory`
   - 每个任务结束时打印：
     - 是否 `accepted`
     - `review_status`
     - `execution_audit_status`
     - 任务耗时

2. **增加任务级 query 增强**
   - 新增 `_build_eval_query(task)`
   - 不再只使用 `task.question`
   - 会把以下信息拼进最终 query：
     - `expected_methods`
     - `manual_expectations`
     - 任务级 `TASK_SPECIFIC_HINTS`
     - 通用 harness finish checklist

3. **增加中断时的 partial report 落盘**
   - 新增 `_write_aggregate_report(report_dir, summaries)`
   - 每完成一个任务，就刷新 `eval_run_report.json`
   - 即使中途 `KeyboardInterrupt`，也会保留当前已完成任务的聚合结果

4. **增加失败时的错误留痕**
   - 如果单个任务抛异常，会在 `report_dir` 下写一个 `<task_id>__error.json`
   - 便于后续回看“到底是哪一个任务先挂了”

### 2.2 `run_eval.py`：给 10 类任务补了 task-specific hints

针对第一轮暴露的问题，本轮给每个任务加了额外护栏，例如：

- `two_group_small_sample`
  - 小样本限制必须明确写出
  - 不允许把组间差异写成因果
- `missing_values_by_group`
  - 先解释缺失值模式和清洗规则
  - 说明缺失值如何影响结论置信度
- `time_series_trend_clean`
  - 尊重时间顺序
  - 不得把趋势硬写成机制结论
- `outlier_sensitive_measurement`
  - 明确是否保留 / 排除 / 仅标记异常值
  - 说明异常值对结论的影响
- `before_after_paired_measure`
  - 必须显式说明这是配对结构
  - 不能把配对数据当成两组独立样本
- `mixed_units_and_dirty_headers`
  - 必须先规范字段名和单位
  - 必须在后续步骤中显式重读规范 `cleaned_data.csv`

这些 hints 的作用是把“复盘里总结出来的问题”变成“第二轮评测前就写死在任务输入里的提醒”。

### 2.3 `prompts.py`：强化 analyst 的执行与表达护栏

本轮对 [`src/data_analysis_agent/prompts.py`](/C:/Users/pc/OneDrive/Desktop/agent/src/data_analysis_agent/prompts.py) 做了几处加强：

1. **强化两阶段契约**
   - 新增要求：
     - Stage 2 对 `cleaned_data.csv` 的重读必须发生在“后续 Python 步骤”中
     - 不能在一个 combined step 里保存、重读然后马上 finish

2. **强化数据结构与清洗说明**
   - 配对 / repeated-measures / pre-post 数据必须在 Methods 中说清
   - 若做过表头规范化、缺失值处理、异常值保留或剔除，也必须在报告中明确交代

3. **强化图表解释要求**
   - 新增硬要求：
     - 只生成图不解释，不允许 finish
     - 每个被引用的图都必须配直接文字解释

4. **强化 finish 前自检**
   - 新增 self-check：
     - Stage 1 已保存规范 `cleaned_data.csv`
     - 后续步骤显式重读
     - 图表都有解释
     - 报告写出主要限制或解释边界

5. **强化 observation prompt 的 finish blocker**
   - 如果当前可见证据无法证明“后续步骤显式重读 cleaned_data.csv”，不要 finish
   - 如果报告会出现“只有图，没有解释”的情况，不要 finish

这些修改的直接目标是压低第一轮高频出现的：

- `cleaning_contract_failure`
- `chart_quality_failure`
- 因表达不充分导致的 `review_rejection`

## 3. 测试与验证

本轮新增 / 更新了 prompt 相关断言，位置在：

- [tests/test_prompts.py](/C:/Users/pc/OneDrive/Desktop/agent/tests/test_prompts.py)

新增断言主要检查：

- system prompt 已包含：
  - `later Python step`
  - `paired or repeated-measures`
  - `bare image references`
- observation prompt 已包含：
  - 必须显式看到后续步骤重读 `cleaned_data.csv`
  - 没有图表文字解释时不能 finish

## 4. 本轮优化预期改善什么

本轮不是为了“让指标立刻变得漂亮”，而是为了让第二轮评测更接近真实能力上限。

预期改善点：

1. **减少误判为“程序卡住”**
   - 通过实时进度输出和 partial report 落盘，运行体验会明显更清楚。

2. **减少任务资产和主链脱节**
   - `manual_expectations`、`expected_methods` 和任务级护栏现在真正会进入分析 query。

3. **降低阶段执行审计失败概率**
   - 尤其是“没有在后续步骤显式重读 cleaned_data.csv”的问题。

4. **降低 reviewer 对图表和表达的打回概率**
   - 重点是把“图表必须配解释”“限制必须写出来”从软建议提升为硬要求。

## 5. 下一步建议

做完这轮优化后，最自然的下一步不是再继续改 prompt，而是：

1. 重新跑第二轮 eval
2. 对比第一轮 partial eval
3. 重点观察以下指标是否改善：
   - `cleaning_contract_failure` 数量
   - `chart_quality_failure` 数量
   - `review_rejection` 数量
   - `accepted` 数量
   - 平均步数
   - 平均耗时

如果第二轮结果依然显示 reviewer 层问题远多于契约问题，那么下一轮优化重点就应该从 analyst prompt 转向：

- reviewer critique 到 failure taxonomy 的映射逻辑
- task-specific evaluation rubric
- 图表表达模板的进一步标准化
