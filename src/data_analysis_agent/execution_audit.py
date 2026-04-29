"""Execution-stage contract audit for two-stage tabular analysis."""

from __future__ import annotations

import ast
from pathlib import Path

from .runtime_models import AgentStepTrace, StageExecutionAuditResult, StageExecutionFinding
from .symbolic_rules import rule_id_for_stage_finding

_SUPPORTED_READ_FUNCS = {"read_csv", "read_excel"}
_SUPPORTED_WRITE_METHODS = {"to_csv", "to_excel"}


def audit_stage_execution(
    *,
    step_traces: tuple[AgentStepTrace, ...],
    source_data_path: str | Path,
    cleaned_data_path: str | Path,
) -> StageExecutionAuditResult:
    python_steps = tuple(
        trace
        for trace in step_traces
        if trace.tool_name == "PythonInterpreterTool"
        and trace.tool_status in {"success", "partial"}
        and str(trace.tool_input or "").strip()
    )
    if not python_steps:
        return StageExecutionAuditResult(
            status="skipped",
            findings=(
                StageExecutionFinding(
                    finding_type="missing_python_steps",
                    message="No successful Python analysis steps were available for stage-contract audit.",
                    rule_id="execution_audit_failure",
                ),
            ),
        )

    source_candidates = _build_path_candidates(Path(source_data_path))
    cleaned_candidates = _build_path_candidates(Path(cleaned_data_path))
    findings: list[StageExecutionFinding] = []
    evidence_steps: list[int] = []
    stage1_step: int | None = None
    stage2_step: int | None = None
    raw_reuse_step: int | None = None
    ambiguous_after_stage1 = False
    ambiguous_save_detected = False

    for trace in python_steps:
        operations, step_findings = _inspect_python_step(
            code=trace.tool_input,
            step_index=trace.step_index,
            source_candidates=source_candidates,
            cleaned_candidates=cleaned_candidates,
        )
        findings.extend(step_findings)
        if stage1_step is None:
            if any(item["kind"] == "cleaned" and item["operation"] == "write" for item in operations):
                stage1_step = trace.step_index
                evidence_steps.append(trace.step_index)
            elif any(item["kind"] == "ambiguous" and item["operation"] == "write" for item in operations):
                ambiguous_save_detected = True
            continue

        if any(item["kind"] == "raw" and item["operation"] == "read" for item in operations):
            raw_reuse_step = trace.step_index
            evidence_steps.append(trace.step_index)
        if any(item["kind"] == "cleaned" and item["operation"] == "read" for item in operations) and stage2_step is None:
            stage2_step = trace.step_index
            evidence_steps.append(trace.step_index)
        if any(item["kind"] == "ambiguous" for item in operations):
            ambiguous_after_stage1 = True

    if stage1_step is None:
        if ambiguous_save_detected:
            findings.append(
                StageExecutionFinding(
                    finding_type="ambiguous_stage1_save",
                    message="Stage 1 appears to save cleaned data via an unsupported dynamic path pattern, so compliance cannot be proven.",
                    rule_id=rule_id_for_stage_finding("ambiguous_stage1_save"),
                )
            )
            return _finalize_audit(
                status="ambiguous",
                stage1=False,
                stage2=False,
                raw_reuse=False,
                findings=findings,
                evidence_steps=evidence_steps,
            )
        findings.append(
            StageExecutionFinding(
                finding_type="missing_stage1_save",
                message="No Python step explicitly saved the canonical cleaned_data.csv path.",
                rule_id=rule_id_for_stage_finding("missing_stage1_save"),
            )
        )
        return _finalize_audit(
            status="failed",
            stage1=False,
            stage2=False,
            raw_reuse=False,
            findings=findings,
            evidence_steps=evidence_steps,
        )

    if not Path(cleaned_data_path).exists():
        findings.append(
            StageExecutionFinding(
                finding_type="missing_cleaned_file",
                message="A Stage 1 save step was detected, but the canonical cleaned_data.csv file does not exist.",
                step_index=stage1_step,
                rule_id=rule_id_for_stage_finding("missing_cleaned_file"),
            )
        )
        return _finalize_audit(
            status="failed",
            stage1=True,
            stage2=stage2_step is not None,
            raw_reuse=raw_reuse_step is not None,
            findings=findings,
            evidence_steps=evidence_steps,
        )

    if raw_reuse_step is not None:
        findings.append(
            StageExecutionFinding(
                finding_type="raw_data_reused_after_stage1",
                message="A later Python step re-read the raw source dataset after Stage 1 completed.",
                step_index=raw_reuse_step,
                rule_id=rule_id_for_stage_finding("raw_data_reused_after_stage1"),
            )
        )
        return _finalize_audit(
            status="failed",
            stage1=True,
            stage2=stage2_step is not None,
            raw_reuse=True,
            findings=findings,
            evidence_steps=evidence_steps,
        )

    if stage2_step is None:
        status = "ambiguous" if ambiguous_after_stage1 else "failed"
        findings.append(
            StageExecutionFinding(
                finding_type="missing_stage2_reload" if status == "failed" else "ambiguous_stage2_reload",
                message=(
                    "No later Python step explicitly reloaded the canonical cleaned_data.csv path."
                    if status == "failed"
                    else "Later Python steps used unsupported file-access patterns, so a compliant Stage 2 reload cannot be proven."
                ),
                step_index=stage1_step,
                rule_id=rule_id_for_stage_finding("missing_stage2_reload" if status == "failed" else "ambiguous_stage2_reload"),
            )
        )
        return _finalize_audit(
            status=status,
            stage1=True,
            stage2=False,
            raw_reuse=False,
            findings=findings,
            evidence_steps=evidence_steps,
        )

    if ambiguous_after_stage1:
        findings.append(
            StageExecutionFinding(
                finding_type="ambiguous_post_stage1_access",
                message="At least one post-Stage-1 Python step used unsupported file-access patterns, so compliance cannot be proven conservatively.",
                rule_id="execution_audit_failure",
            )
        )
        return _finalize_audit(
            status="ambiguous",
            stage1=True,
            stage2=True,
            raw_reuse=False,
            findings=findings,
            evidence_steps=evidence_steps,
        )

    findings.append(
        StageExecutionFinding(
            finding_type="stage_contract_passed",
            message="Detected canonical cleaned_data.csv save in Stage 1 and explicit reload in a later Python step.",
            step_index=stage2_step,
            rule_id="",
        )
    )
    return _finalize_audit(
        status="passed",
        stage1=True,
        stage2=True,
        raw_reuse=False,
        findings=findings,
        evidence_steps=evidence_steps,
    )


