# DataSciBench Official Evaluation Readiness

This note records the current state of the DataSciBench official scoring integration.

## What Is Integrated

- Official evaluator source: `data/external/datascibench_official/`
- Official prompt/metric layout: `data/{task_id}/prompt.json` and `metric/{task_id}/metric.yaml`
- Academic-Data-Agent output bridge:
  - BigCodeBench-style tasks (`bcb*`) are converted to `{model_id}_outputs.jsonl` and scored with `python -m experiments.evaluate_tmc`.
  - TFC artifact tasks (`csv_excel*`, `human*`, `dl*`) are staged into `data/{task_id}/{model_id}_{run_id}/` and scored with `python -m experiments.evaluate` when `data/{task_id}/gt/` exists.
  - Missing official GT is reported as unsupported, not scored with a custom substitute metric.
- Full-evaluation runner preparation:
  - `run_datascibench.py` now builds a task input manifest from official task files when present.
  - If no task files are available, it falls back to prompt-only execution.

## Pilot Official Scoring Result

Source agent run:

`eval/reports/datascibench/20260511_111031/eval_datascibench_summary.json`

Official scoring bridge run:

`eval/reports/datascibench_official/20260511_115020/official_eval_summary.json`

| Metric | Value |
| --- | ---: |
| Pilot tasks | 10 |
| Prepared for official evaluator | 6 |
| Officially scored | 6 |
| Unsupported | 4 |
| Evaluator failures | 0 |

Scored `bcb*` task CR values:

| Task | Official evaluator | CR |
| --- | --- | ---: |
| `bcb198` | `evaluate_tmc` | 1.0 |
| `bcb42` | `evaluate_tmc` | 1.0 |
| `bcb50` | `evaluate_tmc` | 0.0 |
| `bcb646` | `evaluate_tmc` | 0.0 |
| `bcb690` | `evaluate_tmc` | 1.0 |
| `bcb983` | `evaluate_tmc` | 1.0 |

Unsupported pilot tasks:

| Task | Reason |
| --- | --- |
| `bcb579` | No extractable `task_func` implementation in trace/report |
| `csv_excel_1` | Missing HuggingFace `gt` directory |
| `csv_excel_41` | Missing HuggingFace `gt` directory |
| `dl_10` | Missing HuggingFace `gt` directory |

## Current Blocker

The public HuggingFace dataset clone attempt failed with authentication:

`Password authentication in git is no longer supported. You must use a user access token or an SSH key instead.`

To score non-BCB TFC tasks, download the HuggingFace evaluation data into:

`data/external/datascibench_hf/`

Expected effect: the bridge will sync `gt` folders into `data/external/datascibench_official/data/{task_id}/gt/` and then invoke the official `experiments.evaluate` scorer.

## Commands

Prepare or score an existing Academic-Data-Agent run:

```powershell
& 'D:\anaconda\envs\agent_env\python.exe' eval\scripts\prepare_datascibench_official_eval.py `
  --summary eval\reports\datascibench\20260511_111031\eval_datascibench_summary.json `
  --official-root data\external\datascibench_official `
  --hf-root data\external\datascibench_hf `
  --run-official-eval `
  --python-executable 'D:\anaconda\envs\agent_env\python.exe' `
  --timeout-seconds 90
```

Run the full 222-task DataSciBench set after official data is in place:

```powershell
& 'D:\anaconda\envs\agent_env\python.exe' eval\scripts\run_datascibench.py `
  --data-root data\external\datascibench_official `
  --sample-size 0 `
  --task-group all `
  --data-source-type all `
  --env-file .env `
  --task-retries 0 `
  --max-steps 16 `
  --quality-mode draft `
  --latency-mode quality `
  --vision-review-mode off
```

Then pass the generated `eval_datascibench_summary.json` into `prepare_datascibench_official_eval.py`.

## Full Evaluation Gate

Before launching full evaluation:

1. Download HuggingFace GT with a valid token or authenticated CLI.
2. Run a 10-20 task mixed pilot with official GT present.
3. Confirm `csv_excel` and `human` TFC tasks produce non-empty official result CSVs.
4. Decide whether `dl` tasks should run in this environment or be split into a dependency-heavy second pass.
5. Only then start the full 222-task run, because it will incur API cost and may run for many hours.
