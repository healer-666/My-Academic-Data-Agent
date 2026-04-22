# Harness 第一轮评测复盘报告

## 1. 评测范围

- 评测时间：`2026-04-21`
- 结果来源目录：[`eval/reports/20260421_083207`](/C:/Users/pc/OneDrive/Desktop/agent/eval/reports/20260421_083207)
- 当前纳入复盘的任务数：`8`
- 未纳入本轮统计的任务：
  - `reference_guideline_lookup`
  - `memory_constrained_repeat_task`
- 说明：
  - 本轮是 **partial eval**，不是完整的 `seed_v1 baseline`
  - 终止原因不是主链崩溃，而是在后续任务的模型请求阶段被手动中断

## 2. 整体结果概览

本轮 8 个任务已经足够反映当前 harness 的真实状态。系统并不是“不会做分析”，而是已经进入了一个更难也更有价值的阶段：主链能够跑通不少任务，但在 **全量数据契约、证据表达、图表表达和审稿通过率** 上还没有稳定下来。

核心统计如下：

| 指标 | 数值 |
|---|---:|
| 任务数 | 8 |
| 通过数 | 1 |
| 通过率 | 12.5% |
| `workflow_complete=true` | 5 |
| 阶段审计通过 | 5 |
| 审稿打回 | 7 |
| 平均步数 | 6.375 |
| 平均耗时 | 373.971 秒 |

一句话总结：

> 当前系统已经具备“能跑、能审、能拦”的 harness 雏形，但距离“稳定通过一组标准任务”还有明显差距。

## 3. 各任务结果

| 任务 | 是否通过 | 审稿状态 | 工作流完成 | 阶段审计 | 主要失败类型 | 图表数 | 步数 | 耗时（秒） |
|---|---|---|---|---|---|---:|---:|---:|
| `two_group_small_sample` | 否 | `max_reviews_reached` | 否 | `failed` | `cleaning_contract_failure` | 2 | 6 | 439.749 |
| `missing_values_by_group` | 否 | `max_reviews_reached` | 是 | `passed` | `review_rejection` | 4 | 6 | 344.030 |
| `time_series_trend_clean` | 否 | `max_reviews_reached` | 是 | `passed` | `citation_evidence_failure` | 3 | 6 | 329.506 |
| `outlier_sensitive_measurement` | 否 | `max_reviews_reached` | 是 | `passed` | `citation_evidence_failure` | 3 | 6 | 381.499 |
| `correlation_without_causality` | 是 | `accepted` | 是 | `passed` | `citation_evidence_failure` | 3 | 7 | 430.071 |
| `multi_group_with_variance_shift` | 否 | `max_reviews_reached` | 否 | `failed` | `cleaning_contract_failure` | 3 | 5 | 319.052 |
| `before_after_paired_measure` | 否 | `max_reviews_reached` | 是 | `passed` | `citation_evidence_failure` | 3 | 7 | 372.122 |
| `mixed_units_and_dirty_headers` | 否 | `max_reviews_reached` | 否 | `failed` | `cleaning_contract_failure` | 0 | 8 | 375.742 |

## 4. 本轮最重要的发现

### 4.1 阶段执行审计是有效的，而且抓到了真实问题

`two_group_small_sample`、`multi_group_with_variance_shift` 和 `mixed_units_and_dirty_headers` 都触发了 `cleaning_contract_failure`。这说明新加的阶段执行审计不是装饰层，而是真的在拦截：

- 没有明确保存规范 `cleaned_data.csv`
- 没有在后续步骤中明确重读 `cleaned_data.csv`
- 看起来已经做了分析，但其实没有证明“正式分析是基于清洗后的全量数据完成的”

这类失败对项目是好消息，因为它说明系统已经从“能跑”开始进入“能约束”的阶段。以前这类问题可能会被静默放过，现在至少已经能被硬拦截。

### 4.2 当前 reviewer 的压力主要集中在“证据”和“图表表达”

在通过阶段审计的任务中，最常见的问题不是代码跑不动，而是：

- `citation_evidence_failure`
- `chart_quality_failure`
- 最终落到 `max_reviews_reached`

这说明当前主链已经能做出统计分析和图表，但 **分析结果的表达层** 还没有稳定下来。更具体地说，问题可能集中在：

- 结论与数据支持之间的绑定不够清楚
- 图表虽然生成了，但配套解释不够充分
- 审稿要求的“保守表述、证据闭环、图文对应”还没有被 analyst prompt 稳定学会

### 4.3 真正通过的任务只有一个，而且它也暴露了 taxonomy 的问题