def _finalize_audit(
    *,
    status: str,
    stage1: bool,
    stage2: bool,
    raw_reuse: bool,
    findings: list[StageExecutionFinding],
    evidence_steps: list[int],
) -> StageExecutionAuditResult:
    return StageExecutionAuditResult(
        status=status,
        stage1_save_detected=stage1,
        stage2_cleaned_reload_detected=stage2,
        raw_data_reused_after_stage1=raw_reuse,
        findings=tuple(findings),
        evidence_step_indices=tuple(dict.fromkeys(evidence_steps)),
    )


def _build_path_candidates(path: Path) -> set[str]:
    candidates = {_normalize_path_text(path.as_posix()), _normalize_path_text(str(path))}
    try:
        candidates.add(_normalize_path_text(path.resolve().as_posix()))
    except Exception:
        pass
    try:
        relative = path.resolve().relative_to(Path.cwd().resolve())
    except Exception:
        relative = None
    if relative is not None:
        candidates.add(_normalize_path_text(relative.as_posix()))
        candidates.add(_normalize_path_text(str(relative)))
    return {item for item in candidates if item}


def _normalize_path_text(value: str) -> str:
    return str(value or "").strip().replace("\\", "/")


def _inspect_python_step(
    *,
    code: str,
    step_index: int,
    source_candidates: set[str],
    cleaned_candidates: set[str],
) -> tuple[list[dict[str, str]], list[StageExecutionFinding]]:
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [], [
            StageExecutionFinding(
                finding_type="unparseable_python",
                message=f"Python code could not be parsed for execution audit: {exc.msg}",
                step_index=step_index,
                rule_id="execution_audit_failure",
            )
        ]

    visitor = _PathAuditVisitor(
        step_index=step_index,
        source_candidates=source_candidates,
        cleaned_candidates=cleaned_candidates,
    )
    visitor.visit(tree)
    return visitor.operations, visitor.findings


