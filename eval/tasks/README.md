# 第一批自造科研表格任务

这批任务用于当前项目的第一阶段 harness 建设，目标不是追求最复杂的数据，而是优先把主链稳定性测扎实。

任务设计原则：

- 优先测结构化表格分析主链
- 优先覆盖清洗、全量数据重读、图表、报告、审稿与阶段执行审计
- 只在少量任务中混入 RAG / Memory
- 所有任务都使用小型单表 CSV，便于快速跑通 baseline 和回归比较

当前 10 类任务如下：

1. `two_group_small_sample`
2. `multi_group_with_variance_shift`
3. `before_after_paired_measure`
4. `time_series_trend_clean`
5. `missing_values_by_group`
6. `outlier_sensitive_measurement`
7. `mixed_units_and_dirty_headers`
8. `correlation_without_causality`
9. `reference_guideline_lookup`
10. `memory_constrained_repeat_task`

建议执行顺序与 `eval/scripts/run_eval.py` 内置顺序一致，这样后续增强任务更容易接上。

其中：

- 前 `8` 类主要测纯主链
- `reference_guideline_lookup` 用于测轻量 RAG
- `memory_constrained_repeat_task` 用于测带历史约束的 Memory 行为
