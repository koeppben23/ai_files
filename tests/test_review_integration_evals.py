"""
test_review_integration_evals.py — Integration E2E evals with mock executor.

These tests prove the complete enforcement chain from LLM executor call
through to parse → validate → block/proceed, using a mock subprocess.run
that injects controlled responses.

Coverage:
  1. Valid JSON, valid verdict → proceed
  2. Syntactically broken JSON → fail closed
  3. Schema-valid JSON with decision-rule violation → fail closed
  4. Free prose / non-JSON → fail closed
  5. Empty response → fail closed
  6. Executor timeout / error → fail closed
  7. Approve with defect finding → fail closed
  8. Missing required fields → fail closed

Chain:
  _call_llm_review(content, mandate)
      → writes context, calls subprocess.run (mocked)
      → response captured from stdout
      → _parse_llm_review_response(response_text, schema)
          → JSON parse? no → hard block
          → schema validate? fail → hard block
          → proceed
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from .util import REPO_ROOT


_SCHEMA_PATH = REPO_ROOT / "governance_runtime" / "assets" / "schemas" / "governance_mandates.v1.schema.json"


def _load_schema() -> dict | None:
    if not _SCHEMA_PATH.exists():
        return None
    try:
        return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


MANDATES_SCHEMA = _load_schema()


def _make_mock_run(stdout: str = "", stderr: str = "", returncode: int = 0):
    def mock_run(*args, **kwargs):
        result = type("MockResult", (), {"stdout": stdout, "stderr": stderr, "returncode": returncode})()
        return result
    return mock_run


def _call_llm_review_with_response(content: str, stdout: str, stderr: str = "", returncode: int = 0):
    script = REPO_ROOT / "governance_runtime" / "entrypoints" / "phase5_plan_record_persist.py"
    spec = importlib.util.spec_from_file_location("phase5_plan_record_persist", script)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load phase5_plan_record_persist module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    import os
    old_exec = os.environ.get("AI_GOVERNANCE_EXECUTION_BINDING")
    old_review = os.environ.get("AI_GOVERNANCE_REVIEW_BINDING")
    old_session = os.environ.get("OPENCODE_SESSION_ID")
    old_opencode = os.environ.get("OPENCODE")
    old_model = os.environ.get("OPENCODE_MODEL")
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace_dir = Path(tmpdir)
            (workspace_dir / "governance-config.json").write_text(
                json.dumps(
                    {
                        "pipeline_mode": True,
                        "presentation": {
                            "mode": "standard",
                        },
                        "review": {
                            "phase5_max_review_iterations": 3,
                            "phase6_max_review_iterations": 3,
                        },
                    },
                    ensure_ascii=True,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            os.environ["AI_GOVERNANCE_EXECUTION_BINDING"] = "mock-executor"
            os.environ["AI_GOVERNANCE_REVIEW_BINDING"] = "mock-executor"
            os.environ["OPENCODE"] = "1"
            os.environ["OPENCODE_SESSION_ID"] = "sess_review_eval"
            os.environ["OPENCODE_MODEL"] = "openai/gpt-5"

            if returncode != 0:
                def _raise_server(**kwargs):  # type: ignore[no-untyped-def]
                    raise module.ServerNotAvailableError(stderr or f"server error ({returncode})")
                module._invoke_llm_via_server = _raise_server
            else:
                module._invoke_llm_via_server = lambda **kwargs: stdout

            return module._call_llm_review(content, "mock mandate", workspace_dir=workspace_dir)
    finally:
        if old_exec is None:
            os.environ.pop("AI_GOVERNANCE_EXECUTION_BINDING", None)
        else:
            os.environ["AI_GOVERNANCE_EXECUTION_BINDING"] = old_exec
        if old_review is None:
            os.environ.pop("AI_GOVERNANCE_REVIEW_BINDING", None)
        else:
            os.environ["AI_GOVERNANCE_REVIEW_BINDING"] = old_review
        if old_session is None:
            os.environ.pop("OPENCODE_SESSION_ID", None)
        else:
            os.environ["OPENCODE_SESSION_ID"] = old_session
        if old_opencode is None:
            os.environ.pop("OPENCODE", None)
        else:
            os.environ["OPENCODE"] = old_opencode
        if old_model is None:
            os.environ.pop("OPENCODE_MODEL", None)
        else:
            os.environ["OPENCODE_MODEL"] = old_model


class TestReviewIntegrationChainE2E:
    """Integration E2E evals for the full review enforcement chain."""

    def test_valid_json_approve_no_findings_proceeds(self):
        response = json.dumps({
            "verdict": "approve",
            "governing_evidence": "Reviewed implementation against plan. All steps covered.",
            "contract_check": "SSOT boundaries preserved. No contract drift.",
            "findings": [],
            "regression_assessment": "Low risk. Changes isolated.",
            "test_assessment": "Tests cover changed scope.",
        })
        result = _call_llm_review_with_response("review this plan", response)
        assert result["llm_invoked"] is True
        assert result["validation_valid"] is True
        assert result["verdict"] == "approve"

    def test_valid_json_changes_requested_with_findings_proceeds(self):
        response = json.dumps({
            "verdict": "changes_requested",
            "governing_evidence": "Checked source against contracts.",
            "contract_check": "Minor drift in response shape.",
            "findings": [
                {
                    "severity": "high",
                    "type": "defect",
                    "location": "src/api.py:42",
                    "evidence": "Response field missing causes client breakage",
                    "impact": "Clients relying on this field will break",
                    "fix": "Add the missing field to response payload",
                }
            ],
            "regression_assessment": "Existing endpoints unaffected.",
            "test_assessment": "Tests missing for new field.",
        })
        result = _call_llm_review_with_response("review this plan", response)
        assert result["llm_invoked"] is True
        assert result["validation_valid"] is True
        assert result["verdict"] == "changes_requested"
        assert len(result["findings"]) == 1

    def test_syntactically_broken_json_fail_closed(self):
        response = '{"verdict": "approve", "findings": ['
        result = _call_llm_review_with_response("review this plan", response)
        assert result["llm_invoked"] is True
        assert result["validation_valid"] is False
        assert "response-not-structured-json" in result["validation_violations"]
        assert result["verdict"] == "changes_requested"

    def test_non_json_free_prose_fail_closed(self):
        response = "Looking good overall. I reviewed the code and it seems fine. Minor suggestions but nothing blocking."
        result = _call_llm_review_with_response("review this plan", response)
        assert result["llm_invoked"] is True
        assert result["validation_valid"] is False
        assert "response-not-structured-json" in result["validation_violations"]
        assert result["verdict"] == "changes_requested"

    def test_malformed_json_missing_brace_fail_closed(self):
        response = '"verdict": "approve", "findings": []}'
        result = _call_llm_review_with_response("review this plan", response)
        assert result["llm_invoked"] is True
        assert result["validation_valid"] is False
        assert "response-not-structured-json" in result["validation_violations"]

    def test_empty_response_fail_closed(self):
        result = _call_llm_review_with_response("review this plan", "")
        assert result["verdict"] == "changes_requested"

    def test_whitespace_only_response_fail_closed(self):
        result = _call_llm_review_with_response("review this plan", "   \n\n  ")
        assert result["verdict"] == "changes_requested"

    def test_executor_timeout_fail_closed(self):
        result = _call_llm_review_with_response("review this plan", "", returncode=124)
        assert result["verdict"] == "changes_requested"

    def test_executor_error_fail_closed(self):
        result = _call_llm_review_with_response("review this plan", "", returncode=1, stderr="LLM provider error")
        assert result["verdict"] == "changes_requested"

    def test_approve_with_critical_defect_fail_closed(self):
        response = json.dumps({
            "verdict": "approve",
            "governing_evidence": "Reviewed code.",
            "contract_check": "OK.",
            "findings": [
                {
                    "severity": "critical",
                    "type": "defect",
                    "location": "src/auth.py:1",
                    "evidence": "Auth bypass via missing token check",
                    "impact": "Anyone can access protected endpoints",
                    "fix": "Add token validation",
                }
            ],
            "regression_assessment": "All endpoints affected.",
            "test_assessment": "No tests for auth.",
        })
        result = _call_llm_review_with_response("review this plan", response)
        assert result["llm_invoked"] is True
        assert result["validation_valid"] is False
        violations = result.get("validation_violations", [])
        assert any("defect" in v.lower() for v in violations)
        assert result["verdict"] == "changes_requested"

    def test_approve_with_medium_defect_fail_closed(self):
        response = json.dumps({
            "verdict": "approve",
            "governing_evidence": "Looks fine.",
            "contract_check": "No issues.",
            "findings": [
                {
                    "severity": "medium",
                    "type": "defect",
                    "location": "src/main.py:1",
                    "evidence": "Logic error in condition",
                    "impact": "Wrong branch executed",
                    "fix": "Fix condition",
                }
            ],
            "regression_assessment": "Most endpoints affected.",
            "test_assessment": "Insufficient coverage.",
        })
        result = _call_llm_review_with_response("review this plan", response)
        assert result["llm_invoked"] is True
        assert result["validation_valid"] is False
        violations = result.get("validation_violations", [])
        assert any("defect" in v.lower() for v in violations)

    def test_missing_required_field_governing_evidence_fail_closed(self):
        response = json.dumps({
            "verdict": "changes_requested",
            "contract_check": "OK.",
            "findings": [
                {
                    "severity": "high",
                    "type": "defect",
                    "location": "src/main.py:42",
                    "evidence": "Missing null check causes crash",
                    "impact": "Crash on empty input",
                    "fix": "Add null guard",
                }
            ],
            "regression_assessment": "Other endpoints unaffected.",
            "test_assessment": "Tests sufficient.",
        })
        result = _call_llm_review_with_response("review this plan", response)
        assert result["llm_invoked"] is True
        assert result["validation_valid"] is False
        violations = result.get("validation_violations", [])
        assert any("governing_evidence" in v or "required" in v.lower() for v in violations)

    def test_missing_required_field_contract_check_fail_closed(self):
        response = json.dumps({
            "verdict": "changes_requested",
            "governing_evidence": "Reviewed code.",
            "findings": [
                {
                    "severity": "high",
                    "type": "defect",
                    "location": "src/main.py:42",
                    "evidence": "Missing null check causes crash",
                    "impact": "Crash on empty input",
                    "fix": "Add null guard",
                }
            ],
            "regression_assessment": "Other endpoints unaffected.",
            "test_assessment": "Tests sufficient.",
        })
        result = _call_llm_review_with_response("review this plan", response)
        assert result["llm_invoked"] is True
        assert result["validation_valid"] is False
        violations = result.get("validation_violations", [])
        assert any("contract_check" in v or "required" in v.lower() for v in violations)

    def test_invalid_verdict_value_fail_closed(self):
        response = json.dumps({
            "verdict": "looks_good",
            "governing_evidence": "Reviewed all files.",
            "contract_check": "No issues found.",
            "findings": [],
            "regression_assessment": "Minimal risk.",
            "test_assessment": "Tests sufficient.",
        })
        result = _call_llm_review_with_response("review this plan", response)
        assert result["llm_invoked"] is True
        assert result["validation_valid"] is False
        assert result["verdict"] == "changes_requested"

    def test_changes_requested_without_findings_fail_closed(self):
        response = json.dumps({
            "verdict": "changes_requested",
            "governing_evidence": "Something needs fixing.",
            "contract_check": "Minor drift.",
            "findings": [],
            "regression_assessment": "Low risk.",
            "test_assessment": "Tests adequate.",
        })
        result = _call_llm_review_with_response("review this plan", response)
        assert result["llm_invoked"] is True
        assert result["validation_valid"] is False
        violations = result.get("validation_violations", [])
        assert any("changes_requested" in v.lower() and "no findings" in v.lower() for v in violations)

    def test_json_array_response_fail_closed(self):
        response = json.dumps([{"verdict": "approve"}, {"note": "all good"}])
        result = _call_llm_review_with_response("review this plan", response)
        assert result["llm_invoked"] is True
        assert result["validation_valid"] is False
        assert "response-not-structured-json" in result.get("validation_violations", [])

    def test_valid_multiple_findings_proceeds(self):
        response = json.dumps({
            "verdict": "changes_requested",
            "governing_evidence": "Reviewed all changed files.",
            "contract_check": "Two contract drifts found.",
            "findings": [
                {
                    "severity": "high",
                    "type": "contract-drift",
                    "location": "src/api.py:10",
                    "evidence": "Response field removed without deprecation",
                    "impact": "Breaking change for existing clients",
                    "fix": "Mark field deprecated before removal",
                },
                {
                    "severity": "medium",
                    "type": "test-gap",
                    "location": "tests/test_api.py",
                    "evidence": "No tests for new response shape",
                    "impact": "Regression goes undetected",
                    "fix": "Add integration tests for new response",
                },
            ],
            "regression_assessment": "Existing endpoints affected.",
            "test_assessment": "Insufficient coverage for new behavior.",
        })
        result = _call_llm_review_with_response("review this plan", response)
        assert result["llm_invoked"] is True
        assert result["validation_valid"] is True
        assert result["verdict"] == "changes_requested"
        assert len(result["findings"]) == 2

    def test_findings_with_invalid_severity_fail_closed(self):
        response = json.dumps({
            "verdict": "changes_requested",
            "governing_evidence": "Reviewed code.",
            "contract_check": "Minor issues.",
            "findings": [
                {
                    "severity": "BLOCKER",
                    "type": "defect",
                    "location": "src/main.py:1",
                    "evidence": "Bug in code",
                    "impact": "Service fails",
                    "fix": "Fix bug",
                }
            ],
            "regression_assessment": "Low risk.",
            "test_assessment": "Tests adequate.",
        })
        result = _call_llm_review_with_response("review this plan", response)
        assert result["llm_invoked"] is True
        assert result["validation_valid"] is False
        violations = result.get("validation_violations", [])
        assert any("severity" in v.lower() for v in violations)

    def test_findings_with_invalid_type_fail_closed(self):
        response = json.dumps({
            "verdict": "changes_requested",
            "governing_evidence": "Reviewed code.",
            "contract_check": "Issues found.",
            "findings": [
                {
                    "severity": "high",
                    "type": "bug",
                    "location": "src/main.py:1",
                    "evidence": "Bug in code",
                    "impact": "Service fails",
                    "fix": "Fix bug",
                }
            ],
            "regression_assessment": "Low risk.",
            "test_assessment": "Tests adequate.",
        })
        result = _call_llm_review_with_response("review this plan", response)
        assert result["llm_invoked"] is True
        assert result["validation_valid"] is False
        violations = result.get("validation_violations", [])
        assert any("type" in v.lower() for v in violations)

    def test_finding_location_too_short_fail_closed(self):
        response = json.dumps({
            "verdict": "changes_requested",
            "governing_evidence": "Reviewed code.",
            "contract_check": "Issue found.",
            "findings": [
                {
                    "severity": "high",
                    "type": "defect",
                    "location": "x",
                    "evidence": "Bug in code",
                    "impact": "Service fails",
                    "fix": "Fix bug",
                }
            ],
            "regression_assessment": "Low risk.",
            "test_assessment": "Tests adequate.",
        })
        result = _call_llm_review_with_response("review this plan", response)
        assert result["llm_invoked"] is True
        assert result["validation_valid"] is False
        violations = result.get("validation_violations", [])
        assert any("location" in v.lower() for v in violations)
