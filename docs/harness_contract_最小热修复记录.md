# Harness Contract 最小热修复记录

## 背景
在 `2026-04-23` 的第三轮 smoke eval 中，`two_group_small_sample` 和 `correlation_without_causality` 都已经通过了执行审计，但仍然卡在共享 `report contract`。

这说明当前主矛盾已经从“分析链路能不能跑通”转成了“contract heuristic 能不能正确识别已经写出来的内容”。

## 触发本次热修复的两个 run

### 1. `two_group_small_sample`
- run: [run_20260423_170944](/C:/Users/pc/OneDrive/Desktop/agent/outputs/run_20260423_170944)
- 关键结果：
  - `execution_audit = passed`
  - `report_contract_passed = false`
  - 唯一 blocking issue:
    - `Rank-based hypothesis tests such as Mann-Whitney U or Kruskal-Wallis must state the null hypothesis in plain language.`

### 2. `correlation_without_causality`
- run: [run_20260423_181636](/C:/Users/pc/OneDrive/Desktop/agent/outputs/run_20260423_181636)
- 关键结果：
  - `execution_audit = passed`
  - `report_contract_passed = false`
  - 唯一 blocking issue:
    - `At least one cited figure is not accompanied by a nearby interpretation sentence that explains the visual evidence.`

## 根因定位

### `two_group_small_sample`
最终报告里已经出现了类似“零假设为两组分布无系统性差异”的表述，但 `report_contract.py` 里的 `_NULL_HYPOTHESIS_HINTS` 词表偏窄，只覆盖了：
- `null hypothesis`
- `原假设`
- `no systematic`
- `distributional difference`
- `分布相同`

它没有稳定覆盖：
- `零假设`
- `无系统性差异`
- `无差异`
- `两组分布无系统性差异`

因此出现了“报告其实写了，但 contract 仍判定 `null_hypothesis_stated = false`”的误伤。

### `correlation_without_causality`
最终报告里已经有散点图解释，但 `_FIGURE_INTERPRETATION_HINTS` 更偏向箱线图 / 误差棒图场景，缺少散点图与相关性任务常见表达，例如：
- `scatter`
- `scatter plot`
- `trend line`
- `positive correlation`
- `monotonic`
- `each point`
- `point cloud`
- `散点图`
- `每个点代表`
- `趋势线`
- `正相关`
- `单调递增`
- `点云`
- `分层模式`

同时，图片邻近解释窗口也较窄，只扫描图片附近较短的一段文本；当“图上看到了什么”与“这说明什么”分成多条 bullet 写时，容易漏掉后面的解释句。

## 本次最小改动

### 1. 扩充 `_NULL_HYPOTHESIS_HINTS`
补入更贴近中文报告写法的表达：
- `零假设`
- `无系统性差异`
- `无差异`
- `分布无差异`
- `两组分布无系统性差异`

### 2. 扩充 `_FIGURE_INTERPRETATION_HINTS`
补入更适合散点图 / 相关性任务的解释词：
- `scatter`
- `scatter plot`
- `trend line`
- `positive correlation`
- `monotonic`
- `each point`
- `point cloud`
- `散点`
- `散点图`
- `每个点代表`
- `趋势线`
- `正相关`
- `单调递增`
- `点云`
- `分层模式`
- `沿一条直线`

### 3. 放宽图表解释邻近窗口
将 `_count_figure_interpretations(...)` 中图片附近的扫描窗口从 `+6` 放宽到 `+10`，避免“图像说明分成多条 bullet，后面两三条才出现真正解释句”时被误判。

## 回归测试
本次同步补充了两条针对性测试：

1. `test_contract_accepts_chinese_null_hypothesis_wording`
   - 验证中文“零假设 / 无系统性差异”写法不再误判。

2. `test_contract_counts_scatter_plot_interpretation`
   - 验证散点图解释在包含 `each point / scatter plot / trend line / positive correlation / point cloud` 等表达时能够被正确命中。

## 预期效果
本次热修复不改变 analyst / reviewer / harness 的整体结构，也不增加新的模型角色，目标是用最小改动压掉两类已经定位清楚的 heuristic 误伤：

1. 报告实际上已经写了“零假设”，但 contract 没识别出来
2. 报告实际上已经写了散点图解释，但 contract 没识别出来

如果修复后这两类 smoke task 仍不过，那么下一步就不再优先怀疑 heuristic 词表，而要转向：
- 任务级写作模板是否还缺更明确的句型
- `RevisionBrief` 是否需要再细化到图表类型级别
- reviewer 高层逻辑是否仍然过严

## 第二阶段追加热修复（同日）
在修复“零假设识别”和“散点图解释命中”之后，新的 smoke eval 暴露了两个更具体的问题：

### 1. `two_group_small_sample`：图路径证据不一致
- `report_contract` 已通过
- 但 reviewer 仍拒稿
- 根因不是图表解释，而是 reviewer 看到的 `Generated artifacts evidence` 中：
  - telemetry 里有时只有 basename，如 `boxplot_day7_score_by_group.png`
  - 报告里引用的是绝对路径
  - reviewer 在校验时直接拿 basename 当路径，导致 `exists=False`

本次修复：
- 在 `review_service.py` 中新增 review-round 图路径解析逻辑
- 当 telemetry 只给 basename 时，自动解析到当前 `review_round_x` 目录
- reviewer 现在会基于实际落在本轮输出目录里的路径做 `exists` 判断
- 同时在 reviewer prompt 中明确：不要仅因为图路径是绝对路径而拒稿，重点看它是否解析到当前 run 的真实工件

### 2. `correlation_without_causality`：Spearman 相关系数未被识别为 effect size
- 图表解释问题已消失
- 新的唯一 contract 阻塞项变成：
  - `Any reported hypothesis test must include an effect size.`
- 但报告里已经报告了 `Spearman rho`

本次修复：
- 在 `_EFFECT_SIZE_HINTS` 中补入：
  - `spearman rho`
  - `spearman ρ`
  - `rho =`
  - `ρ =`
  - `相关系数`

### 3. telemetry 路径分隔符归一化
为了减少 Windows 反斜杠和 POSIX 斜杠混用带来的 warning，本次还在 `reporting.py` 中统一做了 telemetry 路径标准化：
- `cleaned_data_path`
- `figures_generated`

都会在提取 telemetry 时转换为 `/` 风格。

## 第二阶段补充测试
这次同步补了两类回归保护：

1. `test_valid_telemetry_normalizes_windows_style_paths`
   - 验证 telemetry 中的 Windows 风格路径会被统一成 `/`

2. `test_build_reviewer_task_resolves_basename_figure_paths_to_review_round_dir`
   - 验证当 telemetry 只提供 basename 图文件名时，reviewer task 仍能解析到当前 review round 的真实图路径，并得到 `exists=True`