`correlation_without_causality` 是本轮唯一一个 `accepted` 的任务。这说明当前系统并不是完全无法达标，至少在“相关性分析 + 保守表达”这一路上，已经有成功样例。

但这个任务同时也暴露出一个 harness 层面的细节问题：

- 它已经 `accepted=true`
- 但 `failure_types` 里仍然出现了 `citation_evidence_failure` 和 `chart_quality_failure`

这说明当前 failure taxonomy 还没有把“中途被 reviewer 批评过”和“最终确实失败了”清晰地区分开。换句话说，当前 taxonomy 更像“问题痕迹聚合”，还不完全等于“最终失败标签”。

### 4.4 系统并不缺分析方法，缺的是让这些方法稳定通过治理层

从各任务的 `methods_used` 看，系统已经会尝试：

- 描述统计
- Mann-Whitney U
- Kruskal-Wallis
- Shapiro-Wilk
- Wilcoxon signed-rank
- Bootstrap confidence interval
- 相关分析
- 各类基础可视化

因此当前的主要短板并不是“模型不会选方法”或“系统不会画图”，而是：

- 全量数据使用契约没完全稳住
- 报告与图表表达不够 reviewer-friendly
- 返修轮次还不足以把大多数任务推过 accepted 线

## 5. 对项目当前状态的判断

如果把这轮 partial eval 翻译成一句对项目的工程判断，可以写成：

> 当前项目已经从“能分析的 Agent”进入“可被约束、可被审稿、可被复盘的 Harness 雏形”阶段，但它还没有稳定学会在治理压力下连续通过标准任务。

更具体地说：

- 输入治理：已经比较强
- 执行主链：已经能跑出真实分析结果
- 审计与审稿：已经开始发挥实质作用
- 稳定通过率：还偏低
- failure taxonomy：还需要从“问题痕迹”进一步收束到“最终失败归因”

## 6. 第一优先级改进项

### 6.1 先修 Analyst Prompt，让“全量数据契约”更难被违反

当前最该补的不是新功能，而是把 analyst 在 Stage 1 / Stage 2 的动作约束写得更强。

建议优先强化：

- 必须显式保存标准 `cleaned_data.csv`
- 正式统计分析必须显式从标准 `cleaned_data.csv` 重读
- 报告里要写明清洗动作和数据来源

目标是先把 `cleaning_contract_failure` 从 3 个任务压下去。

### 6.2 调整 Reviewer / Taxonomy 映射规则

当前 taxonomy 把一些 reviewer critique 直接写成 failure type，哪怕最终任务已经 accepted。这会让 baseline 的失败画像比真实情况更差。

建议改成两层：

- `critique_tags`：记录被 reviewer 指出过什么问题
- `failure_types`：只记录最终没有解决、真正导致未通过的问题

### 6.3 给高频失败任务增加 task-specific guardrails

第一轮最值得补的 guardrail 包括：

- `two_group_small_sample`
  - 必须说明样本量限制
  - 禁止过度结论
- `time_series_trend_clean`
  - 结论不能超出观察区间
  - 图表必须有趋势解释
- `outlier_sensitive_measurement`
  - 必须说明异常值的存在与影响
- `before_after_paired_measure`
  - 必须明确这是配对结构
  - 图表与结论都要体现“同一对象前后变化”

## 7. 第二优先级改进项

### 7.1 提高 eval 过程的可观测性

本轮从命令行看起来像“长时间没反应”，但实际上任务在持续运行。建议在 `run_eval.py` 中增加：

- 每个任务开始时打印 `task_id`
- 每个任务结束时打印 `accepted / review_status / duration`
- 当前进度提示，例如 `3/10`

这样后续跑 baseline 时，不容易把“正在跑”误判成“卡死”。

### 7.2 为失败任务建立更细的复盘标签

本轮已经能看出至少需要区分：

- 契约失败
- 证据表达失败
- 图表表达失败
- 纯审稿未通过

下一步可以把“最终失败原因”和“中途 critique 痕迹”拆开，这会让 baseline 更能指导优化。

## 8. 当前复盘结论

这轮 8 个任务的结果已经足够说明三件事：

1. 当前 harness 不是空壳，审计和审稿都真的在工作。
2. 当前系统最大的瓶颈不是“不会分析”，而是“分析结果还不够稳地通过治理层”。
3. 下一步最值得做的是优化主链约束与表达质量，而不是继续堆新功能。

如果后续补完 `reference_guideline_lookup` 和 `memory_constrained_repeat_task`，再把 10 个任务合并成正式 `seed_v1 baseline`，这份 partial eval 复盘就可以升级为完整的第一轮 baseline 复盘。
