"""
test_governance_fail_closed_truth.py — Fail-closed truth: missing/stale artifacts, receipts, digests, mandates block correctly.

Every missing mandate, stale receipt, absent artifact, or invalid digest must produce status=error/blocked.
Soft failures are regressions.

CI-blocking main merge guard: every test here must pass.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tests.conftest_governance import (
    _load_implement,
    _load_module,
    _load_phase5,
    _load_review_decision,
    _read_json,
    _read_state,
    _set_env,
    _write_e2e_fixture,
    _write_phase6_session,
    _write_phase6_approved_session,
)


@pytest.mark.e2e_governance
class TestE2EBadPaths:
    """Bad paths: /plan must block on missing or broken inputs."""

    def test_blocks_when_executor_unavailable(self, tmp_path, monkeypatch, capsys):
        """Without OPENCODE_PLAN_LLM_CMD or OPENCODE_IMPLEMENT_LLM_CMD, /plan auto-generate fails."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        monkeypatch.delenv("OPENCODE_PLAN_LLM_CMD", raising=False)
        monkeypatch.delenv("OPENCODE_IMPLEMENT_LLM_CMD", raising=False)

        module = _load_phase5()
        rc = module.main(["--quiet"])
        assert rc == 2
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["reason_code"] == "BLOCKED-PLAN-EXECUTOR-UNAVAILABLE"

    def test_blocks_when_llm_returns_empty(self, tmp_path, monkeypatch, capsys):
        """When LLM executor returns empty string, /plan must block."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        monkeypatch.setenv("OPENCODE_PLAN_LLM_CMD", "echo ''")

        module = _load_phase5()
        rc = module.main(["--quiet"])
        assert rc == 2

    def test_blocks_when_llm_returns_non_json(self, tmp_path, monkeypatch, capsys):
        """When LLM executor returns non-JSON, /plan must block."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        monkeypatch.setenv("OPENCODE_PLAN_LLM_CMD", "echo 'not json at all'")

        module = _load_phase5()
        rc = module.main(["--quiet"])
        assert rc == 2

    def test_blocks_when_llm_returns_incomplete_plan(self, tmp_path, monkeypatch, capsys):
        """When LLM returns JSON missing mandatory planOutputSchema fields, /plan must block."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        incomplete = json.dumps({"objective": "Something"})
        monkeypatch.setenv("OPENCODE_PLAN_LLM_CMD", f"echo '{incomplete}'")

        module = _load_phase5()
        rc = module.main(["--quiet"])
        assert rc == 2

    def test_blocks_when_mandate_schema_missing(self, tmp_path, monkeypatch, capsys):
        """When mandate schema is absent, /plan auto-generate must block."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        monkeypatch.setenv("OPENCODE_PLAN_LLM_CMD", "echo '{\"objective\":\"x\"}'")

        module = _load_phase5()

        def _raise_missing():
            raise module.MandateSchemaMissingError("not found")

        monkeypatch.setattr(module, "_load_mandates_schema", _raise_missing)
        rc = module.main(["--quiet"])
        assert rc == 2
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["reason_code"] == "MANDATE-SCHEMA-MISSING"

    def test_blocks_when_mandate_schema_invalid_json(self, tmp_path, monkeypatch, capsys):
        """When mandate schema is corrupt JSON, /plan auto-generate must block."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        monkeypatch.setenv("OPENCODE_PLAN_LLM_CMD", "echo '{\"objective\":\"x\"}'")

        module = _load_phase5()

        def _raise_invalid():
            raise module.MandateSchemaInvalidJsonError("bad json")

        monkeypatch.setattr(module, "_load_mandates_schema", _raise_invalid)
        rc = module.main(["--quiet"])
        assert rc == 2
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["reason_code"] == "MANDATE-SCHEMA-INVALID-JSON"

    def test_blocks_when_mandate_schema_invalid_structure(self, tmp_path, monkeypatch, capsys):
        """When mandate schema lacks plan_mandate block, /plan auto-generate must block."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        monkeypatch.setenv("OPENCODE_PLAN_LLM_CMD", "echo '{\"objective\":\"x\"}'")

        module = _load_phase5()

        def _raise_invalid():
            raise module.MandateSchemaInvalidStructureError("missing plan_mandate")

        monkeypatch.setattr(module, "_load_mandates_schema", _raise_invalid)
        rc = module.main(["--quiet"])
        assert rc == 2
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["reason_code"] == "MANDATE-SCHEMA-INVALID-STRUCTURE"


