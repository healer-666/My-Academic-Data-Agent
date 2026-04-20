from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from data_analysis_agent.harness import (  # noqa: E402
    compare_baselines,
    load_baseline_snapshot,
    load_regression_rules,
    render_comparison_markdown,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare two harness baselines.")
    parser.add_argument("--current", required=True, help="Path to the current baseline JSON.")
    parser.add_argument("--baseline", required=True, help="Path to the reference baseline JSON.")
    parser.add_argument("--rules", default="eval/regression_rules.json", help="Regression rules JSON path.")
    parser.add_argument("--report-dir", default=None, help="Optional report output directory.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    current = load_baseline_snapshot(PROJECT_ROOT / args.current)
    baseline = load_baseline_snapshot(PROJECT_ROOT / args.baseline)
    rules = load_regression_rules(PROJECT_ROOT / args.rules)
    comparison = compare_baselines(current=current, baseline=baseline, rules=rules)

    if args.report_dir:
        report_dir = (PROJECT_ROOT / args.report_dir).resolve()
    else:
        report_dir = (PROJECT_ROOT / "eval" / "reports" / datetime.now().strftime("%Y%m%d_%H%M%S") / "compare").resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    markdown = render_comparison_markdown(comparison)
    (report_dir / "comparison.md").write_text(markdown, encoding="utf-8")
    (report_dir / "comparison.json").write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")
    print(markdown)
    print(f"\nComparison report directory: {report_dir.as_posix()}")
    return 0 if comparison.get("passed", False) else 1


if __name__ == "__main__":
    raise SystemExit(main())
