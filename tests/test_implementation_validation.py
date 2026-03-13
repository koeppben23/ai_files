from __future__ import annotations

from governance.engine.implementation_validation import (
    CheckResult,
    ExecutorRunResult,
    RC_GOVERNANCE_ONLY_CHANGES,
    RC_PLAN_COVERAGE_MISSING,
    RC_TARGETED_CHECKS_FAILED,
    RC_TARGETED_CHECKS_MISSING,
    build_plan_coverage,
    split_domain_changed_files,
    validate_implementation,
)


def test_happy_validation_passes_with_domain_diff_coverage_and_checks() -> None:
    domain_files = split_domain_changed_files(
        ["src/service.py", ".governance/implementation/llm_edit_context.json"],
        forbidden_prefixes=(".governance/",),
    )
    coverage = build_plan_coverage(
        requirements=[{"id": "PLAN-STEP-001", "code_hotspots": ["src/service.py"]}],
        domain_changed_files=domain_files,
    )
    report = validate_implementation(
        executor_result=ExecutorRunResult(
            executor_invoked=True,
            exit_code=0,
            stdout_path="stdout.log",
            stderr_path="stderr.log",
            changed_files=("src/service.py",),
            domain_changed_files=domain_files,
            governance_only_changes=False,
        ),
        plan_coverage=coverage,
        checks=(CheckResult(name="tests::happy", passed=True, exit_code=0, output_path="checks.log"),),
    )
    assert report.is_compliant is True
    assert report.reason_codes == ()


def test_bad_governance_only_changes_fail_closed() -> None:
    coverage = build_plan_coverage(
        requirements=[{"id": "PLAN-STEP-001", "code_hotspots": ["src/service.py"]}],
        domain_changed_files=(),
    )
    report = validate_implementation(
        executor_result=ExecutorRunResult(
            executor_invoked=True,
            exit_code=0,
            stdout_path="stdout.log",
            stderr_path="stderr.log",
            changed_files=(".governance/implementation/llm_edit_context.json",),
            domain_changed_files=(),
            governance_only_changes=True,
        ),
        plan_coverage=coverage,
        checks=(CheckResult(name="tests::happy", passed=True, exit_code=0, output_path="checks.log"),),
    )
    assert report.is_compliant is False
    assert RC_GOVERNANCE_ONLY_CHANGES in report.reason_codes
    assert RC_PLAN_COVERAGE_MISSING in report.reason_codes


def test_corner_missing_checks_blocks() -> None:
    report = validate_implementation(
        executor_result=ExecutorRunResult(
            executor_invoked=True,
            exit_code=0,
            stdout_path="stdout.log",
            stderr_path="stderr.log",
            changed_files=("src/service.py",),
            domain_changed_files=("src/service.py",),
            governance_only_changes=False,
        ),
        plan_coverage=(
            build_plan_coverage(
                requirements=[{"id": "PLAN-STEP-001", "code_hotspots": ["src/service.py"]}],
                domain_changed_files=("src/service.py",),
            )[0],
        ),
        checks=(),
    )
    assert report.is_compliant is False
    assert RC_TARGETED_CHECKS_MISSING in report.reason_codes


def test_edge_failing_checks_blocks() -> None:
    report = validate_implementation(
        executor_result=ExecutorRunResult(
            executor_invoked=True,
            exit_code=0,
            stdout_path="stdout.log",
            stderr_path="stderr.log",
            changed_files=("src/service.py",),
            domain_changed_files=("src/service.py",),
            governance_only_changes=False,
        ),
        plan_coverage=(
            build_plan_coverage(
                requirements=[{"id": "PLAN-STEP-001", "code_hotspots": ["src/service.py"]}],
                domain_changed_files=("src/service.py",),
            )[0],
        ),
        checks=(CheckResult(name="tests::fails", passed=False, exit_code=1, output_path="checks.log"),),
    )
    assert report.is_compliant is False
    assert RC_TARGETED_CHECKS_FAILED in report.reason_codes