class _PathAuditVisitor(ast.NodeVisitor):
    def __init__(
        self,
        *,
        step_index: int,
        source_candidates: set[str],
        cleaned_candidates: set[str],
    ) -> None:
        self.step_index = step_index
        self.source_candidates = source_candidates
        self.cleaned_candidates = cleaned_candidates
        self.variable_kinds: dict[str, str] = {}
        self.variable_literals: dict[str, str] = {}
        self.operations: list[dict[str, str]] = []
        self.findings: list[StageExecutionFinding] = []

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
        literal = self._resolve_path_text(node.value)
        kind = self._resolve_path_kind(node.value)
        for target in node.targets:
            if isinstance(target, ast.Name):
                if literal:
                    self.variable_literals[target.id] = literal
                if kind in {"raw", "cleaned"}:
                    self.variable_kinds[target.id] = kind
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:  # noqa: N802
        literal = self._resolve_path_text(node.value)
        kind = self._resolve_path_kind(node.value)
        if isinstance(node.target, ast.Name):
            if literal:
                self.variable_literals[node.target.id] = literal
            if kind in {"raw", "cleaned"}:
                self.variable_kinds[node.target.id] = kind
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        operation = self._classify_file_operation(node)
        if operation is not None:
            kind = self._resolve_path_kind(operation["path_node"])
            if kind is None:
                kind = "ambiguous"
                self.findings.append(
                    StageExecutionFinding(
                        finding_type=f"ambiguous_{operation['operation']}_path",
                        message=(
                            f"Step {self.step_index} uses an unsupported dynamic path pattern for "
                            f"{operation['label']}, so stage-contract compliance cannot be proven."
                        ),
                        step_index=self.step_index,
                        rule_id="execution_audit_failure",
                    )
                )
            self.operations.append({"operation": operation["operation"], "kind": kind})
        self.generic_visit(node)

    def _classify_file_operation(self, node: ast.Call) -> dict[str, object] | None:
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in _SUPPORTED_WRITE_METHODS and node.args:
            return {"operation": "write", "path_node": node.args[0], "label": func.attr}
        name = ""
        if isinstance(func, ast.Attribute):
            name = func.attr
        elif isinstance(func, ast.Name):
            name = func.id
        if name in _SUPPORTED_READ_FUNCS and node.args:
            return {"operation": "read", "path_node": node.args[0], "label": name}
        return None

    def _resolve_path_kind(self, node: ast.AST | None) -> str | None:
        if node is None:
            return None
        if isinstance(node, ast.Str):
            return self._match_literal(node.s)
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return self._match_literal(node.value)
        if isinstance(node, ast.Name):
            return self.variable_kinds.get(node.id) or self._match_literal(self.variable_literals.get(node.id, ""))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.args:
            if node.func.id in {"Path", "str"}:
                return self._resolve_path_kind(node.args[0])
        literal = self._resolve_path_text(node)
        if literal:
            return self._match_literal(literal)
        return None

    def _resolve_path_text(self, node: ast.AST | None) -> str:
        if node is None:
            return ""
        if isinstance(node, ast.Str):
            return _normalize_path_text(node.s)
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return _normalize_path_text(node.value)
        if isinstance(node, ast.Name):
            return self.variable_literals.get(node.id, "")
        if isinstance(node, ast.Call):
            func = node.func
            func_name = ""
            if isinstance(func, ast.Attribute):
                func_name = func.attr
            elif isinstance(func, ast.Name):
                func_name = func.id
            if func_name in {"Path", "str"} and node.args:
                return self._resolve_path_text(node.args[0])
            if func_name == "join" and node.args:
                parts = [self._resolve_path_text(arg).strip("/") for arg in node.args]
                if all(parts):
                    first = parts[0]
                    rest = [part for part in parts[1:] if part]
                    return _normalize_path_text("/".join([first, *rest]))
        return ""

    def _match_literal(self, value: str) -> str | None:
        normalized = _normalize_path_text(value)
        if normalized in self.cleaned_candidates:
            return "cleaned"
        if normalized in self.source_candidates:
            return "raw"
        return None
