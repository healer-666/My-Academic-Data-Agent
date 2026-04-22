# Harness 第三轮优化记录

## 背景
前两轮 harness 评测表明，系统的主要瓶颈已经不再只是执行链路，而是 reviewer 通过率偏低。具体表现为：

- 部分任务的 `execution_audit` 已经开始稳定通过，但最终仍被 reviewer 打回。
- 失败原因逐渐集中到报告结构不完整、图表引用后缺少直接解释、缺少局限性说明，以及任务结构说明不够明确。
- 现有 failure taxonomy 对 reviewer 层失败的表达仍然偏粗，容易把中途 critique 痕迹和最终失败原因混在一起。

因此，第三轮优化不再继续强化 `run_eval.py` 的执行流程，而是把重心放在：

1. analyst 的报告表达模板化  
2. reviewer 的拒稿标准结构化  
3. reviewer 输入中的报告结构检测  
4. harness failure taxonomy 收束  

## 本轮改动

### 1. 强化 analyst 的固定报告骨架
在 `prompts.py` 中补充了更明确的写作护栏，要求最终报告使用稳定结构，并显式包含：

- `Data Overview / 数据概览`
- `Data Cleaning Notes / 数据清洗说明`
- `Methods / 方法说明`
- `Core Statistical Results / 主要统计结果`
- `Figure Interpretation / 图表解释`
- `Limitations / 局限性`
- `Conclusion / 结论`

同时新增了更明确的任务级写作要求：

- 两组比较任务要写出差异、限制与非因果解释
- 配对任务要写清“同一对象前后变化”
- 趋势任务要强调只描述观察到的趋势，不外推机制
- 异常值任务要说明处理策略及其影响

### 2. reviewer prompt 改成“模板对齐检查”
在 `build_reviewer_prompt(...)` 中补充了更明确的拒绝条件：

- 有图但没有直接文字解释，直接拒稿
- 有统计检验但缺少清洗说明或局限性，直接拒稿
- 配对 / before-after 任务未明确说明数据结构，直接拒稿
- 缺失值 / 异常值任务未说明处理策略，直接拒稿

同时要求 reviewer 的 critique 优先指出结构缺失，而不是只给出模糊的“图表解释不足”或“证据不充分”。

### 3. reviewer 输入增加轻量结构检测
在 `review_service.py` 中新增了启发式报告结构检测，供 reviewer 使用：

- 是否出现 `Data Overview / 数据概览`
- 是否出现 `Data Cleaning Notes / 数据清洗说明`
- 是否出现 `Methods / 方法说明`
- 是否出现 `Core Statistical Results / 主要统计结果`
- 是否出现 `Figure Interpretation / 图表解释`
- 是否出现 `Limitations / 局限性`
- 是否出现 `Conclusion / 结论`
- 图表引用数量
- 图表解释命中数量
- 是否显式提到 paired / pre-post
- 是否显式提到 missing value handling
- 是否显式提到 outlier handling
- 是否显式提到 small-sample limitation

这些信号不会替代 reviewer，但会作为审稿输入的一部分，帮助 reviewer 更稳定地识别“结构缺口”。

### 4. harness query 更强利用任务资产
在 `run_eval.py` 中继续强化 `_build_eval_query(task)`，除了原来的分析方法偏好和 guardrails 外，又新增了：

- 固定报告模板要求
- paired / before-after 任务写法提醒
- missing/outlier 任务清洗说明提醒

这样 task spec 里的 `manual_expectations` 不只是告诉 agent “做什么分析”，还会直接影响“报告里怎么写”。

### 5. failure taxonomy 收束
在 `harness/failure_taxonomy.py` 中将 reviewer 层失败改为更可解释的类别：

- `report_structure_failure`
- `figure_interpretation_failure`
- `citation_evidence_failure`
- `review_rejection`

同时保留：

- `cleaning_contract_failure`
- `artifact_contract_failure`

并新增了一个关键约束：

- 如果最终结果已经 `accepted`，不再仅因为 reviewer critique 文本中曾出现图表或结构问题，就自动给该任务打上 reviewer 层 failure 标签。

## 本轮验证
本轮针对第三轮新增逻辑，运行了以下测试：

```powershell
python -m pytest -q tests\test_prompts.py tests\test_agent_runner.py tests\test_harness.py
```

结果：

- `21 passed`

## 下一轮重点观察指标
第三轮优化的目标不是让系统“更会跑”，而是让系统“更容易过 reviewer”。下一轮评测时，建议重点观察：

1. `accepted` 数量是否上升
2. `review_rejection` 是否下降
3. `report_structure_failure` 是否比上一轮更清晰可区分
4. `figure_interpretation_failure` 是否成为更明确的单独类别
5. `cleaning_contract_failure` 是否没有明显恶化
6. 平均步数与平均耗时是否没有显著变差

## 当前判断
第三轮优化的核心不是再给 agent 更多自由，而是：

- 让 analyst 写得更像 reviewer 想看到的报告
- 让 reviewer 更明确地按结构检查
- 让 harness 更准确地区分“执行失败”和“表达失败”

如果下一轮评测中 `accepted` 数量仍然没有明显上升，那么下一步就应该进一步考虑：

- 补更强的报告生成模板
- 在返修阶段加入更明确的 task-specific revision checklist
- 或者继续调整 reviewer 的拒稿阈值与 critique 风格
