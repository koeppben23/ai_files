"""Tests for plan compliance validation at Phase 6 entry.

Covers validate_plan_compliance (tiered status logic) and
evaluate_p6_plan_compliance (mode-dependent enforcement).
"""

from __future__ import annotations

import pytest

from governance_runtime.application.use_cases.validate_plan_compliance import (
    PlanComplianceReport,
    validate_plan_compliance,
)
from governance_runtime.engine.gate_evaluator import (
    P6PlanComplianceEvaluation,
    evaluate_p6_plan_compliance,
)
from governance_runtime.domain.reason_codes import (
    BLOCKED_P6_PLAN_COMPLIANCE_MAJOR,
    REASON_CODE_NONE,
    WARN_P6_PLAN_COMPLIANCE_DRIFT,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _plan_record(
    *,
    files_planned: list[str] | None = None,
    contracts_planned: list[str] | None = None,
    test_strategy: list[str] | None = None,
) -> dict:
    """Build a minimal plan-record dict with one version."""
    return {
        "schema_version": "1.0.0",
        "repo_fingerprint": "a" * 24,
        "status": "active",
        "versions": [
            {
                "version": 1,
                "timestamp": "2026-03-01T12:00:00+00:00",
                "phase": "4",
                "session_run_id": "sess-001",
                "content_hash": "sha256:" + "a" * 64,
                "supersedes": None,
                "trigger": "initial",
                "feature_complexity": {
                    "class": "COMPLEX",
                    "reason": "test",
                    "planning_depth": "full",
                },
                "ticket_record": {
                    "context": "ctx",
                    "decision": "dec",
                    "rationale": "rat",
                    "consequences": "con",
                    "rollback": "rb",
                },
                "nfr_checklist": {
                    "security_privacy": {"status": "N/A", "detail": "n/a"},
                    "observability": {"status": "OK", "detail": "ok"},
                    "performance": {"status": "OK", "detail": "ok"},
                    "migration_compatibility": {"status": "N/A", "detail": "n/a"},
                    "rollback_release_safety": {"status": "OK", "detail": "ok"},
                },
                "test_strategy": test_strategy if test_strategy is not None else ["Unit tests"],
                "touched_surface": {
                    "files_planned": files_planned or [],
                    "contracts_planned": contracts_planned or [],
                    "schema_planned": [],
                },
            }
        ],
    }


# ---------------------------------------------------------------------------
# validate_plan_compliance — core logic
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestValidatePlanCompliance:

    def test_no_plan_record_returns_no_plan(self) -> None:
        report = validate_plan_compliance(
            plan_record=None,
            actual_files_changed=["src/foo.py"],
        )
        assert report.status == "no-plan"
        assert report.reason == "no-plan-record-found"
        assert report.plan_version is None

    def test_empty_versions_returns_no_plan(self) -> None:
        plan = {"versions": []}
        report = validate_plan_compliance(
            plan_record=plan,
            actual_files_changed=["src/foo.py"],
        )
        assert report.status == "no-plan"
        assert report.reason == "plan-record-has-no-versions"

    def test_perfect_compliance(self) -> None:
        plan = _plan_record(files_planned=["src/foo.py", "src/bar.py"])
        report = validate_plan_compliance(
            plan_record=plan,
            actual_files_changed=["src/foo.py", "src/bar.py"],
        )
        assert report.status == "compliant"
        assert report.plan_version == 1
        assert len(report.files_unplanned) == 0
        assert len(report.files_missing) == 0

    def test_minor_drift_with_few_unplanned_files(self) -> None:
        """1-2 unplanned files below the threshold -> drift-detected."""
        plan = _plan_record(files_planned=["src/foo.py", "src/bar.py"])
        report = validate_plan_compliance(
            plan_record=plan,
            actual_files_changed=["src/foo.py", "src/bar.py", "src/extra.py"],
        )
        assert report.status == "drift-detected"
        assert "src/extra.py" in report.files_unplanned

    def test_major_deviation_many_unplanned_files(self) -> None:
        """Many unplanned files (>50% ratio, >=3 count) -> major-deviation."""
        plan = _plan_record(files_planned=["src/foo.py"])
        unplanned = [f"src/extra{i}.py" for i in range(5)]
        report = validate_plan_compliance(
            plan_record=plan,
            actual_files_changed=["src/foo.py"] + unplanned,
        )
        assert report.status == "major-deviation"

    def test_missing_contract_is_major(self) -> None:
        """Missing a planned contract -> major-deviation."""
        plan = _plan_record(
            files_planned=["src/foo.py"],
            contracts_planned=["api/v1/users"],
        )
        report = validate_plan_compliance(
            plan_record=plan,
            actual_files_changed=["src/foo.py"],
            actual_contracts_changed=[],
        )
        assert report.status == "major-deviation"
        assert "api/v1/users" in report.contracts_missing

    def test_unplanned_contract_is_major(self) -> None:
        """Unplanned contract change -> major-deviation."""
        plan = _plan_record(files_planned=["src/foo.py"])
        report = validate_plan_compliance(
            plan_record=plan,
            actual_files_changed=["src/foo.py"],
            actual_contracts_changed=["api/v2/orders"],
        )
        assert report.status == "major-deviation"
        assert "api/v2/orders" in report.contracts_unplanned

    def test_most_planned_files_missing_is_major(self) -> None:
        """Most planned files not changed -> major-deviation."""
        planned = [f"src/planned{i}.py" for i in range(6)]
        plan = _plan_record(files_planned=planned)
        report = validate_plan_compliance(
            plan_record=plan,
            actual_files_changed=["src/planned0.py"],
        )
        assert report.status == "major-deviation"

    def test_path_normalization_backslash(self) -> None:
        """Backslash paths are normalized to forward slashes."""
        plan = _plan_record(files_planned=["src/foo.py"])
        report = validate_plan_compliance(
            plan_record=plan,
            actual_files_changed=["src\\foo.py"],
        )
        assert report.status == "compliant"

    def test_drift_details_populated(self) -> None:
        plan = _plan_record(files_planned=["src/foo.py"])
        report = validate_plan_compliance(
            plan_record=plan,
            actual_files_changed=["src/foo.py", "src/extra.py"],
        )
        assert len(report.drift_details) > 0
        assert any("unplanned" in d.lower() or "not in plan" in d.lower() for d in report.drift_details)

    def test_test_strategy_present_flag(self) -> None:
        plan = _plan_record(test_strategy=["Run unit tests"])
        report = validate_plan_compliance(
            plan_record=plan,
            actual_files_changed=[],
        )
        assert report.test_strategy_present is True

    def test_test_strategy_absent_flag(self) -> None:
        plan = _plan_record(test_strategy=[])
        report = validate_plan_compliance(
            plan_record=plan,
            actual_files_changed=[],
        )
        assert report.test_strategy_present is False

    def test_test_files_found_passed_through(self) -> None:
        plan = _plan_record(files_planned=[])
        report = validate_plan_compliance(
            plan_record=plan,
            actual_files_changed=[],
            test_files_found=["tests/test_foo.py"],
        )
        assert "tests/test_foo.py" in report.test_files_found

    def test_uses_latest_version(self) -> None:
        """When multiple versions exist, uses the latest."""
        plan = _plan_record(files_planned=["src/old.py"])
        # Add a second version with different planned files
        plan["versions"].append({
            "version": 2,
            "timestamp": "2026-03-02T12:00:00+00:00",
            "phase": "4",
            "session_run_id": "sess-002",
            "content_hash": "sha256:" + "b" * 64,
            "supersedes": 1,
            "trigger": "self_review_revision",
            "feature_complexity": plan["versions"][0]["feature_complexity"],
            "ticket_record": plan["versions"][0]["ticket_record"],
            "nfr_checklist": plan["versions"][0]["nfr_checklist"],
            "test_strategy": ["Tests v2"],
            "touched_surface": {
                "files_planned": ["src/new.py"],
                "contracts_planned": [],
                "schema_planned": [],
            },
        })
        report = validate_plan_compliance(
            plan_record=plan,
            actual_files_changed=["src/new.py"],
        )
        assert report.status == "compliant"
        assert report.plan_version == 2


# ---------------------------------------------------------------------------
# evaluate_p6_plan_compliance — mode-dependent enforcement
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestEvaluateP6PlanCompliance:

    def test_compliant_no_block(self) -> None:
        plan = _plan_record(files_planned=["src/foo.py"])
        result = evaluate_p6_plan_compliance(
            plan_record=plan,
            actual_files_changed=["src/foo.py"],
            mode="user",
        )
        assert result.status == "compliant"
        assert result.reason_code == REASON_CODE_NONE
        assert result.blocked is False

    def test_no_plan_warns_only(self) -> None:
        result = evaluate_p6_plan_compliance(
            plan_record=None,
            actual_files_changed=["src/foo.py"],
            mode="pipeline",
        )
        assert result.status == "no-plan"
        assert result.reason_code == WARN_P6_PLAN_COMPLIANCE_DRIFT
        assert result.blocked is False

    def test_drift_detected_user_mode_no_block(self) -> None:
        plan = _plan_record(files_planned=["src/foo.py"])
        result = evaluate_p6_plan_compliance(
            plan_record=plan,
            actual_files_changed=["src/foo.py", "src/extra.py"],
            mode="user",
        )
        assert result.status == "drift-detected"
        assert result.reason_code == WARN_P6_PLAN_COMPLIANCE_DRIFT
        assert result.blocked is False

    def test_drift_detected_pipeline_mode_no_block(self) -> None:
        """drift-detected is never a hard block, even in pipeline mode."""
        plan = _plan_record(files_planned=["src/foo.py"])
        result = evaluate_p6_plan_compliance(
            plan_record=plan,
            actual_files_changed=["src/foo.py", "src/extra.py"],
            mode="pipeline",
        )
        assert result.status == "drift-detected"
        assert result.blocked is False

    def test_major_deviation_user_mode_warns(self) -> None:
        """major-deviation in user mode -> WARN, not blocked."""
        plan = _plan_record(
            files_planned=["src/foo.py"],
            contracts_planned=["api/v1/users"],
        )
        result = evaluate_p6_plan_compliance(
            plan_record=plan,
            actual_files_changed=["src/foo.py"],
            actual_contracts_changed=[],
            mode="user",
        )
        assert result.status == "major-deviation"
        assert result.reason_code == WARN_P6_PLAN_COMPLIANCE_DRIFT
        assert result.blocked is False

    def test_major_deviation_pipeline_mode_blocks(self) -> None:
        """major-deviation in pipeline mode -> BLOCKED, hard block."""
        plan = _plan_record(
            files_planned=["src/foo.py"],
            contracts_planned=["api/v1/users"],
        )
        result = evaluate_p6_plan_compliance(
            plan_record=plan,
            actual_files_changed=["src/foo.py"],
            actual_contracts_changed=[],
            mode="pipeline",
        )
        assert result.status == "major-deviation"
        assert result.reason_code == BLOCKED_P6_PLAN_COMPLIANCE_MAJOR
        assert result.blocked is True

    def test_report_attached_to_result(self) -> None:
        plan = _plan_record(files_planned=["src/foo.py"])
        result = evaluate_p6_plan_compliance(
            plan_record=plan,
            actual_files_changed=["src/foo.py"],
            mode="user",
        )
        assert isinstance(result.report, PlanComplianceReport)

    def test_reason_codes_are_registered(self) -> None:
        from governance_runtime.domain.reason_codes import is_registered_reason_code

        assert is_registered_reason_code(BLOCKED_P6_PLAN_COMPLIANCE_MAJOR, allow_none=False)
        assert is_registered_reason_code(WARN_P6_PLAN_COMPLIANCE_DRIFT, allow_none=False)
