from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _answer_tags(text: str) -> dict[str, str]:
    return dict(re.findall(r"@(\w+)\[(.*?)\]", str(text or "")))


def _official_equal(response: Any, label: Any) -> bool:
    if response == label:
        return True
    try:
        return abs(float(response) - float(label)) < 1e-6
    except Exception:
        return False


def compute_official_style_metrics(*, labels_path: Path, responses_path: Path) -> dict[str, Any]:
    labels = _load_jsonl(labels_path)
    responses = _load_jsonl(responses_path)
    by_id = {str(item.get("id")): item for item in responses}
    matched = []
    for label in labels:
        task_id = str(label.get("id"))
        response = by_id.get(task_id, {})
        response_text = str(response.get("response", "") or "")
        if not response_text:
            continue
        predicted = _answer_tags(response_text)
        expected = {name: value for name, value in label.get("common_answers", [])}
        correctness = {name: _official_equal(predicted.get(name), value) for name, value in expected.items()}
        matched.append({"id": task_id, "correctness": correctness})
    question_correct = sum(1 for item in matched if item["correctness"] and all(item["correctness"].values()))
    sub_correct = sum(sum(item["correctness"].values()) for item in matched)
    sub_total = sum(len(item["correctness"]) for item in matched)
    all_denominator_correct = question_correct
    return {
        "label_count": len(labels),
        "response_count": len(responses),
        "matched_nonempty_response_count": len(matched),
        "official_accuracy_by_question_matched": round(question_correct / len(matched), 4) if matched else 0.0,
        "official_accuracy_by_question_all": round(all_denominator_correct / len(labels), 4) if labels else 0.0,
        "official_accuracy_by_sub_question": round(sub_correct / sub_total, 4) if sub_total else 0.0,
        "official_question_correct_count": question_correct,
    }


def _rate_by_level(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    levels: dict[str, list[dict[str, Any]]] = {}
    for item in results:
        levels.setdefault(str(item.get("level", "unknown")), []).append(item)
    return {
        level: {
            "count": len(items),
            "exact_match": sum(1 for item in items if item.get("exact_match")),
            "rate": round(sum(1 for item in items if item.get("exact_match")) / len(items), 4) if items else 0.0,
        }
        for level, items in sorted(levels.items())
    }


def _ensure_matplotlib():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt


def _label_bars(ax: Any, bars: Any, labels: list[str], *, padding: float = 0.02) -> None:
    for bar, label in zip(bars, labels):
        height = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            height + padding,
            label,
            ha="center",
            va="bottom",
            fontsize=9,
        )


def generate_charts(summary: dict[str, Any], official_metrics: dict[str, Any], output_dir: Path) -> dict[str, Path]:
    plt = _ensure_matplotlib()
    output_dir.mkdir(parents=True, exist_ok=True)
    chart_paths: dict[str, Path] = {}

    metric_names = [
        "Official-style AQ (all)",
        "Local compatible EM",
        "Format compliance",
        "Strict project pass",
    ]
    metric_values = [
        official_metrics["official_accuracy_by_question_all"],
        float(summary.get("exact_match_rate", 0.0)),
        float(summary.get("format_compliance_rate", 0.0)),
        float(summary.get("strict_project_pass_rate", 0.0)),
    ]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    bars = ax.bar(metric_names, metric_values, color=["#2563eb", "#059669", "#7c3aed", "#ea580c"])
    ax.set_ylim(0, 1)
    ax.set_ylabel("Rate")
    ax.set_title("DABench Public Benchmark Metrics")
    _label_bars(ax, bars, [f"{value:.1%}" for value in metric_values])
    ax.tick_params(axis="x", rotation=20)
    fig.tight_layout()
    chart_paths["metrics"] = output_dir / "dabench_metrics.png"
    fig.savefig(chart_paths["metrics"], dpi=160)
    plt.close(fig)

    failure_distribution = dict(summary.get("failure_type_distribution", {}))
    fig, ax = plt.subplots(figsize=(7, 4))
    labels = list(failure_distribution)
    values = [failure_distribution[label] for label in labels]
    bars = ax.bar(labels, values, color="#475569")
    ax.set_ylabel("Task count")
    ax.set_title("DABench Failure Distribution")
    y_padding = max(values or [1]) * 0.02
    _label_bars(ax, bars, [str(value) for value in values], padding=y_padding)
    ax.tick_params(axis="x", rotation=20)
    fig.tight_layout()
    chart_paths["failure"] = output_dir / "dabench_failure_distribution.png"
    fig.savefig(chart_paths["failure"], dpi=160)
    plt.close(fig)

    by_level = _rate_by_level(list(summary.get("results", [])))
    fig, ax = plt.subplots(figsize=(7, 4))
    level_order = [level for level in ("easy", "medium", "hard") if level in by_level]
    values = [by_level[level]["rate"] for level in level_order]
    bars = ax.bar(level_order, values, color=["#16a34a", "#ca8a04", "#dc2626"])
    ax.set_ylim(0, 1)
    ax.set_ylabel("Exact match rate")
    ax.set_title("DABench Accuracy by Difficulty")
    _label_bars(ax, bars, [f"{value:.1%}" for value in values])
    fig.tight_layout()
    chart_paths["difficulty"] = output_dir / "dabench_accuracy_by_difficulty.png"
    fig.savefig(chart_paths["difficulty"], dpi=160)
    plt.close(fig)
    return chart_paths


