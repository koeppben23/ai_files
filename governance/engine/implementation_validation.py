from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from governance.infrastructure.fs_atomic import atomic_write_text


RC_EXECUTOR_NOT_CONFIGURED = "IMPLEMENTATION_LLM_EXECUTOR_NOT_CONFIGURED"
RC_EXECUTOR_FAILED = "IMPLEMENTATION_LLM_EXECUTOR_FAILED"
RC_NO_REPO_CHANGES = "IMPLEMENTATION_NO_REPO_CHANGES"
RC_GOVERNANCE_ONLY_CHANGES = "IMPLEMENTATION_GOVERNANCE_ONLY_CHANGES"
RC_NO_DOMAIN_DIFFS = "IMPLEMENTATION_NO_DOMAIN_DIFFS"
RC_PLAN_COVERAGE_MISSING = "IMPLEMENTATION_PLAN_COVERAGE_MISSING"
RC_TARGETED_CHECKS_MISSING = "IMPLEMENTATION_TARGETED_CHECKS_MISSING"
RC_TARGETED_CHECKS_FAILED = "IMPLEMENTATION_TARGETED_CHECKS_FAILED"
RC_FORBIDDEN_PATH_CHANGED = "IMPLEMENTATION_FORBIDDEN_PATH_CHANGED"
RC_EMPTY_DIFF = "IMPLEMENTATION_EMPTY_DIFF"
RC_EXECUTOR_OUTPUT_MISSING = "IMPLEMENTATION_EXECUTOR_OUTPUT_MISSING"


@dataclass(frozen=True)
class ExecutorRunResult:
    executor_invoked: bool
    exit_code: int
    stdout_path: str | None
    stderr_path: str | None
    changed_files: tuple[str, ...]
    domain_changed_files: tuple[str, ...]
    governance_only_changes: bool


@dataclass(frozen=True)
class PlanCoverageItem:
    plan_ref: str
    satisfied: bool
    evidence_files: tuple[str, ...]
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    exit_code: int | None
    output_path: str | None


@dataclass(frozen=True)
class ImplementationValidationReport:
    executor_invoked: bool
    executor_succeeded: bool
    has_domain_diffs: bool
    governance_only_changes: bool
    changed_files: tuple[str, ...]
    domain_changed_files: tuple[str, ...]
    plan_coverage: tuple[PlanCoverageItem, ...]
    checks: tuple[CheckResult, ...]
    reason_codes: tuple[str, ...]
    is_compliant: bool


def _is_forbidden_path(path: str, forbidden_prefixes: tuple[str, ...]) -> bool:
    normalized = str(path or "").strip().replace("\\", "/")
    return any(normalized.startswith(prefix) for prefix in forbidden_prefixes)


def split_domain_changed_files(changed_files: Iterable[str], *, forbidden_prefixes: tuple[str, ...]) -> tuple[str, ...]:
    out: list[str] = []
    for token in changed_files:
        path = str(token or "").strip().replace("\\", "/")
        if not path:
            continue
        if _is_forbidden_path(path, forbidden_prefixes):
            continue
        out.append(path)
    return tuple(sorted(set(out)))


def build_plan_coverage(
    *,
    requirements: list[dict[str, object]],
    domain_changed_files: tuple[str, ...],
) -> tuple[PlanCoverageItem, ...]:
    changed_set = set(domain_changed_files)
    items: list[PlanCoverageItem] = []
    for idx, requirement in enumerate(requirements, start=1):
        req_id = str(requirement.get("id") or f"PLAN-STEP-{idx:03d}").strip()
        hotspots = requirement.get("code_hotspots")
        hotspot_paths = [str(x).strip() for x in hotspots] if isinstance(hotspots, list) else []
        required_code_change = bool(hotspot_paths)
        evidence = tuple(sorted({p for p in hotspot_paths if p in changed_set}))
        satisfied = bool(evidence) if required_code_change else bool(domain_changed_files)
        reason_codes: tuple[str, ...] = ()
        if required_code_change and not satisfied:
            reason_codes = (RC_PLAN_COVERAGE_MISSING,)
        items.append(
            PlanCoverageItem(
                plan_ref=req_id,
                satisfied=satisfied,
                evidence_files=evidence,
                reason_codes=reason_codes,
            )
        )
    return tuple(items)


