# Harness `seed_v1` vs `seed_v2` 对比复盘

## 2026-04-24 后续状态

后续 `seed_v5` 已固化为当前稳定基线，完整 10 任务达到 `10/10 accepted`。

当前主矛盾已经不再是大面积 analyst / reviewer 不对齐，也不再是 `cleaning_contract_failure` 集中阻塞。后续改动应默认使用 `eval/baselines/seed_v5.json` 做回归对照。

详细记录见 `docs/harness_seed_v4_iteration_summary.md`。如果后续出现回归，建议继续沿用“先检查失败 run，再做最小修复”的节奏，而不是继续扩大 prompt 面积。

## 1. 复盘范围

本次对比使用的不是两个已经合并好的 baseline 文件，而是两轮评测中每个任务**最新可用的 summary**。

- 第一轮基线参考：
  - [eval/reports/20260421_083207](/C:/Users/pc/OneDrive/Desktop/agent/eval/reports/20260421_083207)
  - 当时只完成了 `8` 个任务，属于 partial eval
- 第二轮基线参考：
  - 当前 `eval/reports/` 下每个任务的**最新一份** summary
  - 共覆盖 `10` 个任务

说明：

- `seed_v1`：更适合看“第一轮暴露出什么问题”
- `seed_v2`：更适合看“在修改 `run_eval.py` 和 prompt 之后，系统结构性问题有没有变化”

因此，这份文档更关注**趋势**和**失败模式迁移**，而不是简单比较两个绝对数值。

## 2. 总体对比

| 指标 | `seed_v1` | `seed_v2` | 变化 |
|---|---:|---:|---|
| 任务数 | 8 | 10 | 第二轮任务覆盖更完整 |
| 通过数 | 1 | 0 | 第二轮暂未出现 accepted |
| `workflow_complete=true` | 5 | 6 | 绝对数增加，但比例未明显改善 |
| 阶段审计通过 | 5 | 6 | 绝对数增加，但仍有较多契约失败 |
| 审稿打回 | 7 | 10 | 第二轮 reviewer 对全部任务都未放行 |
| 平均步数 | 6.375 | 5.9 | 略有下降 |
| 平均耗时 | 373.971 秒 | 324.499 秒 | 明显下降 |

失败类型分布对比：

| 失败类型 | `seed_v1` | `seed_v2` | 变化 |
|---|---:|---:|---|
| `review_rejection` | 7 | 10 | 第二轮所有任务最终都被 reviewer 卡住 |
| `citation_evidence_failure` | 4 | 5 | 绝对数略增 |
| `chart_quality_failure` | 4 | 5 | 绝对数略增 |
| `cleaning_contract_failure` | 3 | 4 | 绝对数略增 |

## 3. 第一眼结论

如果先不看细节，只看整体趋势，这轮优化带来的效果可以概括成一句话：

> 第二轮让评测过程更可观测、平均耗时更短、部分任务的执行契约明显改善，但并没有把系统整体推到“更容易通过 reviewer”的状态，反而暴露出更清晰的失败分层。

换句话说，第二轮不是“整体变好很多”，而是：

- **执行链路的一部分问题被修正了**
- **但报告表达与 reviewer 治理层的问题更清楚地暴露出来了**

这其实是有价值的，因为系统开始从“糊成一团地失败”变成“更能看清失败发生在哪一层”。

## 4. 哪些地方变好了

### 4.1 `run_eval.py` 的可观测性明显提升

这虽然不直接体现在 accepted 数量上，但对工程推进非常重要。

第二轮已经解决了第一轮最难受的一个问题：

- 第一次跑时，终端长时间没有任何反馈，很像程序卡住
- 第二轮现在会打印：
  - 当前 report 目录
  - `i / N`
  - 当前任务名
  - 任务结束后的 `accepted / review / audit / duration`

这意味着 harness 真正开始具备“可运行、可监控、可中断后续跑”的工程体验。

### 4.2 部分任务的阶段执行契约确实改善了

最明显的是：

