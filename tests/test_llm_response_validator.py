"""
test_llm_response_validator.py — Eval tests for LLM response contract enforcement.

These tests verify that the validator correctly enforces the output contract
from rules.md SSOT. Each test simulates a specific LLM behavior pattern
and asserts the expected validation outcome.

Test categories:
  1. Valid structured responses → VALID
  2. Decision-rule violations → INVALID
  3. Schema violations → INVALID
  4. Free-text / malformed responses → INVALID
  5. Developer response validation
  6. Edge cases
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "governance_runtime" / "application" / "validators"))
from llm_response_validator import (
    coerce_output_against_mandates_schema,
    validate_developer_response,
    validate_plan_response,
    validate_review_response,
)

_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "governance_runtime" / "assets" / "schemas" / "governance_mandates.v1.schema.json"


def _load_schema() -> dict | None:
    if not _SCHEMA_PATH.exists():
        return None
    try:
        return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


MANDATES_SCHEMA = _load_schema()


VALID_REVIEW = {
    "verdict": "changes_requested",
    "governing_evidence": "Checked src/main.py, tests/test_main.py, and openapi.yaml for contract alignment.",
    "contract_check": "No SSOT violations. API contracts preserved. No silent fallback detected.",
    "findings": [
        {
            "severity": "high",
            "type": "defect",
            "location": "src/main.py:42",
            "evidence": "Null check missing at line 42 causes NullPointerException on empty input",
            "impact": "Service crashes when request body is empty",
            "fix": "Add null check: if body is None: return 400",
        }
    ],
    "regression_assessment": "Other endpoints should be unaffected. /api/users endpoint behavior unchanged.",
    "test_assessment": "Missing negative test for empty input. Existing tests cover happy path only.",
}

VALID_APPROVE = {
    "verdict": "approve",
    "governing_evidence": "Reviewed src/utils.py and tests/. All edge cases handled. No contract drift.",
    "contract_check": "SSOT boundaries preserved. No silent fallback. Authority boundaries intact.",
    "findings": [],
    "regression_assessment": "Minimal risk. Change is isolated to utility function.",
    "test_assessment": "Tests are sufficient for the changed scope. Happy and edge cases covered.",
}


class TestReviewValidatorValidResponses:
    """Valid structured responses must pass validation."""

    def test_valid_changes_requested(self):
        r = validate_review_response(VALID_REVIEW)
        assert r.valid is True
        assert r.result.value == "valid"
        assert r.verdict == "changes_requested"
        assert r.findings_count == 1

    def test_valid_approve_no_findings(self):
        r = validate_review_response(VALID_APPROVE)
        assert r.valid is True
        assert r.verdict == "approve"
        assert r.findings_count == 0

    def test_valid_multiple_findings(self):
        data = dict(VALID_REVIEW)
        data["findings"] = [
            {
                "severity": "critical",
                "type": "defect",
                "location": "src/auth.py:10",
                "evidence": "SQL injection possible via unsanitized user input in query string",
                "impact": "Unauthorized database access",
                "fix": "Use parameterized query with bound variables",
            },
            {
                "severity": "medium",
                "type": "test-gap",
                "location": "tests/test_auth.py",
                "evidence": "No tests for authentication failure paths",
                "impact": "Auth regression goes undetected",
                "fix": "Add test cases for invalid credentials and missing tokens",
            },
        ]
        r = validate_review_response(data, MANDATES_SCHEMA)
        assert r.valid is True
        assert r.findings_count == 2


class TestReviewValidatorDecisionRules:
    """Decision-rule violations must fail validation."""

    def test_approve_with_critical_findings(self):
        data = dict(VALID_APPROVE)
        data["findings"] = [
            {
                "severity": "critical",
                "type": "defect",
                "location": "src/payment.py:1",
                "evidence": "Missing auth check exposes payment endpoint",
                "impact": "Unauthorized payment operations",
                "fix": "Add @requires_auth decorator",
            }
        ]
        r = validate_review_response(data, MANDATES_SCHEMA)
        assert r.valid is False
        assert any("approve" in v.rule.lower() and "critical" in v.rule.lower() for v in r.violations)

    def test_approve_with_high_findings(self):
        data = dict(VALID_APPROVE)
        data["findings"] = [
            {
                "severity": "high",
                "type": "risk",
                "location": "src/main.py:100",
                "evidence": "Memory leak in unbounded cache",
                "impact": "OOM over time in long-running process",
                "fix": "Add cache eviction policy",
            }
        ]
        r = validate_review_response(data, MANDATES_SCHEMA)
        assert r.valid is False
        assert any("approve" in v.rule.lower() and "high" in v.rule.lower() for v in r.violations)

    def test_changes_requested_but_no_findings(self):
        data = dict(VALID_REVIEW)
        data["findings"] = []
        r = validate_review_response(data, MANDATES_SCHEMA)
        assert r.valid is False
        assert any("changes_requested" in v.rule.lower() and "no findings" in v.rule.lower() for v in r.violations)

    def test_cannot_approve_with_defect(self):
        data = dict(VALID_APPROVE)
        data["findings"] = [
            {
                "severity": "medium",
                "type": "defect",
                "location": "src/main.py:1",
                "evidence": "Logic error in condition",
                "impact": "Wrong branch executed",
                "fix": "Fix condition",
            }
        ]
        r = validate_review_response(data, MANDATES_SCHEMA)
        assert r.valid is False


class TestReviewValidatorSchemaViolations:
    """Schema violations must fail validation."""

    def test_invalid_verdict_value(self):
        data = dict(VALID_REVIEW)
        data["verdict"] = "looks_good"
        r = validate_review_response(data, MANDATES_SCHEMA)
        assert r.valid is False

    def test_missing_required_field_governing_evidence(self):
        data = dict(VALID_REVIEW)
        del data["governing_evidence"]
        r = validate_review_response(data, MANDATES_SCHEMA)
        assert r.valid is False

    def test_missing_required_field_contract_check(self):
        data = dict(VALID_REVIEW)
        del data["contract_check"]
        r = validate_review_response(data, MANDATES_SCHEMA)
        assert r.valid is False

    def test_missing_required_field_findings(self):
        data = dict(VALID_REVIEW)
        del data["findings"]
        r = validate_review_response(data, MANDATES_SCHEMA)
        assert r.valid is False

    def test_invalid_finding_severity(self):
        data = dict(VALID_REVIEW)
        data["findings"][0]["severity"] = "critical_flaw"
        r = validate_review_response(data, MANDATES_SCHEMA)
        assert r.valid is False
        assert any("severity" in v.field.lower() for v in r.violations)

    def test_invalid_finding_type(self):
        data = dict(VALID_REVIEW)
        data["findings"][0]["type"] = "bug"
        r = validate_review_response(data, MANDATES_SCHEMA)
        assert r.valid is False

    def test_finding_too_short_location(self):
        data = dict(VALID_REVIEW)
        data["findings"][0]["location"] = "x"
        r = validate_review_response(data, MANDATES_SCHEMA)
        assert r.valid is False

    def test_finding_too_short_evidence(self):
        data = dict(VALID_REVIEW)
        data["findings"][0]["evidence"] = "too short"
        r = validate_review_response(data, MANDATES_SCHEMA)
        assert r.valid is False

    def test_not_a_dict(self):
        r = validate_review_response("all good lgtm!")
        assert r.valid is False
        assert r.verdict == "unknown"

    def test_not_a_list(self):
        r = validate_review_response(["item1", "item2"])
        assert r.valid is False

    def test_empty_string(self):
        r = validate_review_response("")
        assert r.valid is False


class TestDeveloperValidatorValidResponses:
    """Valid developer responses must pass."""

    def test_valid_developer_response(self):
        data = {
            "objective": "Add null check to src/main.py to prevent NullPointerException on empty input.",
            "governing_evidence": "Modified src/main.py:42. Contract: input must be non-null. Test: tests/test_main.py.",
            "touched_surface": ["src/main.py", "tests/test_main.py"],
            "change_summary": "Added null check guard at line 42. Returns 400 for None input.",
            "contract_and_authority_check": "SSOT boundaries preserved. No authority drift. No silent fallback.",
            "test_evidence": "Added negative test for empty input. All tests pass.",
            "regression_assessment": "Existing happy-path behavior unchanged.",
            "residual_risks": [],
        }
        r = validate_developer_response(data, MANDATES_SCHEMA)
        assert r.valid is True


class TestDeveloperValidatorSchemaViolations:
    """Developer schema violations must fail."""

    def test_empty_touched_surface(self):
        data = {
            "objective": "Fix the bug in main.py.",
            "governing_evidence": "Modified main.py.",
            "touched_surface": [],
            "change_summary": "Changed main.py",
            "contract_and_authority_check": "OK.",
            "test_evidence": "Tests pass.",
            "regression_assessment": "Minimal.",
            "residual_risks": [],
        }
        r = validate_developer_response(data, MANDATES_SCHEMA)
        assert r.valid is False

    def test_missing_objective(self):
        data = {
            "governing_evidence": "Modified main.py.",
            "touched_surface": ["src/main.py"],
            "change_summary": "Changed main.py",
            "contract_and_authority_check": "OK.",
            "test_evidence": "Tests pass.",
            "regression_assessment": "Minimal.",
            "residual_risks": [],
        }
        r = validate_developer_response(data, MANDATES_SCHEMA)
        assert r.valid is False

    def test_short_objective(self):
        data = {
            "objective": "fix bug",
            "governing_evidence": "Modified main.py.",
            "touched_surface": ["src/main.py"],
            "change_summary": "Changed main.py",
            "contract_and_authority_check": "OK.",
            "test_evidence": "Tests pass.",
            "regression_assessment": "Minimal.",
            "residual_risks": [],
        }
        r = validate_developer_response(data, MANDATES_SCHEMA)
        assert r.valid is False

    def test_not_a_dict(self):
        r = validate_developer_response("I fixed it")
        assert r.valid is False


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_all_severity_levels(self):
        for sev in ["critical", "high", "medium", "low"]:
            data = dict(VALID_REVIEW)
            data["verdict"] = "changes_requested"
            data["findings"] = [
                {
                    "severity": sev,
                    "type": "defect",
                    "location": "src/file.py:1",
                    "evidence": "Test evidence for " + sev + " severity finding",
                    "impact": "Test impact",
                    "fix": "Test fix",
                }
            ]
            r = validate_review_response(data, MANDATES_SCHEMA)
            assert r.valid is True, f"severity={sev} should be valid"

    def test_all_finding_types(self):
        for ftype in ["defect", "risk", "contract-drift", "test-gap", "improvement"]:
            data = dict(VALID_REVIEW)
            data["findings"] = [
                {
                    "severity": "low",
                    "type": ftype,
                    "location": "src/file.py:1",
                    "evidence": "Test evidence for " + ftype,
                    "impact": "Test impact",
                    "fix": "Test fix",
                }
            ]
            r = validate_review_response(data, MANDATES_SCHEMA)
            assert r.valid is True, f"type={ftype} should be valid"

    def test_empty_findings_array_is_valid_when_approved(self):
        data = dict(VALID_APPROVE)
        data["findings"] = []
        r = validate_review_response(data, MANDATES_SCHEMA)
        assert r.valid is True

    def test_null_findings_treated_as_empty(self):
        data = dict(VALID_REVIEW)
        data["findings"] = None
        r = validate_review_response(data, MANDATES_SCHEMA)
        assert r.valid is False  # Missing required field

    def test_residual_risks_can_be_empty_array(self):
        data = {
            "objective": "Add validation to endpoint.",
            "governing_evidence": "Modified src/main.py",
            "touched_surface": ["src/main.py"],
            "change_summary": "Added validation.",
            "contract_and_authority_check": "All boundaries preserved.",
            "test_evidence": "Tests pass.",
            "regression_assessment": "Minimal risk.",
            "residual_risks": [],
        }
        r = validate_developer_response(data, MANDATES_SCHEMA)
        assert r.valid is True

    def test_coerce_plan_string_fields_avoids_type_mismatch(self):
        if not isinstance(MANDATES_SCHEMA, dict):
            pytest.skip("mandates schema not available")
        defs = MANDATES_SCHEMA.get("$defs", {})
        plan_schema = defs.get("planOutputSchema")
        if not isinstance(plan_schema, dict):
            pytest.skip("planOutputSchema not available")

        raw = {
            "objective": "Create complete e2e governance evidence.",
            "target_state": {"artifacts": ["diff", "review"]},
            "target_flow": ["implement", "test", "review"],
            "state_machine": {"states": ["a", "b"]},
            "blocker_taxonomy": [{"code": "X"}],
            "audit": {"required": ["logs"]},
            "go_no_go": {"go": ["all evidence present"]},
            "test_strategy": {"scope": "full"},
            "reason_code": "PLAN-E2E-001",
            "language": "en",
            "presentation_contract": {
                "title": "Plan Presentation",
                "language": "en",
                "open_decisions": [],
                "next_actions": [
                    "/review-decision approve",
                    "/review-decision changes_requested",
                    "/review-decision reject",
                ],
            },
        }
        coerced = coerce_output_against_mandates_schema(raw, MANDATES_SCHEMA, "planOutputSchema")
        result = validate_plan_response(coerced, plan_schema=plan_schema)
        raw_rules = list(result.raw_violations)
        assert not any("target_state" in rule and "is not of type 'string'" in rule for rule in raw_rules)
        assert not any("target_flow" in rule and "is not of type 'string'" in rule for rule in raw_rules)
        assert not any("state_machine" in rule and "is not of type 'string'" in rule for rule in raw_rules)
        assert not any("blocker_taxonomy" in rule and "is not of type 'string'" in rule for rule in raw_rules)
        assert not any("audit" in rule and "is not of type 'string'" in rule for rule in raw_rules)
        assert not any("go_no_go" in rule and "is not of type 'string'" in rule for rule in raw_rules)
        assert not any("test_strategy" in rule and "is not of type 'string'" in rule for rule in raw_rules)

    def test_coerce_review_findings_when_json_string(self):
        if not isinstance(MANDATES_SCHEMA, dict):
            pytest.skip("mandates schema not available")
        raw = {
            "verdict": "changes_requested",
            "governing_evidence": "Checked src/main.py and tests/test_main.py for contract alignment.",
            "contract_check": "No SSOT violations found.",
            "findings": [
                {
                    "severity": "high",
                    "type": "defect",
                    "location": "src/main.py:42",
                    "evidence": "Null check missing in critical path when request body is empty",
                    "impact": "Service can crash on malformed request",
                    "fix": "Add explicit None guard and return 400",
                }
            ],
            "regression_assessment": "Minimal risk outside changed module.",
            "test_assessment": "Need one additional negative-path test.",
        }
        raw["findings"] = json.dumps(raw["findings"], ensure_ascii=True)
        coerced = coerce_output_against_mandates_schema(raw, MANDATES_SCHEMA, "reviewOutputSchema")
        assert isinstance(coerced, dict)
        assert isinstance(coerced.get("findings"), list)
