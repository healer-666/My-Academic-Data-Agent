"""Harness helpers for eval tasks, baselines, and regression checks."""

from __future__ import annotations

from .baseline import aggregate_baseline_snapshot, load_baseline_snapshot, save_baseline_snapshot
from .failure_taxonomy import classify_failure_types, determine_primary_failure_type
from .models import BaselineSnapshot, EvalRunSummary, RegressionRules, TaskSpec
from .regression import compare_baselines, load_regression_rules, render_comparison_markdown
from .summary import build_eval_run_summary, build_run_summary_payload
from .task_loader import load_task_spec, load_task_specs

__all__ = [
    "BaselineSnapshot",
    "EvalRunSummary",
    "RegressionRules",
    "TaskSpec",
    "aggregate_baseline_snapshot",
    "build_eval_run_summary",
    "build_run_summary_payload",
    "classify_failure_types",
    "compare_baselines",
    "determine_primary_failure_type",
    "load_baseline_snapshot",
    "load_regression_rules",
    "load_task_spec",
    "load_task_specs",
    "render_comparison_markdown",
    "save_baseline_snapshot",
]