- `two_group_small_sample`
  - `seed_v1`: `workflow_complete=false`, `audit=failed`
  - `seed_v2`: `workflow_complete=true`, `audit=passed`

- `mixed_units_and_dirty_headers`
  - `seed_v1`: `workflow_complete=false`, `audit=failed`
  - `seed_v2`: `workflow_complete=true`, `audit=passed`

这说明第二轮对 prompt 里“后续 Python 步骤显式重读 `cleaned_data.csv`”的强化，并不是无效改动。至少对一部分任务，系统已经更能遵守全量数据使用契约。

### 4.3 平均耗时下降了

虽然结果没变得更“能过”，但第二轮的平均耗时从：

- `373.971 秒`

降到了：

- `324.499 秒`

这说明：

- 更强的任务级 query 注入没有明显拖慢系统
- 整体执行路径反而更短一些
- 平均步数也从 `6.375` 降到 `5.9`

这对后续持续跑 harness 很重要，因为后面你会反复迭代 prompt / review / taxonomy，这种评测成本下降是实打实的收益。

## 5. 哪些地方没有变好，甚至更糟了

### 5.1 第二轮没有任何任务 `accepted`

这是最直接的坏消息。

第一轮虽然只有 8 个任务，但至少 `correlation_without_causality` 是 accepted 的。第二轮在 10 个任务里：

- `accepted = 0`
- `review_rejection = 10`

这说明第二轮优化虽然改善了某些执行层问题，但**没有把 reviewer 层的通过率拉起来**。

### 5.2 一部分任务从“契约失败”转成了“表达失败”

典型任务：

- `two_group_small_sample`
  - `seed_v1`: 主要挂在 `cleaning_contract_failure`
  - `seed_v2`: 变成 `citation_evidence_failure + chart_quality_failure + review_rejection`

- `mixed_units_and_dirty_headers`
  - `seed_v1`: `cleaning_contract_failure`
  - `seed_v2`: `citation_evidence_failure + chart_quality_failure + review_rejection`

这不是纯坏事。它意味着系统开始能通过执行契约层，但到 reviewer 那里又被卡住了。也就是说，**失败位置从执行层上移到了表达层**。

从 harness 视角看，这其实比“根本没过审计”更接近真正的下一阶段问题。

### 5.3 有些任务的执行契约反而退化了

典型任务：

- `missing_values_by_group`
  - `seed_v1`: `workflow_complete=true`, `audit=passed`
  - `seed_v2`: `workflow_complete=false`, `audit=failed`

- `outlier_sensitive_measurement`
  - `seed_v1`: `workflow_complete=true`, `audit=passed`
  - `seed_v2`: `workflow_complete=false`, `audit=failed`

尤其 `outlier_sensitive_measurement` 还出现了：

- `Telemetry cleaned_data_path does not match the canonical run artifact path.`

这说明第二轮 prompt 改强之后，并没有让所有任务都更稳，反而让某些任务在 Stage 1 / Stage 2 契约上变得更脆。换句话说，**新的 prompt 护栏有改善，但仍不够稳定**。

### 5.4 `multi_group_with_variance_shift` 仍然是难点，而且更慢了

这个任务在两轮里都没过审计：

- `seed_v1`: `audit=failed`, `duration=319.052`
- `seed_v2`: `audit=failed`, `duration=653.171`

这是第二轮里最明显的“又慢又没过”的任务。它说明：

- 多组比较 + 波动差异 + 图表表达
- 仍然是当前系统的难点组合

这个任务很适合后面单独作为重点优化对象。

## 6. 逐任务变化判断

### 明显改善

- `two_group_small_sample`
  - 从执行契约失败，提升到工作流完成且审计通过
  - 但 reviewer 层仍未放行

- `mixed_units_and_dirty_headers`
  - 从执行契约失败，提升到工作流完成且审计通过
  - 失败主因转向图表 / 证据表达

### 基本持平

- `time_series_trend_clean`
  - 两轮都能完成工作流并通过审计
  - 但都卡在 reviewer 层

