from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = PROJECT_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from data_analysis_agent.report_contract import build_revision_brief, check_report_contract
from data_analysis_agent.reporting import EvidenceCoverage, ReportTelemetry


class ReportContractTests(unittest.TestCase):
    def test_contract_flags_missing_limitations_and_figure_interpretation(self):
        report_markdown = (
            "# Data Overview\nOverview.\n\n"
            "# Data Cleaning Notes\nDropped missing rows.\n\n"
            "# Methods\nUsed Mann-Whitney U.\n\n"
            "# Core Statistical Results\nU = 0, p = 0.01, effect size = 0.8, 95% CI [1, 2].\n\n"
            "# Figure Interpretation\n"
            "![chart](outputs/run/chart.png)\n\n"
            "# Conclusion\nDone.\n"
        )
        telemetry = ReportTelemetry(figures_generated=("outputs/run/chart.png",))

        result = check_report_contract(
            report_markdown,
            task_type="two_group_small_sample",
            telemetry=telemetry,
            evidence_coverage=EvidenceCoverage(),
        )

        self.assertFalse(result.passed)
        self.assertIn("report_structure_failure", result.issue_types)
        self.assertIn("figure_interpretation_failure", result.issue_types)

    def test_contract_requires_paired_declaration_for_before_after_task(self):
        report_markdown = (
            "# Data Overview\nOverview.\n\n"
            "# Data Cleaning Notes\nNo missing values.\n\n"
            "# Methods\nCompared before and after biomarker values.\n\n"
            "# Core Statistical Results\nWilcoxon test, p = 0.02, effect size = 0.5, 95% CI [0.1, 0.9].\n\n"
            "# Figure Interpretation\nNo figures were generated.\n\n"
            "# Limitations\nSmall sample.\n\n"
            "# Conclusion\nObserved change.\n"
        )

        result = check_report_contract(report_markdown, task_type="before_after_paired_measure")

        self.assertFalse(result.passed)
        self.assertIn("report_structure_failure", result.issue_types)

    def test_contract_requires_null_hypothesis_for_rank_test(self):
        report_markdown = (
            "# Data Overview\nOverview.\n\n"
            "# Data Cleaning Notes\nNo missing values.\n\n"
            "# Methods\nUsed Mann-Whitney U test.\n\n"
            "# Core Statistical Results\nMann-Whitney U = 0.0, p = 0.01, rank-biserial correlation = 1.0, 95% CI [1, 2].\n\n"
            "# Figure Interpretation\nNo figures were generated.\n\n"
            "# Limitations\nSmall sample.\n\n"
            "# Conclusion\nIndependent two-group comparison, not paired.\n"
        )

        result = check_report_contract(report_markdown, task_type="two_group_small_sample")

        self.assertFalse(result.passed)
        self.assertIn("report_structure_failure", result.issue_types)

    def test_contract_accepts_chinese_null_hypothesis_wording(self):
        report_markdown = (
            "# Data Overview\nTwo independent groups measured at day7.\n\n"
            "# Data Cleaning Notes\nNo missing values and no outliers were removed.\n\n"
            "# Methods\nThis is an independent two-group comparison, not a paired or pre-post design. "
            "Mann-Whitney U 检验的零假设是两组分布无系统性差异。\n\n"
            "# Core Statistical Results\nMann-Whitney U = 0.0, p = 0.01, rank-biserial correlation = 1.0, 95% CI [1, 2].\n\n"
            "# Figure Interpretation\nNo figures were generated.\n\n"
            "# Limitations\nSmall sample size limits generalizability and the result remains non-causal.\n\n"
            "# Conclusion\nObserved difference only; no causal claim.\n"
        )

        result = check_report_contract(report_markdown, task_type="two_group_small_sample")

        self.assertTrue(result.statistics_flags["null_hypothesis_stated"])
        self.assertFalse(any("must state the null hypothesis" in issue for issue in result.blocking_issues))

    def test_revision_brief_gives_specific_kruskal_null_hypothesis_action(self):
        brief = build_revision_brief(
            source="pre_review_contract",
            blocking_issues=(
                "Rank-based hypothesis tests such as Mann-Whitney U or Kruskal-Wallis must state the null hypothesis in plain language.",
            ),
            next_round_figures_dir="outputs/run/figures/review_round_2",
        )

        message = brief.to_user_message()

        self.assertIn("Kruskal-Wallis cohort/group comparison", message)
        self.assertIn("do not differ systematically", message)
        self.assertIn("re-run Stage 1 first", message)
        self.assertIn("later separate Python Stage 2", message)

    def test_contract_counts_scatter_plot_interpretation(self):
        report_markdown = (
            "# Data Overview\nCorrelation task.\n\n"
            "# Data Cleaning Notes\nNo missing values and no outliers were removed.\n\n"
            "# Methods\nUsed Spearman correlation on independent observations.\n\n"
            "# Core Statistical Results\nSpearman rho = 0.95, p = 0.001, effect size = 0.95, 95% CI [0.8, 0.99].\n\n"
            "# Figure Interpretation\n"
            "![Scatter Plot](outputs/run/scatter.png)\n"
            "- Each point represents one independent sample.\n"
            "- The scatter plot shows a strong positive correlation, and the trend line indicates a monotonic increase across cohorts.\n"
            "- The point cloud also reveals a clear layered cohort pattern.\n\n"
            "# Limitations\nSmall sample size limits generalizability and the result remains non-causal.\n\n"
            "# Conclusion\nObserved association only; no causal claim.\n"
        )
        telemetry = ReportTelemetry(figures_generated=("outputs/run/scatter.png",))

        result = check_report_contract(
            report_markdown,
            task_type="correlation_without_causality",
            telemetry=telemetry,
            evidence_coverage=EvidenceCoverage(),
        )

        self.assertEqual(result.figure_reference_count, 1)
        self.assertEqual(result.figure_interpretation_hit_count, 1)
        self.assertNotIn("figure_interpretation_failure", result.issue_types)

    def test_contract_accepts_time_trend_boundary_chinese_wording(self):
        report_markdown = (
            "# Data Overview\nA 14-day time series.\n\n"
            "# Data Cleaning Notes\nNo missing values and all rows retained.\n\n"
            "# Methods\nLinear trend and Kruskal-Wallis rank test. "
            "The null hypothesis is no systematic distributional difference between windows.\n\n"
            "# Core Statistical Results\nKruskal-Wallis H = 11.43, p = 0.0033, epsilon-squared effect size = 0.88, 95% CI [2.19, 2.39].\n\n"
            "# Figure Interpretation\nThe trend line shows a steady observed increase over time.\n\n"
            "# Limitations\n本报告描述的仅为观察到的趋势，不建立任何机制或干预效应。\n\n"
            "# Conclusion\n该趋势分析仅描述观察到的数据模式，不推断任何因果关系或干预效果。\n"
        )

        result = check_report_contract(report_markdown, task_type="time_series_trend_clean")

        self.assertTrue(result.task_alignment_flags["time_trend_boundary_mentioned"])
        self.assertNotIn(
            "This time-trend task must explicitly state that the report describes an observed trend only and does not establish mechanism or intervention effect.",
            result.blocking_issues,
        )

    def test_contract_passes_on_complete_two_group_report(self):
        report_markdown = (
            "# Data Overview\nTwo independent groups measured at day7.\n\n"
            "# Data Cleaning Notes\nNormalized group labels and confirmed no missing values.\n\n"
            "# Methods\nThis is an independent two-group comparison, not a paired or pre-post design. "
            "We used Mann-Whitney U and the null hypothesis is no systematic distributional difference between groups.\n\n"
            "# Core Statistical Results\nMann-Whitney U = 0.0, p = 0.01, rank-biserial correlation = 1.0, 95% CI [1, 2].\n\n"
            "# Figure Interpretation\n"
            "![chart](outputs/run/chart.png)\n"
            "The boxplot shows a higher median in the intervention group, a narrow interquartile spread, and no visible outliers.\n\n"
            "# Limitations\nSmall sample size limits generalizability and the result remains non-causal.\n\n"
            "# Conclusion\nObserved difference only; no causal claim.\n"
        )
        telemetry = ReportTelemetry(figures_generated=("outputs/run/chart.png",))

        result = check_report_contract(
            report_markdown,
            task_type="two_group_small_sample",
            telemetry=telemetry,
            evidence_coverage=EvidenceCoverage(),
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.issue_types, ())


if __name__ == "__main__":
    unittest.main()
