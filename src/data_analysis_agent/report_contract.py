"""Shared report contract checks used by analyst, reviewer, and harness."""

from __future__ import annotations

import re

from .reporting import EvidenceCoverage, ReportTelemetry, _iter_markdown_sections
from .runtime_models import ReportContractCheckResult, RevisionBrief
from .symbolic_rules import get_symbolic_rule, rule_ids_for_issue_type


_REPORT_SECTION_HINTS: dict[str, tuple[str, ...]] = {
    "data_overview": ("数据概览", "data overview", "overview"),
    "cleaning_notes": (
        "数据清洗",
        "清洗说明",
        "data cleaning",
        "cleaning notes",
        "preprocessing",
    ),
    "methods": ("方法说明", "methods", "method"),
    "core_results": (
        "主要统计结果",
        "核心统计结果",
        "results",
        "statistical results",
    ),
    "figure_interpretation": (
        "图表解释",
        "结果解释",
        "figure interpretation",
        "result interpretation",
    ),
    "limitations": ("局限性", "限制", "limitations", "limitation"),
    "conclusion": ("结论", "conclusion"),
}
_LIMITATION_BODY_HINTS = (
    "局限",
    "限制",
    "sample size",
    "small sample",
    "non-causal",
    "limitation",
    "limitations",
)
_FIGURE_WORD_HINTS = ("图", "figure", "chart", "plot", "boxplot", "bar chart", "error bar", "误差棒", "箱线图")
_FIGURE_INTERPRETATION_HINTS = (
    "显示",
    "表明",
    "说明",
    "提示",
    "shows",
    "indicates",
    "suggests",
    "reveals",
    "median",
    "中位数",
    "iqr",
    "interquartile",
    "误差棒",
    "置信区间",
    "confidence interval",
    "均值",
    "spread",
    "separation",
    "overlap",
    "outlier",
    "离群",
    "scatter",
    "scatter plot",
    "trend line",
    "positive correlation",
    "monotonic",
    "each point",
    "point cloud",
    "散点",
    "散点图",
    "每个点代表",
    "趋势线",
    "正相关",
    "单调递增",
    "点云",
    "分层模式",
    "沿一条直线",
)
_PAIRED_HINTS = (
    "配对",
    "前后",
    "同一对象",
    "same subjects",
    "same subject",
    "within-subject",
    "before-after",
    "pre-post",
    "paired",
    "repeated",
)
_NON_PAIRED_HINTS = (
    "不是配对",
    "非配对",
    "独立两组",
    "independent two-group",
    "independent groups",
    "not a paired",
    "not paired",
)
_MISSING_HINTS = ("缺失", "missing", "impute", "dropna", "删除缺失", "填补")
_OUTLIER_HINTS = ("异常值", "离群", "outlier", "extreme value", "retained", "excluded", "flagged")
_SMALL_SAMPLE_HINTS = ("小样本", "sample size", "small sample", "n=")
_TREND_BOUNDARY_HINTS = (
    "observed trend",
    "observed trend only",
    "observed data pattern",
    "does not establish mechanism",
    "does not establish intervention effect",
    "does not establish any mechanism",
    "does not establish any mechanism or intervention effect",
    "does not infer causality",
    "does not infer any causal relationship",
    "does not infer any causal relationship or intervention effect",
    "not establish mechanism",
    "仅描述",
    "观察到的趋势",
    "观察到的数据模式",
    "不建立任何机制",
    "不建立任何机制或干预效应",
    "不推断任何因果关系",
    "不推断任何因果关系或干预效果",
    "不外推机制",
    "仅描述观察到的趋势",
    "不建立机制",
    "不能推断机制",
)
_NULL_HYPOTHESIS_HINTS = (
    "null hypothesis",
    "原假设",
    "零假设",
    "no systematic",
    "distributional difference",
    "分布相同",
    "无系统性差异",
    "无差异",
    "分布无差异",
    "两组分布无系统性差异",
)
_EFFECT_SIZE_HINTS = (
    "effect size",
    "cohen",
    "eta",
    "rank-biserial",
    "效应量",
    "r =",
    "spearman rho",
    "spearman ρ",
    "rho =",
    "ρ =",
    "相关系数",
)
_CI_HINTS = ("95% ci", "95% confidence interval", "95% 置信区间", "置信区间")
_CAUSAL_HINTS = ("导致", "引发", "造成", "证明", "cause", "causes", "caused by", "drives", "impact on")
_NON_CAUSAL_HINTS = ("相关", "关联", "提示", "差异", "correlation", "associated", "association", "difference")
_TEST_HINTS = ("mann-whitney", "kruskal-wallis", "t-test", "anova", "wilcoxon", "pearson", "spearman")


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    normalized = str(text or "").lower()
    return any(keyword.lower() in normalized for keyword in keywords)


