# DataSciBench Pilot Evaluation Plan

This note records the first local DataSciBench adapter run for Academic-Data-Agent. It is a feasibility check, not a benchmark score.

## Why DataSciBench

DataSciBench is newer and broader than DABench: it targets full data-science agent workflows, including prompt decomposition, code execution, artifact generation, and TFC-style evaluation. Official resources:

- Website: <https://datascibench.github.io/>
- Code: <https://github.com/THUDM/DataSciBench>
- Evaluation data: <https://huggingface.co/datasets/zd21/DataSciBench/tree/main>

## Pilot Result

| Item | Value |
| --- | ---: |
| Run directory | `eval/reports/datascibench/20260511_111031/` |
| Sample size | 10 |
| Seed | 20260511 |
| Completed tasks | 10 |
| Completed rate | 100.00% |
| Scored by official TFC / GT | 0 |
| Unsupported official scoring | 10 |
| Run errors | 0 |
| Format failures | 0 |
| Average duration | 56.21s/task |

Selected task ids:

| Task id | Group | Data source type |
| --- | --- | --- |
| `bcb198` | `bcb` | `1_bcb` |
| `bcb42` | `bcb` | `1_bcb` |
| `bcb50` | `bcb` | `1_bcb` |
| `bcb579` | `bcb` | `1_bcb` |
| `bcb646` | `bcb` | `1_bcb` |
| `bcb690` | `bcb` | `1_bcb` |
| `bcb983` | `bcb` | `1_bcb` |
| `csv_excel_1` | `csv_excel` | `3=human written data` |
| `csv_excel_41` | `csv_excel` | `2=open source data` |
| `dl_10` | `dl` | `2=open source data` |

## What This Shows

- The adapter can discover official prompt metadata from THUDM/DataSciBench and drive the existing `run_analysis(...)` path.
- The output layout is in place: `responses.jsonl`, `eval_datascibench_summary.json`, `eval_datascibench_summary.md`, `failure_review.md`, `progress.log`, and `run_config.json`.
- The current project can complete a mixed 10-task smoke sample without process-level crashes.
- This is not an official DataSciBench result because HuggingFace ground-truth files and official TFC evaluation are not integrated yet.

## Important Caveats

- The first constrained run with `--data-source-type 1 --task-group csv_excel` found only 3 matching tasks in the current prompt metadata.
- A broader no-dependency run with `--data-source-type 1 --task-group all` found only 6 matching tasks.
- To satisfy the 10-task pilot criterion, the final run used `--data-source-type all --task-group all`, which includes tasks with external/open-source or human-written data requirements. These are intentionally reported as `unsupported_missing_official_gt` until official ground truth is present locally.
- No custom substitute score is reported.

## Reproduction

```powershell
& 'D:\anaconda\envs\agent_env\python.exe' eval\scripts\run_datascibench.py --sample-size 10 --env-file .env --task-retries 0 --task-group all --data-source-type all
```

The current adapter keeps official data and raw run outputs out of git via `.gitignore`.

## Next Steps

1. Download the HuggingFace evaluation data into `data/external/datascibench/`.
2. Map each task output artifact into DataSciBench's expected `experiments.evaluate` / TFC input format.
3. Add scorer-level tests with two tiny fixture tasks that mimic official `gt` and `metric` folders.
4. Re-run a 10-20 task pilot with official scoring enabled.
5. Only after scorer parity is verified, run the larger representative subset and compare against published DataSciBench results.