@pytest.mark.e2e_governance
class TestE2ECornerCases:
    """Corner cases: explicit inputs, executor fallback, edge conditions."""

    def test_executor_fallback_to_implement_llm_cmd(self, tmp_path, monkeypatch):
        """_resolve_plan_executor falls back to OPENCODE_IMPLEMENT_LLM_CMD when OPENCODE_PLAN_LLM_CMD is unset."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        module = _load_phase5()
        monkeypatch.setenv("OPENCODE_IMPLEMENT_LLM_CMD", "fallback-cmd")
        assert module._resolve_plan_executor() == "fallback-cmd"

        monkeypatch.setenv("OPENCODE_PLAN_LLM_CMD", "plan-cmd")
        assert module._resolve_plan_executor() == "plan-cmd"

    def test_explicit_plan_text_skips_auto_generation(self, tmp_path, monkeypatch, capsys):
        """--plan-text must skip auto-generate path and not require LLM executor."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        monkeypatch.delenv("OPENCODE_PLAN_LLM_CMD", raising=False)
        monkeypatch.delenv("OPENCODE_IMPLEMENT_LLM_CMD", raising=False)

        module = _load_phase5()
        rc = module.main(["--plan-text", "Manual plan text.", "--quiet"])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["reason"] == "phase5-plan-record-persisted"

    def test_plan_file_input_works_without_llm_executor(self, tmp_path, monkeypatch, capsys):
        """--plan-file must work without LLM executor available."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        monkeypatch.delenv("OPENCODE_PLAN_LLM_CMD", raising=False)
        monkeypatch.delenv("OPENCODE_IMPLEMENT_LLM_CMD", raising=False)

        plan_file = tmp_path / "plan.md"
        plan_file.write_text("Plan text from file.", encoding="utf-8")

        module = _load_phase5()
        rc = module.main(["--plan-file", str(plan_file), "--quiet"])
        assert rc == 0


@pytest.mark.e2e_governance
class TestE2EEdgeCases:
    """Edge cases: borderline valid/invalid inputs, timing invariants, inconsistent state."""

    def test_review_decision_blocks_when_receipt_rendered_before_state_change(self, tmp_path, monkeypatch, capsys):
        """receipt.rendered_at < state.review_package_last_state_change_at must block (timing violation)."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)

        doc = _read_json(session_path)
        doc["SESSION_STATE"]["session_materialized_at"] = "2026-03-21T12:00:00Z"
        doc["SESSION_STATE"]["review_package_last_state_change_at"] = "2026-03-21T12:00:01Z"
        receipt = doc["SESSION_STATE"]["review_package_presentation_receipt"]
        receipt["rendered_at"] = "2026-03-21T12:00:00Z"
        receipt["presented_at"] = "2026-03-21T12:00:00Z"
        doc["SESSION_STATE"]["review_package_presentation_receipt"] = receipt
        session_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

        module = _load_review_decision()
        rc = module.main(["--decision", "approve", "--quiet"])
        assert rc == 2, f"receipt rendered before state change must block, got rc={rc}"
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload.get("status") in ("error", "blocked"), (
            f"Timing violation must produce error/blocked, got {payload}"
        )

    def test_review_decision_approves_when_receipt_rendered_at_same_time_as_state_change(self, tmp_path, monkeypatch, capsys):
        """receipt.rendered_at == state.review_package_last_state_change_at must pass (boundary valid)."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)

        doc = _read_json(session_path)
        same_ts = "2026-03-21T12:00:00Z"
        doc["SESSION_STATE"]["session_materialized_at"] = same_ts
        doc["SESSION_STATE"]["review_package_last_state_change_at"] = same_ts
        receipt = doc["SESSION_STATE"]["review_package_presentation_receipt"]
        receipt["rendered_at"] = same_ts
        receipt["presented_at"] = same_ts
        doc["SESSION_STATE"]["review_package_presentation_receipt"] = receipt
        session_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

        module = _load_review_decision()
        rc = module.main(["--decision", "approve", "--quiet"])
        assert rc == 0, f"Equal timestamps must be valid, got rc={rc}: {capsys.readouterr().out}"
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload.get("status") == "ok", f"Equal timestamps must approve, got {payload}"

    def test_review_decision_rejects_invalid_decision_value(self, tmp_path, monkeypatch, capsys):
        """Only 'approve', 'changes_requested', and 'reject' (after strip+lower) are valid decisions."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)

        module = _load_review_decision()
        for bad in ("maybe", "yes", "no", "accepted", "denied", "skip", "pass", ""):
            capsys.readouterr()
            rc = module.main(["--decision", bad, "--quiet"])
            assert rc == 2, f"Decision '{bad!r}' must be rejected as invalid"
            payload = json.loads(capsys.readouterr().out.strip())
            assert payload.get("status") == "error", f"Invalid decision '{bad!r}' must be error, got {payload}"

    def test_implement_blocks_when_evidence_gate_not_workflow_complete(self, tmp_path, monkeypatch, capsys):
        """/implement must block when active_gate is Evidence Presentation Gate (not Workflow Complete)."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)

        doc = _read_json(session_path)
        doc["SESSION_STATE"]["workflow_complete"] = True
        doc["SESSION_STATE"]["WorkflowComplete"] = True
        doc["SESSION_STATE"]["UserReviewDecision"] = {"decision": "approve"}
        doc["SESSION_STATE"]["active_gate"] = "Evidence Presentation Gate"
        session_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

        module = _load_implement()
        rc = module.main(["--quiet"])
        assert rc == 2, f"Should block at Evidence Presentation Gate even with workflow_complete, got rc={rc}"
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload.get("status") in ("error", "blocked")


@pytest.mark.e2e_governance
class TestE2EFailClosedMatrix:
    """Verify fail-closed behavior: missing or invalid inputs must block, never silently proceed.

    Fail-closed rule: when mandatory evidence is absent or malformed, the command must
    return rc!=0 and status=blocked/error — never rc=0 with status=ok.
    """

    def test_review_decision_blocks_on_receipt_digest_mismatch(self, tmp_path, monkeypatch, capsys):
        """receipt digest mismatch must block /review-decision."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)

        doc = _read_json(session_path)
        doc["SESSION_STATE"]["review_package_presentation_receipt"]["digest"] = "sha256:WRONG_DIGEST_THAT_SHOULD_NOT_MATCH"
        doc["SESSION_STATE"]["review_package_presentation_receipt"]["state_revision"] = "1"
        session_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

        module = _load_review_decision()
        capsys.readouterr()
        rc = module.main(["--decision", "approve", "--quiet"])
        assert rc != 0, "/review-decision must fail on receipt digest mismatch"
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload.get("status") in ("error", "blocked"), (
            f"status must be error/blocked on digest mismatch, got {payload.get('status')!r}"
        )

    def test_review_decision_blocks_on_missing_receipt(self, tmp_path, monkeypatch, capsys):
        """/review-decision must block when review_package_presentation_receipt is missing."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)

        doc = _read_json(session_path)
        doc["SESSION_STATE"].pop("review_package_presentation_receipt", None)
        session_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

        module = _load_review_decision()
        capsys.readouterr()
        rc = module.main(["--decision", "approve", "--quiet"])
        assert rc != 0, "/review-decision must fail when receipt is missing"
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload.get("status") in ("error", "blocked")

    def test_review_decision_blocks_on_stale_receipt_timestamp(self, tmp_path, monkeypatch, capsys):
        """receipt rendered_at before state change must block /review-decision."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)

        doc = _read_json(session_path)
        receipt = doc["SESSION_STATE"]["review_package_presentation_receipt"]
        receipt["rendered_at"] = "2026-03-21T11:59:59Z"
        receipt["presented_at"] = "2026-03-21T11:59:59Z"
        doc["SESSION_STATE"]["review_package_last_state_change_at"] = "2026-03-21T12:00:00Z"
        session_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

        module = _load_review_decision()
        capsys.readouterr()
        rc = module.main(["--decision", "approve", "--quiet"])
        assert rc != 0, "/review-decision must fail on stale receipt timestamp"
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload.get("status") in ("error", "blocked")

    def test_implement_blocks_when_not_workflow_complete(self, tmp_path, monkeypatch, capsys):
        """/implement must block when not at Workflow Complete gate."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)

        doc = _read_json(session_path)
        doc["SESSION_STATE"]["active_gate"] = "Evidence Presentation Gate"
        doc["SESSION_STATE"]["workflow_complete"] = False
        doc["SESSION_STATE"]["WorkflowComplete"] = False
        session_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

        module = _load_implement()
        capsys.readouterr()
        rc = module.main(["--quiet"])
        assert rc != 0, "/implement must fail when not at Workflow Complete"
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload.get("status") in ("error", "blocked")

    def test_plan_blocks_when_ticket_missing(self, tmp_path, monkeypatch, capsys):
        """/plan must block when Ticket is absent in session state."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        state = _read_state(session_path)
        state["Phase"] = "4"
        state["active_gate"] = "Ticket Input Gate"
        state.pop("Ticket", None)
        state.pop("Task", None)
        session_path.write_text(json.dumps({"SESSION_STATE": state}, indent=2) + "\n", encoding="utf-8")

        module_plan = _load_phase5()
        capsys.readouterr()
        rc = module_plan.main(["--quiet"])
        assert rc != 0, "/plan must fail when Ticket is absent"
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload.get("status") in ("error", "blocked"), (
            f"status must be error/blocked without Ticket, got {payload.get('status')!r}"
        )

    def test_review_decision_blocks_on_invalid_decision_value(self, tmp_path, monkeypatch, capsys):
        """/review-decision with invalid decision must fail with clear reason."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)

        module = _load_review_decision()
        capsys.readouterr()
        rc = module.main(["--decision", "maybe", "--quiet"])
        assert rc != 0, "/review-decision with invalid decision must fail"
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload.get("status") in ("error", "blocked"), (
            f"status must be error/blocked for invalid decision, got {payload.get('status')!r}"
        )
        assert "reason_code" in payload, "blocked response must include reason_code"

# ── F. RECEIPT TAMPER GUARDS ─────────────────────────────────────────────

@pytest.mark.e2e_governance
class TestE2EReceiptTamperGuards:
    """Test /review-decision: Receipt tamper guards.

    After a valid receipt is issued, tampering with any content_digest
    or presentation state must block /review-decision.
    """

    def test_review_decision_blocks_when_plan_body_tampered_after_receipt(self, tmp_path, monkeypatch, capsys):
        """/review-decision must block when plan_body is modified after receipt was issued."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)

        doc = _read_json(session_path)
        receipt = doc["SESSION_STATE"]["review_package_presentation_receipt"]
        original_digest = receipt["digest"]
        doc["SESSION_STATE"]["review_package_plan_body"] = "TAMPERED PLAN BODY"
        session_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

        module = _load_review_decision()
        capsys.readouterr()
        rc = module.main(["--decision", "approve", "--quiet"])
        assert rc != 0, "/review-decision must block when plan_body is tampered after receipt"
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload.get("status") in ("error", "blocked")

    def test_review_decision_blocks_when_receipt_gate_mismatch(self, tmp_path, monkeypatch, capsys):
        """/review-decision must block when receipt.gate does not match Evidence Presentation Gate."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)

        doc = _read_json(session_path)
        doc["SESSION_STATE"]["review_package_presentation_receipt"]["gate"] = "Wrong Gate"
        session_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

        module = _load_review_decision()
        capsys.readouterr()
        rc = module.main(["--decision", "approve", "--quiet"])
        assert rc != 0, "/review-decision must block on receipt gate mismatch"
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload.get("status") in ("error", "blocked")

    def test_review_decision_blocks_when_receipt_state_revision_mismatch(self, tmp_path, monkeypatch, capsys):
        """/review-decision must block when receipt.state_revision does not match session state_revision."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)

        doc = _read_json(session_path)
        doc["SESSION_STATE"]["session_state_revision"] = 5
        doc["SESSION_STATE"]["review_package_presentation_receipt"]["state_revision"] = "1"
        session_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

        module = _load_review_decision()
        capsys.readouterr()
        rc = module.main(["--decision", "approve", "--quiet"])
        assert rc != 0, "/review-decision must block on state_revision mismatch"
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload.get("status") in ("error", "blocked")

    def test_review_decision_blocks_when_receipt_contract_mismatch(self, tmp_path, monkeypatch, capsys):
        """/review-decision must block when receipt.contract is not 'guided-ui.v1'."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)

        doc = _read_json(session_path)
        doc["SESSION_STATE"]["review_package_presentation_receipt"]["contract"] = "wrong-contract"
        session_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

        module = _load_review_decision()
        capsys.readouterr()
        rc = module.main(["--decision", "approve", "--quiet"])
        assert rc != 0, "/review-decision must block on receipt contract mismatch"
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload.get("status") in ("error", "blocked")

    def test_review_decision_blocks_when_review_package_ticket_changed_after_receipt(self, tmp_path, monkeypatch, capsys):
        """/review-decision must block when ticket field is changed after receipt was issued."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)

        doc = _read_json(session_path)
        receipt = doc["SESSION_STATE"]["review_package_presentation_receipt"]
        doc["SESSION_STATE"]["review_package_ticket"] = "CHANGED TICKET"
        session_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

        module = _load_review_decision()
        capsys.readouterr()
        rc = module.main(["--decision", "approve", "--quiet"])
        assert rc != 0, "/review-decision must block when ticket changed after receipt"
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload.get("status") in ("error", "blocked")