def _detect_section_presence(report_markdown: str) -> dict[str, bool]:
    sections = _iter_markdown_sections(report_markdown or "")
    normalized_sections = [(str(title or "").lower(), str(body or "").lower()) for title, body in sections]
    normalized_report = str(report_markdown or "").lower()
    section_presence: dict[str, bool] = {}
    for key, hints in _REPORT_SECTION_HINTS.items():
        section_presence[key] = any(any(hint.lower() in title for hint in hints) for title, _ in normalized_sections) or any(
            re.search(rf"^#+\s+.*{re.escape(hint.lower())}", normalized_report, re.MULTILINE) is not None
            for hint in hints
        )
    if not section_presence["limitations"]:
        section_presence["limitations"] = any(
            _contains_any(body, _LIMITATION_BODY_HINTS) for _, body in normalized_sections
        ) or _contains_any(normalized_report, _LIMITATION_BODY_HINTS)
    return section_presence


def _line_looks_like_figure_interpretation(line: str) -> bool:
    normalized = str(line or "").strip().lower()
    if not normalized or normalized.startswith("![") or normalized.startswith("#"):
        return False
    return _contains_any(normalized, _FIGURE_INTERPRETATION_HINTS)


def _count_figure_interpretations(report_markdown: str) -> tuple[int, int]:
    lines = str(report_markdown or "").splitlines()
    image_line_indices = [index for index, line in enumerate(lines) if re.search(r"!\[[^\]]*\]\(([^)]+)\)", line)]
    figure_reference_count = len(image_line_indices)
    if figure_reference_count == 0:
        return 0, 0

    interpretation_hits = 0
    for line_index in image_line_indices:
        nearby_lines = lines[max(0, line_index - 1) : min(len(lines), line_index + 10)]
        if any(_line_looks_like_figure_interpretation(line) for line in nearby_lines):
            interpretation_hits += 1
    return figure_reference_count, interpretation_hits


def _detect_task_alignment_flags(report_markdown: str, task_type: str) -> dict[str, bool]:
    normalized_report = str(report_markdown or "").lower()
    return {
        "paired_or_prepost_mentioned": _contains_any(normalized_report, _PAIRED_HINTS),
        "non_paired_declared": _contains_any(normalized_report, _NON_PAIRED_HINTS),
        "missing_value_handling_mentioned": _contains_any(normalized_report, _MISSING_HINTS),
        "outlier_handling_mentioned": _contains_any(normalized_report, _OUTLIER_HINTS),
        "small_sample_limitation_mentioned": _contains_any(normalized_report, _SMALL_SAMPLE_HINTS),
        "time_trend_boundary_mentioned": _contains_any(normalized_report, _TREND_BOUNDARY_HINTS),
        "task_type_present": bool(task_type),
    }


def _detect_statistics_flags(report_markdown: str) -> dict[str, bool]:
    normalized_report = str(report_markdown or "").lower()
    hypothesis_test_mentioned = _contains_any(normalized_report, _TEST_HINTS)
    mentions_rank_test = "mann-whitney" in normalized_report or "kruskal-wallis" in normalized_report
    mentions_causal_language = _contains_any(normalized_report, _CAUSAL_HINTS) and not _contains_any(
        normalized_report,
        _NON_CAUSAL_HINTS,
    )
    return {
        "hypothesis_test_mentioned": hypothesis_test_mentioned,
        "null_hypothesis_stated": _contains_any(normalized_report, _NULL_HYPOTHESIS_HINTS),
        "effect_size_present": _contains_any(normalized_report, _EFFECT_SIZE_HINTS),
        "ci_present": _contains_any(normalized_report, _CI_HINTS),
        "mentions_rank_test": mentions_rank_test,
        "causal_language_detected": mentions_causal_language,
    }


