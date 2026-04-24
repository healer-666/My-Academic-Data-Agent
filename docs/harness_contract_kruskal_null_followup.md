# Harness Contract Follow-up: Kruskal-Wallis Null Hypothesis

## Background
On `2026-04-23`, the latest smoke eval showed a clear split:

- `two_group_small_sample` passed in `run_20260423_202021`
- `correlation_without_causality` still failed in `run_20260423_202226`

At that point, the earlier hotfixes had already taken effect:

- `execution_audit = passed`
- `figure_interpretation_hit_count = 2`
- `effect_size_present = true`

The only remaining contract blocker for `correlation_without_causality` was:

- `Rank-based hypothesis tests such as Mann-Whitney U or Kruskal-Wallis must state the null hypothesis in plain language.`

## Root Cause
This was no longer a detector problem.

The report already contained:
- the correlation result,
- the Kruskal-Wallis test result,
- an effect size,
- figure interpretation,
- non-causal wording.

What it still lacked was one explicit plain-language sentence stating the Kruskal-Wallis null hypothesis for the cohort comparison.

So the remaining gap had moved from:

- "the contract checker failed to recognize existing content"

to:

- "the analyst still was not reliably prompted to write the exact null-hypothesis sentence."

## Minimal Fix
Two small forward-facing changes were applied.

### 1. Strengthen the system prompt
In `src/data_analysis_agent/prompts.py`:

- the rank-test guardrail was extended so `Kruskal-Wallis` reports must explicitly state:
  - which groups are being compared, and
  - that the null hypothesis is no systematic distributional difference across those groups.

- an extra task-aware contract sentence was added for correlation-style reports that also compare cohorts or groups with a rank-based test.

### 2. Strengthen the harness task hint
In `eval/scripts/run_eval.py`, the `correlation_without_causality` task hint now explicitly says:

- if `Kruskal-Wallis` is used to compare cohorts,
- the report must state in plain language that the cohort distributions do not differ systematically under the null hypothesis.

## Why This Fix
This change does not alter the contract checker, reviewer workflow, or harness structure.

It only pushes the final remaining contract expectation earlier into the analyst generation stage, which is the smallest change consistent with the observed failure mode.

## Expected Outcome
On the next smoke eval for `correlation_without_causality`, the expected progression is:

- `execution_audit = passed`
- `report_contract_passed = true`
- no failure on `null_hypothesis_stated = false`

If it still fails after this change, the next investigation should move away from prompt wording and into:

- whether the analyst is omitting the sentence despite explicit guidance,
- whether the wrong test is being highlighted as the main hypothesis test,
- or whether the contract logic needs a task-aware exception for mixed correlation + cohort-comparison reports.

## Follow-up Result
On `2026-04-24`, the expected outcome was confirmed:

- `correlation_without_causality` passed in `run_20260424_104643`
- later re-validation passed again in `run_20260424_110437`
- final status: `accepted=true`, `review=accepted`, `audit=passed`

The Kruskal-Wallis null-hypothesis issue is therefore no longer the active blocker.

The follow-up smoke work exposed several adjacent issues instead:

- reviewer over-rejection after the report contract had already passed
- execution audit failing to resolve common `os.path.join(...)` cleaned-data paths
- revision rounds rerunning Stage 2 without rerunning Stage 1 in the same trace
- time-series trend boundary wording not being detected in conservative Chinese wording
- local RAG being skipped when embeddings were not configured, even though keyword retrieval was possible

These are summarized in `docs/harness_seed_v4_iteration_summary.md`.

Current next target:

- inspect the three remaining `cleaning_contract_failure` runs one by one
- avoid broad prompt expansion until each failed run has a concrete root cause