def validate_implementation(
    *,
    executor_result: ExecutorRunResult,
    plan_coverage: tuple[PlanCoverageItem, ...],
    checks: tuple[CheckResult, ...],
    forbidden_paths_changed: bool = False,
) -> ImplementationValidationReport:
    reason_codes: list[str] = []

    if not executor_result.executor_invoked:
        reason_codes.append(RC_EXECUTOR_NOT_CONFIGURED)
    if executor_result.executor_invoked and executor_result.exit_code != 0:
        reason_codes.append(RC_EXECUTOR_FAILED)
    if executor_result.executor_invoked and not executor_result.stdout_path and not executor_result.stderr_path:
        reason_codes.append(RC_EXECUTOR_OUTPUT_MISSING)

    if not executor_result.changed_files:
        reason_codes.append(RC_NO_REPO_CHANGES)
        reason_codes.append(RC_EMPTY_DIFF)

    has_domain_diffs = bool(executor_result.domain_changed_files)
    if executor_result.changed_files and not has_domain_diffs:
        reason_codes.append(RC_NO_DOMAIN_DIFFS)
        if executor_result.governance_only_changes:
            reason_codes.append(RC_GOVERNANCE_ONLY_CHANGES)

    if forbidden_paths_changed:
        reason_codes.append(RC_FORBIDDEN_PATH_CHANGED)

    if not plan_coverage:
        reason_codes.append(RC_PLAN_COVERAGE_MISSING)
    elif any(not item.satisfied for item in plan_coverage):
        reason_codes.append(RC_PLAN_COVERAGE_MISSING)

    if not checks:
        reason_codes.append(RC_TARGETED_CHECKS_MISSING)
    elif any(not check.passed for check in checks):
        reason_codes.append(RC_TARGETED_CHECKS_FAILED)

    unique_reasons = tuple(dict.fromkeys(reason_codes))
    is_compliant = len(unique_reasons) == 0
    return ImplementationValidationReport(
        executor_invoked=executor_result.executor_invoked,
        executor_succeeded=executor_result.executor_invoked and executor_result.exit_code == 0,
        has_domain_diffs=has_domain_diffs,
        governance_only_changes=executor_result.governance_only_changes,
        changed_files=executor_result.changed_files,
        domain_changed_files=executor_result.domain_changed_files,
        plan_coverage=plan_coverage,
        checks=checks,
        reason_codes=unique_reasons,
        is_compliant=is_compliant,
    )


def to_report_payload(report: ImplementationValidationReport) -> dict[str, object]:
    return {
        "executor_invoked": report.executor_invoked,
        "executor_succeeded": report.executor_succeeded,
        "has_domain_diffs": report.has_domain_diffs,
        "governance_only_changes": report.governance_only_changes,
        "changed_files": list(report.changed_files),
        "domain_changed_files": list(report.domain_changed_files),
        "plan_coverage": [
            {
                "plan_ref": item.plan_ref,
                "satisfied": item.satisfied,
                "evidence_files": list(item.evidence_files),
                "reason_codes": list(item.reason_codes),
            }
            for item in report.plan_coverage
        ],
        "checks": [
            {
                "name": item.name,
                "passed": item.passed,
                "exit_code": item.exit_code,
                "output_path": item.output_path,
            }
            for item in report.checks
        ],
        "reason_codes": list(report.reason_codes),
        "is_compliant": report.is_compliant,
    }


def report_to_human_lines(report: ImplementationValidationReport) -> list[str]:
    lines: list[str] = []
    lines.append(f"Implementation Validation: {'PASSED' if report.is_compliant else 'FAILED'}")
    lines.append(f"Executor invoked: {'true' if report.executor_invoked else 'false'}")
    lines.append(f"Changed files: {len(report.changed_files)}")
    lines.append(f"Domain files changed: {len(report.domain_changed_files)}")
    covered = sum(1 for item in report.plan_coverage if item.satisfied)
    total = len(report.plan_coverage)
    lines.append(f"Plan coverage: {covered}/{total}")
    checks_ok = sum(1 for item in report.checks if item.passed)
    lines.append(f"Checks passed: {checks_ok}/{len(report.checks)}")
    return lines


def write_validation_report(path: Path, report: ImplementationValidationReport) -> None:
    payload = to_report_payload(report)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, __import__("json").dumps(payload, ensure_ascii=True, indent=2) + "\n")