def _detect_evidence_flags(
    task_type: str,
    evidence_coverage: EvidenceCoverage | None,
) -> dict[str, bool]:
    coverage = evidence_coverage or EvidenceCoverage()
    citations_required = task_type == "reference_guideline_lookup" or bool(
        coverage.citation_count
        or coverage.invalid_citation_labels
        or coverage.uncited_knowledge_sections_detected
    )
    return {
        "citations_required": citations_required,
        "citations_present": coverage.citation_count > 0,
        "citation_labels_valid": not coverage.invalid_citation_labels,
        "uncited_knowledge_sections": bool(coverage.uncited_knowledge_sections_detected),
    }


def inspect_report_structure(report_markdown: str) -> dict[str, object]:
    section_presence = _detect_section_presence(report_markdown)
    figure_reference_count, figure_interpretation_hit_count = _count_figure_interpretations(report_markdown)
    task_alignment_flags = _detect_task_alignment_flags(report_markdown, "")
    return {
        "section_presence": section_presence,
        "figure_reference_count": figure_reference_count,
        "figure_interpretation_hit_count": figure_interpretation_hit_count,
        "paired_or_prepost_mentioned": task_alignment_flags["paired_or_prepost_mentioned"],
        "missing_value_handling_mentioned": task_alignment_flags["missing_value_handling_mentioned"],
        "outlier_handling_mentioned": task_alignment_flags["outlier_handling_mentioned"],
        "small_sample_limitation_mentioned": task_alignment_flags["small_sample_limitation_mentioned"],
    }


def check_report_contract(
    report_markdown: str,
    *,
    task_type: str = "",
    task_expectations: tuple[str, ...] = (),
    telemetry: ReportTelemetry | None = None,
    evidence_coverage: EvidenceCoverage | None = None,
) -> ReportContractCheckResult:
    del task_expectations  # expectations are represented through task_type-specific contract rules for v1.
    section_presence = _detect_section_presence(report_markdown)
    figure_reference_count, figure_interpretation_hit_count = _count_figure_interpretations(report_markdown)
    task_alignment_flags = _detect_task_alignment_flags(report_markdown, task_type)
    statistics_flags = _detect_statistics_flags(report_markdown)
    evidence_flags = _detect_evidence_flags(task_type, evidence_coverage)
    blocking_issues: list[str] = []
    issue_types: list[str] = []

    required_sections = (
        "data_overview",
        "cleaning_notes",
        "methods",
        "core_results",
        "figure_interpretation",
        "limitations",
        "conclusion",
    )
    missing_sections = [name for name in required_sections if not section_presence.get(name, False)]
    if missing_sections:
        blocking_issues.append("Missing required report sections: " + ", ".join(missing_sections) + ".")
        issue_types.append("report_structure_failure")

    if figure_reference_count > figure_interpretation_hit_count:
        blocking_issues.append(
            "At least one cited figure is not accompanied by a nearby interpretation sentence that explains the visual evidence."
        )
        issue_types.append("figure_interpretation_failure")

    if task_type == "before_after_paired_measure" and not task_alignment_flags["paired_or_prepost_mentioned"]:
        blocking_issues.append("This paired or before-after task must explicitly state that the same subjects were measured repeatedly.")
        issue_types.append("report_structure_failure")

    if task_type == "two_group_small_sample" and not task_alignment_flags["non_paired_declared"]:
        blocking_issues.append("This two-group task must explicitly state that it is an independent two-group comparison, not a paired or pre-post design.")
        issue_types.append("report_structure_failure")

    if task_type == "time_series_trend_clean" and not task_alignment_flags["time_trend_boundary_mentioned"]:
        blocking_issues.append("This time-trend task must explicitly state that the report describes an observed trend only and does not establish mechanism or intervention effect.")
        issue_types.append("report_structure_failure")

    if task_type == "missing_values_by_group" and not task_alignment_flags["missing_value_handling_mentioned"]:
        blocking_issues.append("This task must explicitly describe how missing values were handled and how that affects confidence in the findings.")
        issue_types.append("report_structure_failure")

    if task_type == "outlier_sensitive_measurement" and not task_alignment_flags["outlier_handling_mentioned"]:
        blocking_issues.append("This outlier-sensitive task must explicitly describe how outliers were handled and whether the conclusion depends on them.")
        issue_types.append("report_structure_failure")

    if statistics_flags["mentions_rank_test"] and not statistics_flags["null_hypothesis_stated"]:
        blocking_issues.append(
            "Rank-based hypothesis tests such as Mann-Whitney U or Kruskal-Wallis must state the null hypothesis in plain language. "
            "For Kruskal-Wallis cohort or group comparisons, name the compared groups and state that the null hypothesis is no systematic distributional difference across those groups."
        )
        issue_types.append("report_structure_failure")

    if statistics_flags["hypothesis_test_mentioned"] and not statistics_flags["effect_size_present"]:
        blocking_issues.append("Any reported hypothesis test must include an effect size.")
        issue_types.append("report_structure_failure")

    if statistics_flags["hypothesis_test_mentioned"] and not statistics_flags["ci_present"]:
        blocking_issues.append("Any reported hypothesis test must include a 95% confidence interval.")
        issue_types.append("report_structure_failure")

    if statistics_flags["causal_language_detected"] and task_type != "reference_guideline_lookup":
        blocking_issues.append("The report contains causal wording that is not justified by the current task setup.")
        issue_types.append("report_structure_failure")

    if evidence_flags["citations_required"] and not evidence_flags["citations_present"]:
        blocking_issues.append("Knowledge-based interpretation requires at least one valid inline citation from the retrieved evidence register.")
        issue_types.append("citation_evidence_failure")
    if not evidence_flags["citation_labels_valid"]:
        blocking_issues.append("The report contains an inline citation label that does not match the supplied evidence register.")
        issue_types.append("citation_evidence_failure")
    if evidence_flags["uncited_knowledge_sections"]:
        blocking_issues.append("A knowledge-based section uses background information without citing the supporting evidence register.")
        issue_types.append("citation_evidence_failure")

    if telemetry is not None and tuple(telemetry.figures_generated) and figure_reference_count == 0:
        blocking_issues.append("Figures were generated in telemetry but the report does not cite them explicitly.")
        issue_types.append("figure_interpretation_failure")

    issue_types_tuple = tuple(dict.fromkeys(issue_types))
    rule_ids = tuple(
        dict.fromkeys(
            rule_id
            for issue_type in issue_types_tuple
            for rule_id in rule_ids_for_issue_type(issue_type)
        )
    )
    return ReportContractCheckResult(
        passed=not blocking_issues,
        blocking_issues=tuple(dict.fromkeys(blocking_issues)),
        section_presence=section_presence,
        figure_reference_count=figure_reference_count,
        figure_interpretation_hit_count=figure_interpretation_hit_count,
        task_alignment_flags=task_alignment_flags,
        statistics_flags=statistics_flags,
        evidence_flags=evidence_flags,
        issue_types=issue_types_tuple,
        rule_ids=rule_ids,
    )