def render_report(
    *,
    summary: dict[str, Any],
    official_metrics: dict[str, Any],
    chart_paths: dict[str, Path],
    output_path: Path,
) -> None:
    by_level = _rate_by_level(list(summary.get("results", [])))
    failure_distribution = dict(summary.get("failure_type_distribution", {}))
    rel = {key: path.relative_to(output_path.parent).as_posix() for key, path in chart_paths.items()}
    lines = [
        "# DABench Public Benchmark Result",
        "",
        "This report summarizes a local reproduction run of Academic-Data-Agent on the currently public InfiAgent-DABench closed-form dev files.",
        "",
        "## Key Takeaways",
        "",
        f"- Current public files contain `{official_metrics['label_count']}` labeled closed-form tasks, not the `311` questions stated on the DABench website leaderboard page.",
        f"- Official-style Accuracy by Question is `{official_metrics['official_accuracy_by_question_all']:.2%}` when empty responses count as failures, or `{official_metrics['official_accuracy_by_question_matched']:.2%}` over non-empty matched responses.",
        f"- Local compatible exact match is `{float(summary.get('exact_match_rate', 0.0)):.2%}` (`{summary.get('exact_match_count')}/{summary.get('sample_size')}`), because it normalizes minor case/quote differences for diagnosis.",
        f"- Strict project pass is `{float(summary.get('strict_project_pass_rate', 0.0)):.2%}`, preserving Academic-Data-Agent workflow/audit constraints as a separate reliability signal.",
        "",
        f"![DABench metrics]({rel['metrics']})",
        "",
        "## Metric Table",
        "",
        "| Metric | Value | Notes |",
        "| --- | ---: | --- |",
        f"| Official-style Accuracy by Question (all labels) | {official_metrics['official_accuracy_by_question_all']:.2%} | Closest local reproduction of official evaluator semantics |",
        f"| Official-style Accuracy by Question (matched non-empty) | {official_metrics['official_accuracy_by_question_matched']:.2%} | Official script skips empty responses |",
        f"| Official-style Accuracy by Sub-question | {official_metrics['official_accuracy_by_sub_question']:.2%} | Metric-level correctness |",
        f"| Local compatible exact match | {float(summary.get('exact_match_rate', 0.0)):.2%} | Normalizes case/quote differences |",
        f"| Format compliance | {float(summary.get('format_compliance_rate', 0.0)):.2%} | DABench answer tag extraction success |",
        f"| Workflow complete | {float(summary.get('workflow_complete_rate', 0.0)):.2%} | Project artifact/workflow contract |",
        f"| Execution audit pass | {float(summary.get('execution_audit_pass_rate', 0.0)):.2%} | Project cleaned-data audit |",
        f"| Average duration | {float(summary.get('avg_duration_seconds', 0.0)):.2f}s/task | Local run timing |",
        "",
        "## Cautious Public Baseline Comparison",
        "",
        "| System / run | Accuracy by Question | Comparability |",
        "| --- | ---: | --- |",
        "| Academic-Data-Agent local run | 85.60%-85.94% | Current public 257-task files, local reproduction |",
        "| GPT-4-0613 on DABench page | 78.72% | Website leaderboard, stated 311-question validation set |",
        "| GPT-3.5-turbo-0613 on DABench page | 65.70% | Website leaderboard |",
        "| DAAgent-34B on DABench page | 67.50% | Website leaderboard |",
        "",
        "Do not describe this as an official leaderboard result or SOTA claim. The website, current GitHub files, and HuggingFace files have different task-count wording.",
        "",
        "## Difficulty Breakdown",
        "",
        f"![DABench accuracy by difficulty]({rel['difficulty']})",
        "",
        "| Difficulty | Tasks | Exact matches | Rate |",
        "| --- | ---: | ---: | ---: |",
    ]
    for level in ("easy", "medium", "hard"):
        item = by_level.get(level)
        if item:
            lines.append(f"| {level} | {item['count']} | {item['exact_match']} | {item['rate']:.2%} |")
    lines.extend(
        [
            "",
            "## Failure Distribution",
            "",
            f"![DABench failure distribution]({rel['failure']})",
            "",
            "| Failure type | Count |",
            "| --- | ---: |",
        ]
    )
    for key, value in sorted(failure_distribution.items()):
        lines.append(f"| {key} | {value} |")
    lines.extend(
        [
            "",
            "## Reproduction Notes",
            "",
            "- Command: `python eval/scripts/run_dabench.py --full-validation --dabench-mode --env-file .env --vision-review-mode off`",
            "- Data source checked against current public `da-dev-questions.jsonl` and `da-dev-labels.jsonl` from the InfiAgent-DABench assets.",
            "- Full raw model reports and external benchmark data are intentionally excluded from git; use the local ignored `eval/reports/dabench/20260511_004214/` directory for forensic review.",
        ]
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a lightweight DABench report for docs.")
    parser.add_argument("--summary", default="eval/reports/dabench/20260511_004214/eval_dabench_summary.json")
    parser.add_argument("--labels", default="data/external/dabench/data/da-dev-labels.jsonl")
    parser.add_argument("--responses", default="eval/reports/dabench/20260511_004214/responses.jsonl")
    parser.add_argument("--output", default="docs/dabench_public_benchmark_report.md")
    parser.add_argument("--asset-dir", default="docs/assets")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    summary_path = (PROJECT_ROOT / args.summary).resolve()
    labels_path = (PROJECT_ROOT / args.labels).resolve()
    responses_path = (PROJECT_ROOT / args.responses).resolve()
    output_path = (PROJECT_ROOT / args.output).resolve()
    asset_dir = (PROJECT_ROOT / args.asset_dir).resolve()
    summary = _load_json(summary_path)
    official_metrics = compute_official_style_metrics(labels_path=labels_path, responses_path=responses_path)
    chart_paths = generate_charts(summary, official_metrics, asset_dir)
    render_report(summary=summary, official_metrics=official_metrics, chart_paths=chart_paths, output_path=output_path)
    print(output_path.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