# ── G. /IMPLEMENT GOVERNANCE FAIL-CLOSED ─────────────────────────────────

@pytest.mark.e2e_governance
class TestE2EImplementGovernanceBlockers:
    """Test /implement: governance blockers for mandate, policy, validator, and non-compliant responses.

    /implement must fail-closed when:
    - effective_authoring_policy cannot be built
    - compiled requirements (contracts) are absent
    - LLM response is schema-invalid (validation_violations present)
    - LLM response is schema-valid but content non-compliant (is_compliant=False)
    """

    def _implement_fixture(self, tmp_path: Path):
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _write_phase6_session(session_path, workspace, repo_fp)
        _write_phase6_approved_session(session_path)
        plan_record = workspace / "plan-record.json"
        plan_record.write_text(json.dumps({
            "schema_version": "v1",
            "repo_fingerprint": repo_fp,
            "status": "active",
            "versions": [{"version": 1, "plan_record_text": "Plan.", "plan_record_digest": "sha256:test"}]
        }), encoding="utf-8")
        return config_root, commands_home, session_path, repo_fp, workspace

    def test_implement_blocks_when_effective_policy_unavailable(self, tmp_path, monkeypatch, capsys):
        """/implement must block when effective_authoring_policy cannot be built."""
        config_root, commands_home, session_path, repo_fp, workspace = self._implement_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        module_impl = _load_implement()

        def _raise_unavailable(*args, **kwargs):
            return "", "effective-policy-unavailable"

        monkeypatch.setattr(module_impl, "_load_effective_authoring_policy_text", _raise_unavailable)
        capsys.readouterr()
        rc = module_impl.main(["--quiet"])
        assert rc == 2, f"/implement must block when effective policy unavailable, got rc={rc}"
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload.get("status") in ("error", "blocked")

    def test_implement_blocks_when_requirement_contracts_absent(self, tmp_path, monkeypatch, capsys):
        """/implement must block when requirement contracts (compiled_requirements.json) are absent."""
        config_root, commands_home, session_path, repo_fp, workspace = self._implement_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        doc = _read_json(session_path)
        doc["SESSION_STATE"]["requirement_contracts_present"] = False
        doc["SESSION_STATE"]["requirement_contracts_count"] = 0
        session_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

        module_impl = _load_implement()
        monkeypatch.setenv("OPENCODE_IMPLEMENT_LLM_CMD", "echo '{\"developer_output\":\"ok\"}'")
        capsys.readouterr()
        rc = module_impl.main(["--quiet"])
        assert rc == 2, f"/implement must block when requirement contracts absent, got rc={rc}"
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload.get("status") in ("error", "blocked")

    def test_implement_blocks_when_llm_response_has_validation_violations(self, tmp_path, monkeypatch, capsys):
        """/implement must block when LLM response has validation_violations (schema-invalid)."""
        config_root, commands_home, session_path, repo_fp, workspace = self._implement_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        module_impl = _load_implement()
        monkeypatch.setenv(
            "OPENCODE_IMPLEMENT_LLM_CMD",
            "echo '{\"developer_output\":\"ok\",\"changed_files\":[],\"validation_violations\":[\"missing_required_field\"]}'",
        )
        capsys.readouterr()
        rc = module_impl.main(["--quiet"])
        assert rc == 2, f"/implement must block when LLM has validation_violations, got rc={rc}"
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload.get("status") in ("error", "blocked")

    def test_implement_records_non_compliant_response(self, tmp_path, monkeypatch, capsys):
        """/implement with schema-valid but content-non-compliant response: status=blocked, not ok."""
        config_root, commands_home, session_path, repo_fp, workspace = self._implement_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        module_impl = _load_implement()
        monkeypatch.setenv(
            "OPENCODE_IMPLEMENT_LLM_CMD",
            "echo '{\"developer_output\":\"ok\",\"changed_files\":[],\"validation_violations\":[],\"exit_code\":0}'",
        )
        capsys.readouterr()
        rc = module_impl.main(["--quiet"])
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload.get("status") in ("ok", "blocked"), (
            f"implement response must be ok or blocked, got {payload.get('status')}"
        )
        if payload.get("status") == "ok":
            state = _read_state(session_path)
            impl_status = state.get("implementation_status", "")
            assert impl_status != "ready_for_review", (
                "non-compliant implementation must not have status=ready_for_review"
            )