def format_report_contract_summary(
    contract_result: ReportContractCheckResult,
    *,
    task_type: str = "",
    task_expectations: tuple[str, ...] = (),
) -> str:
    lines = [
        f"- task_type: {task_type or 'not_provided'}",
        "- task_expectations:",
    ]
    if task_expectations:
        lines.extend(f"  - {item}" for item in task_expectations)
    else:
        lines.append("  - none")
    lines.extend(
        [
            f"- report_contract_passed: {contract_result.passed}",
            f"- report_contract_issue_types: {', '.join(contract_result.issue_types) if contract_result.issue_types else 'none'}",
            f"- report_contract_rule_ids: {', '.join(contract_result.rule_ids) if contract_result.rule_ids else 'none'}",
            "- report_structure_presence:",
            f"  - data_overview: {contract_result.section_presence.get('data_overview', False)}",
            f"  - cleaning_notes: {contract_result.section_presence.get('cleaning_notes', False)}",
            f"  - methods: {contract_result.section_presence.get('methods', False)}",
            f"  - core_results: {contract_result.section_presence.get('core_results', False)}",
            f"  - figure_interpretation: {contract_result.section_presence.get('figure_interpretation', False)}",
            f"  - limitations: {contract_result.section_presence.get('limitations', False)}",
            f"  - conclusion: {contract_result.section_presence.get('conclusion', False)}",
            f"- figure_reference_count: {contract_result.figure_reference_count}",
            f"- figure_interpretation_hit_count: {contract_result.figure_interpretation_hit_count}",
            f"- paired_or_prepost_mentioned: {contract_result.task_alignment_flags.get('paired_or_prepost_mentioned', False)}",
            f"- non_paired_declared: {contract_result.task_alignment_flags.get('non_paired_declared', False)}",
            f"- missing_value_handling_mentioned: {contract_result.task_alignment_flags.get('missing_value_handling_mentioned', False)}",
            f"- outlier_handling_mentioned: {contract_result.task_alignment_flags.get('outlier_handling_mentioned', False)}",
            f"- small_sample_limitation_mentioned: {contract_result.task_alignment_flags.get('small_sample_limitation_mentioned', False)}",
            f"- time_trend_boundary_mentioned: {contract_result.task_alignment_flags.get('time_trend_boundary_mentioned', False)}",
            f"- null_hypothesis_stated: {contract_result.statistics_flags.get('null_hypothesis_stated', False)}",
            f"- effect_size_present: {contract_result.statistics_flags.get('effect_size_present', False)}",
            f"- ci_present: {contract_result.statistics_flags.get('ci_present', False)}",
            f"- citations_required: {contract_result.evidence_flags.get('citations_required', False)}",
            f"- citations_present: {contract_result.evidence_flags.get('citations_present', False)}",
            f"- citation_labels_valid: {contract_result.evidence_flags.get('citation_labels_valid', False)}",
            f"- uncited_knowledge_sections: {contract_result.evidence_flags.get('uncited_knowledge_sections', False)}",
            "- report_contract_blocking_issues:",
        ]
    )
    if contract_result.blocking_issues:
        lines.extend(f"  - {item}" for item in contract_result.blocking_issues)
    else:
        lines.append("  - none")
    return "\n".join(lines)