- `before_after_paired_measure`
  - 两轮都通过审计
  - 第二轮主失败类型收束成 `review_rejection`
  - 说明配对结构方面的显式提醒有一定帮助，但仍不足以过审

### 变差

- `correlation_without_causality`
  - 第一轮唯一 accepted
  - 第二轮反而掉到 `max_reviews_reached`
  - 这是一个强烈信号：第二轮 prompt 改动可能让某些原本能过的任务变得更保守或更啰嗦，但不一定更 reviewer-friendly

- `missing_values_by_group`
  - 从 audit pass 退化到 audit failed

- `outlier_sensitive_measurement`
  - 从 audit pass 退化到 audit failed

### 新增任务（无 `seed_v1` 对照）

- `reference_guideline_lookup`
  - `audit=failed`
  - 说明即便引入了 RAG，本轮主要问题仍然不是“会不会引用”，而是 Stage 1 / Stage 2 契约都没完全站稳

- `memory_constrained_repeat_task`
  - `audit=passed`
  - 但仍卡在 reviewer 层
  - 说明 Memory 链路至少没有直接破坏主链执行，但也还没明显转化为通过率收益

## 7. 对第二轮优化成效的判断

如果把这轮结果翻译成一句工程判断，可以写成：

> 第二轮优化成功地把 harness 从“难以观察的黑盒批量跑”推进成“有进度、有 partial report、能看清失败层级”的评测系统，但还没有把 analyst 主链和 reviewer 治理层对齐到稳定通过标准任务的程度。

更进一步讲：

- **工程体验变好了**
- **平均耗时下降了**
- **部分任务的执行契约改善了**
- **但 accepted 没有提升，reviewer rejection 反而成为更一致的主失败结局**

这意味着下一轮优化重点不该再放在 `run_eval.py`，而应该更明确地转向：

1. reviewer 期望和 analyst 生成风格的对齐
2. 图表解释模板
3. evidence / citation failure 的更细拆分
4. cleaning contract 在不同任务上的稳定性

## 8. 下一轮最值得改什么

### 8.1 优先级最高：报告表达模板化

第二轮已经反复表明：

- 很多任务不是不会算
- 也不是不会画
- 而是 **算完和画完之后，写出来的报告不够 reviewer-friendly**

下一轮建议优先做：

- 图表解释模板
- 小样本限制模板
- 配对数据解释模板
- 异常值说明模板
- 缺失值处理说明模板

目标是减少：

- `chart_quality_failure`
- `citation_evidence_failure`
- `review_rejection`

### 8.2 第二优先级：继续收紧契约失败的具体模式

当前 `cleaning_contract_failure` 还在 4 个任务里出现，说明“更强 prompt”还不够，后面可能需要：

- 更明确的 Stage 1 / Stage 2 代码模板
- 在 observation 中更强地提示“你还没有满足 later Python step reload”
- 针对 `missing_values` / `outlier` / `RAG` 任务定向补强

### 8.3 第三优先级：调整 failure taxonomy

第二轮里几乎所有任务都挂了 `review_rejection`，这虽然真实，但还不够细。

后续最好区分：

- reviewer 因图表解释打回
- reviewer 因证据表达打回
- reviewer 因结论语气打回
- reviewer 因统计报告格式打回

这样第三轮的优化方向会更清楚。

## 9. 当前对 harness 阶段的最终判断

如果只看两轮对比，这个项目现在已经很明确地走到了下面这个阶段：

> 它已经不是“有没有 harness”这个问题了，而是一个真正进入了 **第二阶段调优** 的 harness：主链、审计、review、记录、对比都已经在工作，但系统还处于“执行层开始稳住，表达层成为主要瓶颈”的阶段。

这比单纯“通过率低”更重要。因为现在你已经知道：

- 哪些任务是执行层问题
- 哪些任务是表达层问题
- 哪些任务在第二轮反而退化了
- 哪些任务值得单独拎出来做专项优化

这说明 harness 这套东西已经开始真正指导系统迭代，而不是停留在“有框架没用起来”的状态。
