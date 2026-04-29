"""Symbolic rule catalog for governance prompts, verifiers, and ablations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
try:  # pragma: no cover - Python 3.7 compatibility for local test environments
    from typing import Literal
except ImportError:  # pragma: no cover
    class _LiteralFallback:
        def __getitem__(self, _item):
            return str

    Literal = _LiteralFallback()


SymbolicProfile = Literal["full", "prompt_only", "none"]
RuleSeverity = Literal["blocking", "warning", "info"]


@dataclass(frozen=True)
class SymbolicRule:
    rule_id: str
    category: str
    description: str
    severity: RuleSeverity
    prompt_text: str | None
    checker_name: str | None
    failure_message: str
    repair_hint: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


SYMBOLIC_RULES: tuple[SymbolicRule, ...] = (
    SymbolicRule(
        rule_id="stage.save_cleaned_data",
        category="execution_audit",
        description="Stage 1 must save the canonical cleaned_data.csv artifact.",
        severity="blocking",
        prompt_text="Stage 1 must save the cleaned dataset to the canonical cleaned_data.csv path and print a save confirmation.",
        checker_name="audit_stage_execution",
        failure_message="No Python step explicitly saved the canonical cleaned_data.csv path.",
        repair_hint="Re-run Stage 1, read the raw source data, save cleaned_data.csv, and print the saved path.",
    ),
    SymbolicRule(
        rule_id="stage.reload_cleaned_data",
        category="execution_audit",
        description="Stage 2 must explicitly reload cleaned_data.csv in a later Python step.",
        severity="blocking",
        prompt_text="Stage 2 must reload the canonical cleaned_data.csv path in a later Python step before formal analysis.",
        checker_name="audit_stage_execution",
        failure_message="No later Python step explicitly reloaded the canonical cleaned_data.csv path.",
        repair_hint="Run a separate Stage 2 Python step that reads cleaned_data.csv before statistics or plotting.",
    ),
    SymbolicRule(
        rule_id="stage.no_raw_reuse",
        category="execution_audit",
        description="Formal analysis must not re-read the raw source after Stage 1.",
        severity="blocking",
        prompt_text="Do not keep using the raw source file as the primary analytical input after cleaned_data.csv has been saved.",
        checker_name="audit_stage_execution",
        failure_message="A later Python step re-read the raw source dataset after Stage 1 completed.",
        repair_hint="Replace post-cleaning raw-file reads with reads from the canonical cleaned_data.csv path.",
    ),
    SymbolicRule(
        rule_id="report.required_sections",
        category="report_contract",
        description="The final report must include the required academic sections.",
        severity="blocking",
        prompt_text="The final report must contain Data Overview, Data Cleaning Notes, Methods, Core Statistical Results, Figure Interpretation, Limitations, and Conclusion.",
        checker_name="check_report_contract",
        failure_message="Missing required report sections.",
        repair_hint="Add the missing sections without removing already-correct report content.",
    ),
    SymbolicRule(
        rule_id="report.figure_interpretation",
        category="report_contract",
        description="Every cited figure must have nearby interpretation text.",
        severity="blocking",
        prompt_text="Every cited figure must be accompanied by nearby sentences explaining the visual evidence and statistical takeaway.",
        checker_name="check_report_contract",
        failure_message="At least one cited figure is not accompanied by a nearby interpretation sentence.",
        repair_hint="Revise Figure Interpretation so each figure reference has direct explanatory sentences.",
    ),
    SymbolicRule(
        rule_id="report.statistical_reporting",
        category="report_contract",
        description="Hypothesis tests must report effect sizes and confidence intervals.",
        severity="blocking",
        prompt_text="If a hypothesis test is reported, include the test statistic, p-value, effect size, and 95% confidence interval together.",
        checker_name="check_report_contract",
        failure_message="A reported hypothesis test is missing an effect size or 95% confidence interval.",
        repair_hint="Add the missing effect size, confidence interval, and plain-language null hypothesis where applicable.",
    ),
    SymbolicRule(
        rule_id="report.non_causal_language",
        category="report_contract",
        description="Observational reports must avoid unsupported causal wording.",
        severity="blocking",
        prompt_text="Without experimental design, random assignment, or causal identification evidence, use association language rather than causal language.",
        checker_name="check_report_contract",
        failure_message="The report contains causal wording that is not justified by the current task setup.",
        repair_hint="Replace causal claims with conservative association, difference, or observed-pattern wording.",
    ),
    SymbolicRule(
        rule_id="evidence.valid_citations",
        category="evidence",
        description="Knowledge-based claims must cite valid evidence-register labels.",
        severity="blocking",
        prompt_text="Knowledge-based interpretation must use only inline citation labels supplied in the retrieved evidence register.",
        checker_name="check_report_contract",
        failure_message="Knowledge-based interpretation lacks a valid inline citation from the evidence register.",
        repair_hint="Add or fix citations using only labels present in the retrieved evidence register.",
    ),
    SymbolicRule(
        rule_id="task.data_structure_alignment",
        category="task_alignment",
        description="Methods and wording must match paired, independent-group, time-trend, missing-value, or outlier-sensitive task structure.",
        severity="blocking",
        prompt_text="State the task-relevant data structure explicitly and choose methods that match it.",
        checker_name="check_report_contract",
        failure_message="The report does not explicitly match the task-specific data structure or handling requirement.",
        repair_hint="State the design or data issue directly and align the method and limitations with that structure.",
    ),
)

_RULES_BY_ID = {rule.rule_id: rule for rule in SYMBOLIC_RULES}
_ISSUE_TYPE_RULE_IDS: dict[str, tuple[str, ...]] = {
    "report_structure_failure": (
        "report.required_sections",
        "report.figure_interpretation",
        "task.data_structure_alignment",
    ),
    "figure_interpretation_failure": ("report.figure_interpretation",),
    "citation_evidence_failure": ("evidence.valid_citations",),
    "execution_audit_failure": (
        "stage.save_cleaned_data",
        "stage.reload_cleaned_data",
        "stage.no_raw_reuse",
    ),
}
_FINDING_TYPE_RULE_IDS: dict[str, str] = {
    "missing_stage1_save": "stage.save_cleaned_data",
    "ambiguous_stage1_save": "stage.save_cleaned_data",
    "missing_cleaned_file": "stage.save_cleaned_data",
    "missing_stage2_reload": "stage.reload_cleaned_data",
    "ambiguous_stage2_reload": "stage.reload_cleaned_data",
    "raw_data_reused_after_stage1": "stage.no_raw_reuse",
}


def resolve_symbolic_profile(value: str) -> SymbolicProfile:
    normalized = str(value or "full").strip().lower().replace("-", "_")
    if normalized not in {"full", "prompt_only", "none"}:
        raise ValueError(f"Unsupported symbolic_profile: {value}")
    return normalized  # type: ignore[return-value]


def get_symbolic_rules() -> tuple[SymbolicRule, ...]:
    return SYMBOLIC_RULES


def get_symbolic_rule(rule_id: str) -> SymbolicRule | None:
    return _RULES_BY_ID.get(str(rule_id or "").strip())


def rule_ids_for_issue_type(issue_type: str) -> tuple[str, ...]:
    return _ISSUE_TYPE_RULE_IDS.get(str(issue_type or "").strip(), ())


def rule_id_for_stage_finding(finding_type: str) -> str:
    return _FINDING_TYPE_RULE_IDS.get(str(finding_type or "").strip(), "execution_audit_failure")


def rules_for_prompt() -> tuple[SymbolicRule, ...]:
    return tuple(rule for rule in SYMBOLIC_RULES if rule.prompt_text)


def format_symbolic_rule_catalog_for_prompt() -> str:
    lines = ["<Symbolic_Rule_Catalog>"]
    for rule in rules_for_prompt():
        lines.append(f"- {rule.rule_id}: {rule.prompt_text}")
    lines.append("</Symbolic_Rule_Catalog>")
    return "\n".join(lines)