def build_revision_brief(
    *,
    source: str,
    blocking_issues: tuple[str, ...],
    next_round_figures_dir: str,
) -> RevisionBrief:
    issue_text = " ".join(blocking_issues).lower()
    suggested_actions: list[str] = []
    carry_over_constraints = [
        "In the next revision round, re-run Stage 1 first: read the raw source data, save the canonical cleaned_data.csv path again, and print the save confirmation.",
        "After that Stage 1 save, run a later separate Python Stage 2 step that explicitly reloads the canonical cleaned_data.csv path before formal analysis or figure generation.",
        "Keep the report structure stable and do not remove already-correct sections.",
    ]
    if "figure" in issue_text or "图" in issue_text:
        suggested_actions.append("Revise the Figure Interpretation section so every cited figure has direct nearby interpretation sentences.")
    if "cleaning" in issue_text or "清洗" in issue_text:
        suggested_actions.append("Revise Data Cleaning Notes to state the exact cleaning choices and their downstream impact.")
    if "limitation" in issue_text or "局限" in issue_text:
        suggested_actions.append("Add or strengthen the Limitations section with a concrete interpretation boundary.")
    if "paired" in issue_text or "配对" in issue_text:
        suggested_actions.append("State the data structure explicitly as paired, repeated, or explicitly not paired depending on the task.")
    if "citation" in issue_text or "证据" in issue_text:
        suggested_actions.append("Fix inline citations so knowledge-based claims use only valid evidence-register labels.")
    if "null hypothesis" in issue_text or "原假设" in issue_text or "零假设" in issue_text:
        suggested_actions.append("State the null hypothesis in plain language when introducing or interpreting the main test.")
    if "kruskal-wallis" in issue_text:
        suggested_actions.append(
            "For the Kruskal-Wallis cohort/group comparison, add a direct sentence such as: "
            "'The null hypothesis is that the compared cohort/group distributions do not differ systematically.'"
        )
    for rule_id in ("stage.save_cleaned_data", "stage.reload_cleaned_data"):
        rule = get_symbolic_rule(rule_id)
        if rule and rule.failure_message.lower() in issue_text:
            suggested_actions.append(rule.repair_hint)
    for rule_id in (
        "report.required_sections",
        "report.figure_interpretation",
        "report.statistical_reporting",
        "report.non_causal_language",
        "evidence.valid_citations",
        "task.data_structure_alignment",
    ):
        rule = get_symbolic_rule(rule_id)
        if rule and (rule.failure_message.lower() in issue_text or rule.category in issue_text):
            suggested_actions.append(rule.repair_hint)
    if not suggested_actions:
        suggested_actions.append("Resolve every blocking issue before finishing the next round.")
    return RevisionBrief(
        source=source,
        blocking_issues=blocking_issues,
        suggested_actions=tuple(dict.fromkeys(suggested_actions)),
        carry_over_constraints=tuple(carry_over_constraints),
        next_round_figures_dir=next_round_figures_dir,
    )
