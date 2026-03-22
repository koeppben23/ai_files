"""
test_governance_flow_truth.py — Flow truth: canonical user chain /ticket → /plan → /continue → /review-decision → /implement.

CI-blocking main merge guard: every test here must pass.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tests.conftest_governance import (
    _load_implement,
    _load_phase5,
    _load_review_decision,
    _load_session_reader,
    _load_module,
    _read_json,
    _read_state,
    _set_env,
    _write_e2e_fixture,
    _write_phase6_approved_session,
    _write_phase6_session,
)


# ── A. /TICKET ─────────────────────────────────────────────────────────────

@pytest.mark.e2e_governance
class TestE2ETicketRail:
    """Truth tests for /ticket as the canonical workflow start.

    /ticket must:
    1. Record Ticket and Task text in session state.
    2. Generate valid TicketRecordDigest and TaskRecordDigest (SHA256).
    3. Advance Phase from 4 to 5.
    4. Set active_gate to Plan Record Preparation Gate.
    5. Persist exactly one next_action: /continue.
    6. Response includes all required fields.
    """

    def test_ticket_persists_ticket_and_task_text(self, tmp_path, monkeypatch, capsys):
        """Ticket text and Task text must be persisted verbatim in session state."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        state = _read_state(session_path)
        state["Phase"] = "4"
        state["active_gate"] = "Ticket Input Gate"
        state.pop("Ticket", None)
        state.pop("Task", None)
        state.pop("TicketRecordDigest", None)
        state.pop("TaskRecordDigest", None)
        session_path.write_text(json.dumps({"SESSION_STATE": state}, indent=2) + "\n", encoding="utf-8")

        ticket_text = "Implement rate-limiting middleware for the REST API"
        task_text = "Add rate-limiting to all public API endpoints using Redis"

        module = _load_module("phase4_intake_persist", "phase4_intake_persist.py")
        capsys.readouterr()
        rc = module.main([
            f"--ticket-text={ticket_text}",
            f"--task-text={task_text}",
            "--quiet",
        ])
        assert rc == 0, "/ticket must succeed"

        persisted = _read_state(session_path)
        assert persisted.get("Ticket") == ticket_text, (
            f"Ticket text must be persisted verbatim, got {persisted.get('Ticket')!r}"
        )
        assert persisted.get("Task") == task_text, (
            f"Task text must be persisted verbatim, got {persisted.get('Task')!r}"
        )

    def test_ticket_generates_valid_digests(self, tmp_path, monkeypatch, capsys):
        """TicketRecordDigest and TaskRecordDigest must be valid SHA256 (64 hex chars)."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        state = _read_state(session_path)
        state["Phase"] = "4"
        state["active_gate"] = "Ticket Input Gate"
        state.pop("Ticket", None)
        state.pop("Task", None)
        state.pop("TicketRecordDigest", None)
        state.pop("TaskRecordDigest", None)
        session_path.write_text(json.dumps({"SESSION_STATE": state}, indent=2) + "\n", encoding="utf-8")

        module = _load_module("phase4_intake_persist", "phase4_intake_persist.py")
        capsys.readouterr()
        module.main(["--ticket-text=Build auth", "--task-text=Add JWT", "--quiet"])

        state = _read_state(session_path)
        ticket_digest = str(state.get("TicketRecordDigest", ""))
        task_digest = str(state.get("TaskRecordDigest", ""))
        for name, digest in [("TicketRecordDigest", ticket_digest), ("TaskRecordDigest", task_digest)]:
            assert len(digest) == 64 and all(c in "0123456789abcdef" for c in digest), (
                f"{name} must be SHA256 hex (64 chars), got {digest!r}"
            )

    def test_ticket_advances_phase_to_5(self, tmp_path, monkeypatch, capsys):
        """/ticket must advance Phase from 4 to 5-ArchitectureReview."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        state = _read_state(session_path)
        state["Phase"] = "4"
        state["active_gate"] = "Ticket Input Gate"
        state.pop("Ticket", None)
        state.pop("Task", None)
        state.pop("TicketRecordDigest", None)
        state.pop("TaskRecordDigest", None)
        session_path.write_text(json.dumps({"SESSION_STATE": state}, indent=2) + "\n", encoding="utf-8")

        module = _load_module("phase4_intake_persist", "phase4_intake_persist.py")
        capsys.readouterr()
        module.main(["--ticket-text=Build auth", "--task-text=Add JWT", "--quiet"])

        state = _read_state(session_path)
        assert str(state.get("Phase", "")).startswith("5"), (
            f"Phase after /ticket must start with 5, got Phase={state.get('Phase')!r}"
        )
        assert state.get("active_gate") != "Ticket Input Gate", (
            "active_gate must NOT be Ticket Input Gate after /ticket"
        )

    def test_ticket_response_has_required_fields(self, tmp_path, monkeypatch, capsys):
        """/ticket response must include status, phase_after, next_action."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        state = _read_state(session_path)
        state["Phase"] = "4"
        state["active_gate"] = "Ticket Input Gate"
        state.pop("Ticket", None)
        state.pop("Task", None)
        session_path.write_text(json.dumps({"SESSION_STATE": state}, indent=2) + "\n", encoding="utf-8")

        module = _load_module("phase4_intake_persist", "phase4_intake_persist.py")
        capsys.readouterr()
        module.main(["--ticket-text=Build auth", "--task-text=Add JWT", "--quiet"])
        payload = json.loads(capsys.readouterr().out.strip())

        for field in ("status", "phase_after", "next_action"):
            assert field in payload, f"/ticket response must include {field!r} field"
        assert payload["status"] == "ok"
        assert "continue" in payload["next_action"].lower()

        state_after = json.loads(session_path.read_text(encoding="utf-8"))
        assert "TicketRecordDigest" in state_after.get("SESSION_STATE", {}), \
            "TicketRecordDigest must be persisted to session state"
        assert "TaskRecordDigest" in state_after.get("SESSION_STATE", {}), \
            "TaskRecordDigest must be persisted to session state"
        assert len(state_after["SESSION_STATE"]["TicketRecordDigest"]) == 64
        assert len(state_after["SESSION_STATE"]["TaskRecordDigest"]) == 64

    def test_ticket_blocks_without_ticket_text(self, tmp_path, monkeypatch, capsys):
        """/ticket must block when ticket text is empty."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        state = _read_state(session_path)
        state["Phase"] = "4"
        state["active_gate"] = "Ticket Input Gate"
        session_path.write_text(json.dumps({"SESSION_STATE": state}, indent=2) + "\n", encoding="utf-8")

        module = _load_module("phase4_intake_persist", "phase4_intake_persist.py")
        capsys.readouterr()
        rc = module.main(["--ticket-text=", "--task-text=", "--quiet"])
        assert rc != 0, "/ticket must fail without ticket text"
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload.get("status") in ("error", "blocked")


# ── B. /PLAN ───────────────────────────────────────────────────────────────

@pytest.mark.e2e_governance
class TestE2ECommandChains:
    """Test /plan with explicit plan text through the governance routing chain."""

    def test_plan_explicit_text_persists_and_routes(self, tmp_path, monkeypatch, capsys):
        """--plan-text produces plan-record.json and returns ok status."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        module = _load_phase5()
        rc = module.main(["--plan-text", "Architecture plan: add JWT /auth/login endpoint.", "--quiet"])
        assert rc == 0, f"/plan returned {rc}"

        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["status"] == "ok"
        assert payload["reason"] == "phase5-plan-record-persisted"
        assert payload.get("self_review_iterations_met") is True
        assert payload.get("phase5_completed") is True

    def test_plan_record_structure_after_persist(self, tmp_path, monkeypatch, capsys):
        """plan-record.json must have correct schema: schema_version, repo_fingerprint, status, versions."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        module = _load_phase5()
        module.main(["--plan-text", "Architecture plan v1.", "--quiet"])

        plan_record = _read_json(workspace / "plan-record.json")
        assert plan_record["schema_version"]
        assert plan_record["repo_fingerprint"] == repo_fp
        assert plan_record["status"] in ("active", "finalized")
        v = plan_record["versions"][0]
        assert v["version"] == 1
        assert v["plan_record_text"]
        assert v["plan_record_digest"].startswith("sha256:")

    def test_session_state_updated_after_plan(self, tmp_path, monkeypatch, capsys):
        """After /plan, session state must have Phase 5 completion markers and plan record fields."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        module = _load_phase5()
        module.main(["--plan-text", "Architecture plan v1.", "--quiet"])

        state = _read_state(session_path)
        assert state.get("phase5_completed") is True
        assert state.get("PlanRecordVersions", 0) >= 1
        assert state.get("requirement_contracts_present") is True
        assert state.get("PlanRecordStatus") == "active"

    def test_requirements_structure(self, tmp_path, monkeypatch, capsys):
        """compiled_requirements.json must have schema, generated_at, and requirement entries."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        module = _load_phase5()
        module.main(["--plan-text", "Architecture plan v1.", "--quiet"])

        contracts = _read_json(workspace / ".governance" / "contracts" / "compiled_requirements.json")
        assert contracts["schema"]
        assert contracts["generated_at"]
        req = contracts["requirements"][0]
        assert req["id"].startswith("R-PLAN-")
        assert req["title"]
        assert req["criticality"]

    def test_plan_text_from_file_persists(self, tmp_path, monkeypatch, capsys):
        """--plan-file reads plan text from a file and persists it."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        plan_file = tmp_path / "plan.md"
        plan_file.write_text("Plan from file input.", encoding="utf-8")

        module = _load_phase5()
        rc = module.main(["--plan-file", str(plan_file), "--quiet"])
        assert rc == 0

        plan_record = _read_json(workspace / "plan-record.json")
        assert "Plan from file input" in plan_record["versions"][0]["plan_record_text"]

    def test_events_jsonl_records_phase5_event(self, tmp_path, monkeypatch, capsys):
        """events.jsonl must contain a phase5-plan-record-persisted event."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        module = _load_phase5()
        module.main(["--plan-text", "Plan for test.", "--quiet"])

        events_file = workspace / "events.jsonl"
        assert events_file.exists()
        events = [
            json.loads(l)
            for l in events_file.read_text(encoding="utf-8").splitlines()
            if l.strip()
        ]
        event_types = {e.get("event") for e in events}
        assert "phase5-plan-record-persisted" in event_types


# ── C. /CONTINUE ──────────────────────────────────────────────────────────

@pytest.mark.e2e_governance
class TestE2ESessionReader:
    """session_reader --materialize traverses Phase 5 sub-gates toward Phase 6."""

    def test_materialize_does_not_crash_from_phase5(self, tmp_path, monkeypatch):
        """--materialize must not raise on a Phase 5 session."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        module = _load_session_reader()
        rc = module.main(["--commands-home", str(commands_home), "--materialize"])
        assert rc in (0, 1)

    def test_readonly_shows_phase5_state(self, tmp_path, monkeypatch):
        """Without --materialize, session_reader must return the Phase 5 state."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        module = _load_session_reader()
        rc = module.main(["--commands-home", str(commands_home)])

        state = _read_state(session_path)
        assert state.get("Phase") is not None
        assert state.get("Phase") == "5-ArchitectureReview"
        assert rc in (0, 1)


# ── D. /REVIEW-DECISION ───────────────────────────────────────────────────

@pytest.mark.e2e_governance
class TestE2EReviewDecision:
    """Test /review-decision: approve, changes_requested, reject transitions.

    Phase 6 Evidence Presentation Gate requires a valid review package receipt.
    Tests use a properly computed digest to satisfy the receipt validation.
    """

    def _setup_and_apply(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        decision: str,
        capsys: pytest.CaptureFixture[str],
    ) -> dict:
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)

        module = _load_review_decision()
        rc = module.main(["--decision", decision, "--quiet"])
        return {
            "rc": rc,
            "payload": json.loads(capsys.readouterr().out.strip()),
            "session_path": session_path,
            "workspace": workspace,
        }

    def test_approve_transitions_to_workflow_complete(self, tmp_path, monkeypatch, capsys):
        """approve must set workflow_complete, active_gate=Workflow Complete, and next_action_command=/implement."""
        result = self._setup_and_apply(tmp_path, monkeypatch, "approve", capsys)
        assert result["rc"] == 0, f"Expected rc=0, got {result['rc']}: {result['payload']}"

        state = _read_state(result["session_path"])
        assert state.get("workflow_complete") is True
        assert state.get("WorkflowComplete") is True
        assert state.get("active_gate") == "Workflow Complete"
        assert state.get("governance_status") == "complete"
        assert state.get("implementation_status") == "authorized"
        assert state.get("implementation_authorized") is True
        assert state.get("next_action_command") == "/implement"

    def test_approve_next_action_ux(self, tmp_path, monkeypatch, capsys):
        """approve response must have a meaningful next_action hint."""
        result = self._setup_and_apply(tmp_path, monkeypatch, "approve", capsys)
        assert result["rc"] == 0
        assert result["payload"].get("status") == "ok"
        assert result["payload"].get("decision") == "approve"
        assert "next_action" in result["payload"]
        assert "/implement" in result["payload"]["next_action"]

    def test_changes_requested_transitions_to_rework_clarification(self, tmp_path, monkeypatch, capsys):
        """changes_requested must set active_gate=Rework Clarification Gate and clear workflow_complete."""
        result = self._setup_and_apply(tmp_path, monkeypatch, "changes_requested", capsys)
        assert result["rc"] == 0, f"Expected rc=0, got {result['rc']}: {result['payload']}"

        state = _read_state(result["session_path"])
        assert state.get("active_gate") == "Rework Clarification Gate"
        assert state.get("workflow_complete") in (None, False)
        assert state.get("Phase") == "6-PostFlight"
        assert state.get("Next") == "6"
        assert state.get("phase6_state") == "phase6_changes_requested"

    def test_changes_requested_next_action_ux(self, tmp_path, monkeypatch, capsys):
        """changes_requested response must have a meaningful next_action hint."""
        result = self._setup_and_apply(tmp_path, monkeypatch, "changes_requested", capsys)
        assert result["rc"] == 0
        assert result["payload"].get("status") == "ok"
        assert result["payload"].get("decision") == "changes_requested"
        assert "next_action" in result["payload"]

    def test_reject_transitions_to_phase4_ticket_input_gate(self, tmp_path, monkeypatch, capsys):
        """reject must return to Phase 4 with active_gate=Ticket Input Gate."""
        result = self._setup_and_apply(tmp_path, monkeypatch, "reject", capsys)
        assert result["rc"] == 0, f"Expected rc=0, got {result['rc']}: {result['payload']}"

        state = _read_state(result["session_path"])
        assert state.get("Phase") == "4"
        assert state.get("active_gate") == "Ticket Input Gate"
        assert "ticket" in state.get("next_gate_condition", "").lower()

    def test_reject_next_action_ux(self, tmp_path, monkeypatch, capsys):
        """reject response must have a meaningful next_action hint."""
        result = self._setup_and_apply(tmp_path, monkeypatch, "reject", capsys)
        assert result["rc"] == 0
        assert result["payload"].get("status") == "ok"
        assert result["payload"].get("decision") == "reject"
        assert "next_action" in result["payload"]
        assert "ticket" in result["payload"]["next_action"].lower()

    def test_review_decision_blocks_when_not_phase6(self, tmp_path, monkeypatch, capsys):
        """/review-decision must block when not in Phase 6."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        module = _load_review_decision()
        rc = module.main(["--decision", "approve", "--quiet"])
        assert rc == 2
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload.get("status") == "error"
        assert "Phase 6" in payload.get("message", "")

    def test_review_decision_blocks_when_not_evidence_presentation_gate(self, tmp_path, monkeypatch, capsys):
        """/review-decision must block when not at Evidence Presentation Gate."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)
        doc = _read_json(session_path)
        doc["SESSION_STATE"]["active_gate"] = "Some Other Gate"
        session_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

        module = _load_review_decision()
        rc = module.main(["--decision", "approve", "--quiet"])
        assert rc == 2
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload.get("status") == "error"
        assert "Evidence Presentation Gate" in payload.get("message", "")

    def test_review_decision_blocks_invalid_decision(self, tmp_path, monkeypatch, capsys):
        """Invalid decision values must be rejected."""
        result = self._setup_and_apply(tmp_path, monkeypatch, "maybe", capsys)
        assert result["rc"] == 2
        assert result["payload"].get("status") == "error"

    def test_review_decision_audit_event(self, tmp_path, monkeypatch, capsys):
        """events.jsonl must contain a REVIEW_DECISION audit event."""
        result = self._setup_and_apply(tmp_path, monkeypatch, "approve", capsys)
        assert result["rc"] == 0

        events_file = result["workspace"] / "events.jsonl"
        assert events_file.exists()
        events = [
            json.loads(l)
            for l in events_file.read_text(encoding="utf-8").splitlines()
            if l.strip()
        ]
        event_types = {e.get("event") for e in events}
        assert "REVIEW_DECISION" in event_types


# ── E. /IMPLEMENT ─────────────────────────────────────────────────────────

@pytest.mark.e2e_governance
class TestE2EImplement:
    """Test /implement: approve path, effective policy blocking."""

    def test_implement_blocks_when_no_approve_decision(self, tmp_path, monkeypatch, capsys):
        """/implement must block when workflow_complete is not set."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)
        doc = _read_json(session_path)
        doc["SESSION_STATE"]["active_gate"] = "Workflow Complete"
        session_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

        module = _load_implement()
        rc = module.main(["--quiet"])
        assert rc == 2
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload.get("status") == "error"
        assert "approved" in payload.get("message", "").lower() or "decision" in payload.get("message", "").lower()

    def test_implement_blocks_at_rework_clarification_gate(self, tmp_path, monkeypatch, capsys):
        """/implement must block when active_gate=Rework Clarification Gate."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)
        doc = _read_json(session_path)
        doc["SESSION_STATE"]["active_gate"] = "Rework Clarification Gate"
        doc["SESSION_STATE"]["workflow_complete"] = True
        doc["SESSION_STATE"]["UserReviewDecision"] = {"decision": "changes_requested"}
        session_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

        module = _load_implement()
        rc = module.main(["--quiet"])
        assert rc == 2
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload.get("status") == "error"
        assert "rework" in payload.get("message", "").lower() or "clarification" in payload.get("message", "").lower()

    def test_implement_blocks_at_ticket_input_gate(self, tmp_path, monkeypatch, capsys):
        """/implement must block when active_gate=Ticket Input Gate."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)
        doc = _read_json(session_path)
        doc["SESSION_STATE"]["active_gate"] = "Ticket Input Gate"
        doc["SESSION_STATE"]["workflow_complete"] = True
        session_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

        module = _load_implement()
        rc = module.main(["--quiet"])
        assert rc == 2
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload.get("status") == "error"
        assert "ticket" in payload.get("message", "").lower() or "reject" in payload.get("message", "").lower()

    def test_implement_blocks_when_plan_record_absent(self, tmp_path, monkeypatch, capsys):
        """/implement must block when no plan-record.json exists."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)
        _write_phase6_approved_session(session_path)
        doc = _read_json(session_path)
        doc["SESSION_STATE"].pop("PlanRecordVersions", None)
        session_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        assert not (workspace / "plan-record.json").exists()

        module = _load_implement()
        rc = module.main(["--quiet"])
        assert rc == 2
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload.get("status") in ("error", "blocked")
        assert "plan" in payload.get("message", "").lower()

    def test_implement_blocks_when_contracts_absent(self, tmp_path, monkeypatch, capsys):
        """/implement must block when requirement contracts are absent."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)
        _write_phase6_approved_session(session_path)
        plan_record = workspace / "plan-record.json"
        plan_record.write_text(json.dumps({
            "schema_version": "v1", "repo_fingerprint": repo_fp,
            "status": "active",
            "versions": [{"version": 1, "plan_record_text": "Plan.", "plan_record_digest": "sha256:test"}]
        }), encoding="utf-8")
        doc = _read_json(session_path)
        doc["SESSION_STATE"]["requirement_contracts_present"] = False
        doc["SESSION_STATE"]["requirement_contracts_count"] = 0
        session_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

        module = _load_implement()
        rc = module.main(["--quiet"])
        assert rc == 2
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload.get("status") == "error"
        assert "contract" in payload.get("message", "").lower()

    def test_implement_blocks_when_not_phase6(self, tmp_path, monkeypatch, capsys):
        """/implement must block when not in Phase 6."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        module = _load_implement()
        rc = module.main(["--quiet"])
        assert rc == 2
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload.get("status") == "error"
        assert "Phase 6" in payload.get("message", "")

    def test_implement_blocks_when_effective_policy_unavailable(self, tmp_path, monkeypatch, capsys):
        """Without effective policy, /implement must block with BLOCKED-EFFECTIVE-POLICY-UNAVAILABLE."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)
        _write_phase6_approved_session(session_path)
        plan_record = workspace / "plan-record.json"
        plan_record.write_text(json.dumps({
            "schema_version": "v1", "repo_fingerprint": repo_fp,
            "status": "active",
            "versions": [{"version": 1, "plan_record_text": "Plan.", "plan_record_digest": "sha256:test"}]
        }), encoding="utf-8")
        monkeypatch.setenv("OPENCODE_IMPLEMENT_LLM_CMD", "echo '{\"developer_output\":\"ok\"}'")

        module = _load_implement()

        def _raise_unavailable(*args, **kwargs):
            return "", "effective-policy-unavailable"

        monkeypatch.setattr(module, "_load_effective_authoring_policy_text", _raise_unavailable)
        rc = module.main(["--quiet"])
        assert rc == 2
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload.get("status") in ("error", "blocked")

    def test_implement_happy_path_with_valid_approval_and_artifacts(self, tmp_path, monkeypatch, capsys):
        """With Workflow Complete and all prerequisites: /implement must return status=ok
        with implementation_started=True, valid LLM response, and satisfied validation."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)
        _write_phase6_approved_session(session_path)
        plan_record = workspace / "plan-record.json"
        plan_record.write_text(json.dumps({
            "schema_version": "v1",
            "repo_fingerprint": repo_fp,
            "status": "active",
            "versions": [{
                "version": 1,
                "plan_record_text": "Plan: implement auth.",
                "plan_record_digest": "sha256:abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
            }]
        }), encoding="utf-8")

        module = _load_implement()

        def _mock_start_impl(*, session_path, events_path, actor, note):
            return {
                "status": "ok",
                "phase": "6-PostFlight",
                "next": "6",
                "active_gate": "Implementation Started",
                "next_gate_condition": "Implementation started.",
                "implementation_started": True,
                "implementation_llm_response_valid": True,
                "implementation_llm_validation_violations": [],
                "implementation_validation": {
                    "executor_invoked": True,
                    "executor_succeeded": True,
                    "changed_files": ["src/auth/login.py"],
                    "domain_changed_files": ["src/auth/login.py"],
                    "is_compliant": True,
                    "reason_codes": [],
                },
            }

        monkeypatch.setattr(module, "start_implementation", _mock_start_impl)
        rc = module.main(["--quiet"])
        payload = json.loads(capsys.readouterr().out.strip())
        assert rc == 0, f"/implement happy path should succeed, got rc={rc}: {payload}"
        assert payload.get("status") == "ok", (
            f"Expected status=ok with valid approval+files+response+checks, got {payload}"
        )
        assert payload.get("implementation_started") is True
        assert payload.get("implementation_llm_response_valid") is True
        assert payload.get("implementation_llm_validation_violations") == []
        val = payload.get("implementation_validation", {})
        assert val.get("executor_invoked") is True
        assert val.get("executor_succeeded") is True
        assert val.get("is_compliant") is True
        assert len(val.get("changed_files", [])) > 0, "Must have changed files"


# ── F. REWORK ROUTING ─────────────────────────────────────────────────────

@pytest.mark.e2e_governance
class TestE2EReworkRouting:
    """Test rework routing: changes_requested → Rework Clarification Gate → /plan loop."""

    def test_rework_clarification_gate_requires_rail_to_exit(self, tmp_path, monkeypatch, capsys):
        """After changes_requested, /implement and /review-decision must block until a clarification rail runs."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)

        module_rd = _load_review_decision()
        rc = module_rd.main(["--decision", "changes_requested", "--quiet"])
        assert rc == 0

        state = _read_state(session_path)
        assert state.get("active_gate") == "Rework Clarification Gate"
        assert state.get("phase6_state") == "phase6_changes_requested"
        assert state.get("implementation_review_complete") is False

    def test_rework_exits_via_plan_clarification(self, tmp_path, monkeypatch, capsys):
        """After /plan clarification on Rework Clarification Gate, implementation_review_complete resets."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)

        module_rd = _load_review_decision()
        module_rd.main(["--decision", "changes_requested", "--quiet"])

        doc = _read_json(session_path)
        doc["SESSION_STATE"]["active_gate"] = "Rework Clarification Gate"
        doc["SESSION_STATE"]["Phase"] = "6-PostFlight"
        doc["SESSION_STATE"]["TicketRecordDigest"] = "sha256:abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
        doc["SESSION_STATE"]["TaskRecordDigest"] = "sha256:fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210"
        session_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

        module_plan = _load_phase5()
        rc = module_plan.main(["--plan-text", "Clarified plan: JWT with RS256.", "--quiet"])
        assert rc == 0

        state = _read_state(session_path)
        assert state.get("implementation_review_complete") is False or state.get("phase6_state") in (
            "phase6_changes_requested", "phase6_in_progress", None
        )

    def test_rework_loop_resets_review_iterations(self, tmp_path, monkeypatch, capsys):
        """After changes_requested, the review loop iterations must reset to 0."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)
        doc = _read_json(session_path)
        doc["SESSION_STATE"]["ImplementationReview"] = {
            "implementation_review_complete": True,
            "completion_status": "phase6-completed",
            "iteration": 3,
            "min_self_review_iterations": 1,
            "revision_delta": "none",
        }
        session_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

        module = _load_review_decision()
        rc = module.main(["--decision", "changes_requested", "--quiet"])
        assert rc == 0

        state = _read_state(session_path)
        review_block = state.get("ImplementationReview", {})
        assert review_block.get("iteration") == 0
        assert review_block.get("revision_delta") == "changed"
        assert review_block.get("implementation_review_complete") is False

    def test_rework_scope_change_routes_to_ticket(self, tmp_path, monkeypatch, capsys):
        """On Rework Clarification Gate, /ticket with scope-change text must route back to Phase 4."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)

        module_rd = _load_review_decision()
        module_rd.main(["--decision", "changes_requested", "--quiet"])

        state = _read_state(session_path)
        assert state.get("active_gate") == "Rework Clarification Gate"
        assert state.get("phase6_state") == "phase6_changes_requested"

        state["Phase"] = "6-PostFlight"
        state["active_gate"] = "Rework Clarification Gate"
        state["Next"] = "6"
        state["PersistenceCommitted"] = True
        state["WorkspaceReadyGateCommitted"] = True
        state["WorkspaceArtifactsCommitted"] = True
        state["PointerVerified"] = True
        state["RulebookLoadEvidence"] = {
            "core": {"status": "loaded", "path": "${PROFILES_HOME}/rules.fallback-minimum.md"},
            "profile": {"status": "loaded", "path": "${PROFILES_HOME}/rules.fallback-minimum.md"},
        }
        state["Gates"] = {
            "P5-Architecture": "approved",
            "P5.3-TestQuality": "pass",
            "P5.5-TechnicalDebt": "not-applicable",
            "P5.6-RollbackSafety": "not-applicable",
        }
        session_path.write_text(json.dumps({"SESSION_STATE": state}, indent=2) + "\n", encoding="utf-8")

        module_ticket = _load_module("phase4_intake_persist", "phase4_intake_persist.py")
        capsys.readouterr()
        rc = module_ticket.main([
            "--ticket-text=Scope change: add requirement for rate limiting to authentication",
            "--task-text=Add rate limiting to the JWT auth endpoint",
            "--quiet",
        ])
        payload = json.loads(capsys.readouterr().out.strip())
        assert rc == 0, f"/ticket scope_change should succeed, got rc={rc}: {payload}"
        assert payload.get("status") == "ok"

        state = _read_state(session_path)
        assert state.get("Phase") == "5-ArchitectureReview", (
            f"After scope_change rework via /ticket, Phase must be 5-ArchitectureReview "
            f"(scope change re-triggers Phase 5 review), got {state.get('Phase')}"
        )
        assert state.get("active_gate") == "Plan Record Preparation Gate", (
            f"After scope_change rework, must be at Plan Record Preparation Gate, got {state.get('active_gate')}"
        )

    def test_rework_continue_does_not_consume_without_ticket_or_plan(self, tmp_path, monkeypatch, capsys):
        """/continue on Rework Clarification Gate stays in Phase 6 but does NOT consume clarification.
        Only /ticket or /plan consume the rework clarification state."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)

        module_rd = _load_review_decision()
        module_rd.main(["--decision", "changes_requested", "--quiet"])

        state = _read_state(session_path)
        assert state.get("active_gate") == "Rework Clarification Gate"

        state["Phase"] = "6-PostFlight"
        state["Next"] = "6"
        state["PersistenceCommitted"] = True
        state["WorkspaceReadyGateCommitted"] = True
        state["WorkspaceArtifactsCommitted"] = True
        state["PointerVerified"] = True
        state["RulebookLoadEvidence"] = {
            "core": {"status": "loaded", "path": "${PROFILES_HOME}/rules.fallback-minimum.md"},
            "profile": {"status": "loaded", "path": "${PROFILES_HOME}/rules.fallback-minimum.md"},
        }
        state["Gates"] = {
            "P5-Architecture": "approved",
            "P5.3-TestQuality": "pass",
            "P5.5-TechnicalDebt": "not-applicable",
            "P5.6-RollbackSafety": "not-applicable",
        }
        session_path.write_text(json.dumps({"SESSION_STATE": state}, indent=2) + "\n", encoding="utf-8")

        session_reader = _load_session_reader()
        capsys.readouterr()
        rc = session_reader.main(["--materialize", f"--commands-home={commands_home}"])
        assert rc == 0, f"/continue on Rework Clarification Gate should succeed, got rc={rc}"

        state = _read_state(session_path)
        phase = str(state.get("Phase") or "")
        assert phase.startswith("6"), (
            f"/continue must stay in Phase 6 at Rework Clarification Gate, got Phase={phase}"
        )
        assert state.get("active_gate") == "Rework Clarification Gate", (
            f"Gate must stay Rework Clarification Gate after /continue, got {state.get('active_gate')}"
        )
        assert state.get("rework_clarification_consumed") is not True, (
            "/continue must NOT consume rework clarification (only /ticket or /plan do)"
        )

    def test_rework_clarification_consumed_via_plan(self, tmp_path, monkeypatch, capsys):
        """/plan on Rework Clarification Gate must consume the clarification state."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)

        module_rd = _load_review_decision()
        module_rd.main(["--decision", "changes_requested", "--quiet"])

        state = _read_state(session_path)
        assert state.get("active_gate") == "Rework Clarification Gate"

        state["Phase"] = "6-PostFlight"
        state["Next"] = "6"
        state["PersistenceCommitted"] = True
        state["WorkspaceReadyGateCommitted"] = True
        state["WorkspaceArtifactsCommitted"] = True
        state["PointerVerified"] = True
        state["RulebookLoadEvidence"] = {
            "core": {"status": "loaded", "path": "${PROFILES_HOME}/rules.fallback-minimum.md"},
            "profile": {"status": "loaded", "path": "${PROFILES_HOME}/rules.fallback-minimum.md"},
        }
        state["Gates"] = {
            "P5-Architecture": "approved",
            "P5.3-TestQuality": "pass",
            "P5.5-TechnicalDebt": "not-applicable",
            "P5.6-RollbackSafety": "not-applicable",
        }
        state["TicketRecordDigest"] = "sha256:abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
        state["TaskRecordDigest"] = "sha256:fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210"
        session_path.write_text(json.dumps({"SESSION_STATE": state}, indent=2) + "\n", encoding="utf-8")

        module_plan = _load_phase5()
        capsys.readouterr()
        rc = module_plan.main(["--plan-text", "Plan clarification: implement with RS256.", "--quiet"])
        assert rc == 0, f"/plan on Rework Clarification Gate must succeed, got rc={rc}"

        state = _read_state(session_path)
        assert state.get("rework_clarification_consumed") is True, (
            "/plan must consume rework clarification"
        )
        assert state.get("rework_clarification_consumed_by") == "plan", (
            "rework_clarification_consumed_by must be 'plan'"
        )

    def test_rework_clarification_only_routes_to_continue(self, tmp_path, monkeypatch, capsys):
        """"clarification_only" at Rework Clarification Gate must derive next_action=/continue.

        Rework Clarification Gate with clarification-only text must:
        1. Derive /continue (clarification does not consume rework state).
        2. Stay in Rework Clarification Gate.
        3. NOT advance to Evidence Presentation Gate without explicit /plan or /ticket.
        """
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)

        module_rd = _load_review_decision()
        module_rd.main(["--decision", "changes_requested", "--quiet"])

        state = _read_state(session_path)
        assert state.get("active_gate") == "Rework Clarification Gate"
        assert state.get("phase6_state") == "phase6_changes_requested"

        state["Phase"] = "6-PostFlight"
        state["Next"] = "6"
        state["PersistenceCommitted"] = True
        state["WorkspaceReadyGateCommitted"] = True
        state["WorkspaceArtifactsCommitted"] = True
        state["PointerVerified"] = True
        state["RulebookLoadEvidence"] = {
            "core": {"status": "loaded", "path": "${PROFILES_HOME}/rules.fallback-minimum.md"},
            "profile": {"status": "loaded", "path": "${PROFILES_HOME}/rules.fallback-minimum.md"},
        }
        state["Gates"] = {
            "P5-Architecture": "approved",
            "P5.3-TestQuality": "pass",
            "P5.5-TechnicalDebt": "not-applicable",
            "P5.6-RollbackSafety": "not-applicable",
        }
        state["rework_clarification_input"] = "Bitte das rationale begruenden warum diese entscheidung getroffen wurde"
        session_path.write_text(json.dumps({"SESSION_STATE": state}, indent=2) + "\n", encoding="utf-8")

        session_reader = _load_session_reader()
        capsys.readouterr()
        rc = session_reader.main(["--materialize", f"--commands-home={commands_home}"])
        assert rc == 0, "/continue on Rework Clarification Gate must succeed"

        state = _read_state(session_path)
        assert state.get("active_gate") == "Rework Clarification Gate", (
            f"clarification_only must stay in Rework Clarification Gate, got {state.get('active_gate')!r}"
        )
        assert state.get("rework_clarification_consumed") is not True, (
            "clarification_only must NOT consume rework clarification state"
        )


# ── G. PHASE 6 REVIEW LOOP ────────────────────────────────────────────────

@pytest.mark.e2e_governance
class TestE2EPhase6ReviewLoop:
    """Test Phase 6 internal review loop: deterministic routing with and without LLM."""

    def test_phase6_review_loop_completes_at_iteration_1_with_stable_digest(self, tmp_path, monkeypatch, capsys):
        """/continue with stable digest (prev==curr) completes internal review at iteration 1."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)

        doc = _read_json(session_path)
        stable_digest = "sha256:" + hashlib.sha256(b"e2e:stable:digest").hexdigest()
        doc["SESSION_STATE"]["Phase"] = "6-PostFlight"
        doc["SESSION_STATE"]["Next"] = "6"
        doc["SESSION_STATE"]["active_gate"] = "Implementation Internal Review"
        doc["SESSION_STATE"]["PersistenceCommitted"] = True
        doc["SESSION_STATE"]["WorkspaceReadyGateCommitted"] = True
        doc["SESSION_STATE"]["WorkspaceArtifactsCommitted"] = True
        doc["SESSION_STATE"]["PointerVerified"] = True
        doc["SESSION_STATE"]["RulebookLoadEvidence"] = {
            "core": "deferred",
            "profile": "deferred",
            "templates": "deferred",
            "addons": {},
        }
        doc["SESSION_STATE"]["ImplementationReview"] = {
            "implementation_review_complete": False,
            "completion_status": "phase6-in-progress",
            "iteration": 0,
            "min_self_review_iterations": 1,
            "max_iterations": 1,
            "prev_impl_digest": stable_digest,
            "curr_impl_digest": stable_digest,
            "revision_delta": "none",
        }
        doc["SESSION_STATE"]["implementation_review_complete"] = False
        doc["SESSION_STATE"]["phase6_state"] = "phase6_in_progress"
        doc["SESSION_STATE"]["phase_transition_evidence"] = True
        doc["SESSION_STATE"]["Gates"] = {
            "P5-Architecture": "approved",
            "P5.3-TestQuality": "pass",
            "P5.5-TechnicalDebt": "not-applicable",
            "P5.6-RollbackSafety": "not-applicable",
        }
        session_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

        module = _load_session_reader()
        capsys.readouterr()
        rc = module.main(["--materialize", f"--commands-home={commands_home}"])
        assert rc == 0, f"/continue must succeed with stable digest, got rc={rc}"

        state = _read_state(session_path)
        assert state.get("implementation_review_complete") is True, (
            f"Review must complete when prev==curr digest, got implementation_review_complete={state.get('implementation_review_complete')}"
        )
        assert state.get("phase6_state") == "phase6_completed", (
            f"phase6_state must be phase6_completed, got {state.get('phase6_state')}"
        )
        rev = state.get("ImplementationReview", {})
        assert rev.get("iteration") == 1, (
            f"Must complete at iteration 1 with max_iterations=1, got iteration={rev.get('iteration')}"
        )
        assert rev.get("completion_status") == "phase6-completed", (
            f"completion_status must be phase6-completed, got {rev.get('completion_status')}"
        )

    def test_phase6_review_loop_runs_max_iterations_without_stable_digest(self, tmp_path, monkeypatch, capsys):
        """/continue without stable digest runs all 3 iterations (digest changes each time)."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)

        doc = _read_json(session_path)
        doc["SESSION_STATE"]["Phase"] = "6-PostFlight"
        doc["SESSION_STATE"]["Next"] = "6"
        doc["SESSION_STATE"]["active_gate"] = "Implementation Internal Review"
        doc["SESSION_STATE"]["PersistenceCommitted"] = True
        doc["SESSION_STATE"]["WorkspaceReadyGateCommitted"] = True
        doc["SESSION_STATE"]["WorkspaceArtifactsCommitted"] = True
        doc["SESSION_STATE"]["PointerVerified"] = True
        doc["SESSION_STATE"]["RulebookLoadEvidence"] = {
            "core": "deferred",
            "profile": "deferred",
            "templates": "deferred",
            "addons": {},
        }
        doc["SESSION_STATE"]["ImplementationReview"] = {
            "implementation_review_complete": False,
            "completion_status": "phase6-in-progress",
            "iteration": 0,
            "min_self_review_iterations": 1,
            "max_iterations": 3,
            "prev_impl_digest": "sha256:aaaa1111bbbb",
            "curr_impl_digest": "sha256:bbbb2222cccc",
            "revision_delta": "changed",
        }
        doc["SESSION_STATE"]["implementation_review_complete"] = False
        doc["SESSION_STATE"]["phase6_state"] = "phase6_in_progress"
        doc["SESSION_STATE"]["phase_transition_evidence"] = True
        doc["SESSION_STATE"]["Gates"] = {
            "P5-Architecture": "approved",
            "P5.3-TestQuality": "pass",
            "P5.5-TechnicalDebt": "not-applicable",
            "P5.6-RollbackSafety": "not-applicable",
        }
        session_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

        module = _load_session_reader()
        capsys.readouterr()
        rc = module.main(["--materialize", f"--commands-home={commands_home}"])
        assert rc == 0, f"/continue must succeed even without stable digest, got rc={rc}"

        state = _read_state(session_path)
        rev = state.get("ImplementationReview", {})
        assert rev.get("iteration") == 3, (
            f"Without stable digest, must run all 3 iterations, got iteration={rev.get('iteration')}"
        )
        assert rev.get("revision_delta") == "changed", (
            "Without stable digest, revision_delta must be 'changed'"
        )

    def test_phase6_review_complete_routes_to_evidence_presentation_gate(self, tmp_path, monkeypatch, capsys):
        """/continue after successful internal review routes to Evidence Presentation Gate."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)

        doc = _read_json(session_path)
        stable_digest = "sha256:" + hashlib.sha256(b"e2e:review:complete").hexdigest()
        doc["SESSION_STATE"]["Phase"] = "6-PostFlight"
        doc["SESSION_STATE"]["Next"] = "6"
        doc["SESSION_STATE"]["active_gate"] = "Implementation Internal Review"
        doc["SESSION_STATE"]["PersistenceCommitted"] = True
        doc["SESSION_STATE"]["WorkspaceReadyGateCommitted"] = True
        doc["SESSION_STATE"]["WorkspaceArtifactsCommitted"] = True
        doc["SESSION_STATE"]["PointerVerified"] = True
        doc["SESSION_STATE"]["RulebookLoadEvidence"] = {
            "core": "deferred",
            "profile": "deferred",
            "templates": "deferred",
            "addons": {},
        }
        doc["SESSION_STATE"]["ImplementationReview"] = {
            "implementation_review_complete": False,
            "completion_status": "phase6-in-progress",
            "iteration": 0,
            "min_self_review_iterations": 1,
            "max_iterations": 3,
            "prev_impl_digest": stable_digest,
            "curr_impl_digest": stable_digest,
            "revision_delta": "none",
        }
        doc["SESSION_STATE"]["implementation_review_complete"] = False
        doc["SESSION_STATE"]["phase6_state"] = "phase6_in_progress"
        doc["SESSION_STATE"]["phase_transition_evidence"] = True
        doc["SESSION_STATE"]["Gates"] = {
            "P5-Architecture": "approved",
            "P5.3-TestQuality": "pass",
            "P5.5-TechnicalDebt": "not-applicable",
            "P5.6-RollbackSafety": "not-applicable",
        }
        doc["SESSION_STATE"]["review_package_presented"] = True
        doc["SESSION_STATE"]["review_package_plan_body_present"] = True
        doc["SESSION_STATE"]["review_package_review_object"] = "Implementation review complete"
        doc["SESSION_STATE"]["review_package_ticket"] = "Implement auth"
        doc["SESSION_STATE"]["review_package_approved_plan_summary"] = "JWT plan"
        doc["SESSION_STATE"]["review_package_plan_body"] = "Implement JWT"
        doc["SESSION_STATE"]["review_package_implementation_scope"] = ""
        doc["SESSION_STATE"]["review_package_constraints"] = ""
        doc["SESSION_STATE"]["review_package_decision_semantics"] = "approve"
        doc["SESSION_STATE"]["review_package_evidence_summary"] = "Tests pass"
        doc["SESSION_STATE"]["session_state_revision"] = 1
        session_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

        module = _load_session_reader()
        capsys.readouterr()
        rc = module.main(["--materialize", f"--commands-home={commands_home}"])
        assert rc == 0, f"/continue must succeed, got rc={rc}"

        state = _read_state(session_path)
        assert state.get("active_gate") == "Evidence Presentation Gate", (
            f"After successful review, must route to Evidence Presentation Gate, got {state.get('active_gate')}"
        )
        assert state.get("implementation_review_complete") is True, (
            "implementation_review_complete must be True after loop completion"
        )

    def test_phase6_review_preserves_review_package_fields(self, tmp_path, monkeypatch, capsys):
        """/continue must preserve review_package fields through the loop."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)

        doc = _read_json(session_path)
        stable_digest = "sha256:" + hashlib.sha256(b"e2e:preserve:digest").hexdigest()
        doc["SESSION_STATE"]["Phase"] = "6-PostFlight"
        doc["SESSION_STATE"]["Next"] = "6"
        doc["SESSION_STATE"]["active_gate"] = "Implementation Internal Review"
        doc["SESSION_STATE"]["PersistenceCommitted"] = True
        doc["SESSION_STATE"]["WorkspaceReadyGateCommitted"] = True
        doc["SESSION_STATE"]["WorkspaceArtifactsCommitted"] = True
        doc["SESSION_STATE"]["PointerVerified"] = True
        doc["SESSION_STATE"]["RulebookLoadEvidence"] = {
            "core": "deferred",
            "profile": "deferred",
            "templates": "deferred",
            "addons": {},
        }
        doc["SESSION_STATE"]["ImplementationReview"] = {
            "implementation_review_complete": False,
            "completion_status": "phase6-in-progress",
            "iteration": 0,
            "min_self_review_iterations": 1,
            "max_iterations": 3,
            "prev_impl_digest": stable_digest,
            "curr_impl_digest": stable_digest,
            "revision_delta": "none",
        }
        doc["SESSION_STATE"]["implementation_review_complete"] = False
        doc["SESSION_STATE"]["phase6_state"] = "phase6_in_progress"
        doc["SESSION_STATE"]["phase_transition_evidence"] = True
        doc["SESSION_STATE"]["review_package_ticket"] = "Test ticket"
        doc["SESSION_STATE"]["review_package_approved_plan_summary"] = "Test plan"
        doc["SESSION_STATE"]["review_package_plan_body"] = "Test body"
        session_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

        module = _load_session_reader()
        capsys.readouterr()
        rc = module.main(["--materialize", f"--commands-home={commands_home}"])
        assert rc == 0

        state = _read_state(session_path)
        assert state.get("review_package_ticket") == "Test ticket", "review_package fields must be preserved"
        assert state.get("review_package_approved_plan_summary") == "Test plan"
        assert state.get("review_package_plan_body") == "Test body"


# ── H. COMPREHENSIVE CHAIN ─────────────────────────────────────────────────

@pytest.mark.e2e_governance
class TestE2EComprehensiveChain:
    """Single comprehensive E2E test that chains the full governance workflow.

    Exercises: /ticket → /plan (auto-generate) → /continue (Phase 5 routing)
    → /continue (Phase 6 internal review) → /review-decision approve → /implement.

    Uses mocked LLM responses for deterministic plan generation. Phase 5 and Phase 6
    self-review loops run without LLM (mechanical-only, completing at max iterations).
    """

    def test_full_workflow_chains_all_commands(self, tmp_path, monkeypatch, capsys):
        """Full workflow: /ticket → /plan → /continue → /continue → /review-decision → /implement."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        mock_plan_response: dict[str, object] = {
            "objective": "Build JWT bearer-token authentication for the REST API surface.",
            "target_state": "The /auth/login endpoint accepts credentials and returns a signed JWT token.",
            "target_flow": "1. Create auth module. 2. Add /auth/login route with credential validation. 3. Return JWT on success.",
            "state_machine": "JWT auth: Unauthenticated -> Authenticating -> Authenticated -> JWT Issued -> Ready.",
            "blocker_taxonomy": "No major blockers identified; all required dependencies are available in the codebase.",
            "audit": "Auth logs with timestamp and user ID are recorded for every login attempt.",
            "go_no_go": "Go: all prerequisites are satisfied and the implementation plan is sound.",
            "test_strategy": "Integration tests for /auth/login endpoint with JWT token generation and validation.",
            "reason_code": "AUTH-001",
        }
        mock_plan_file = tmp_path / "mock_plan_response.json"
        mock_plan_file.write_text(json.dumps(mock_plan_response), encoding="utf-8")
        monkeypatch.setenv("OPENCODE_PLAN_LLM_CMD", f"cat {mock_plan_file}")

        state = _read_state(session_path)
        state["Phase"] = "4"
        state["active_gate"] = "Ticket Input Gate"
        state.pop("Ticket", None)
        state.pop("Task", None)
        state.pop("TicketRecordDigest", None)
        state.pop("TaskRecordDigest", None)
        session_path.write_text(json.dumps({"SESSION_STATE": state}, indent=2) + "\n", encoding="utf-8")

        module_ticket = _load_module("phase4_intake_persist", "phase4_intake_persist.py")
        capsys.readouterr()
        rc_ticket = module_ticket.main([
            "--ticket-text=Implement JWT authentication endpoint for secure API access",
            "--task-text=Add JWT bearer token authentication to REST API endpoints",
            "--quiet",
        ])
        ticket_payload = json.loads(capsys.readouterr().out.strip())
        assert rc_ticket == 0, f"/ticket failed: {ticket_payload}; state Phase={state.get('Phase')}"

        state = _read_state(session_path)
        assert state.get("Ticket"), "Ticket must be persisted after /ticket"
        assert state.get("Task"), "Task must be persisted after /ticket"
        digest = state.get("TicketRecordDigest", "")
        assert digest and len(digest) == 64, f"TicketRecordDigest must be set (got {digest!r})"

        module_plan = _load_phase5()
        capsys.readouterr()
        rc_plan = module_plan.main(["--quiet"])
        plan_payload = json.loads(capsys.readouterr().out.strip())
        assert rc_plan == 0, f"/plan failed: {plan_payload}"

        state = _read_state(session_path)
        assert state.get("phase5_completed") is True, "Phase 5 must be completed after /plan"
        plan_record = workspace / "plan-record.json"
        assert plan_record.exists(), "plan-record.json must exist after /plan"
        pr = _read_json(plan_record)
        assert len(pr.get("versions", [])) >= 1, "plan-record.json must have at least one version"
        assert (workspace / ".governance" / "contracts" / "compiled_requirements.json").exists()

        session_reader = _load_session_reader()
        capsys.readouterr()
        state = _read_state(session_path)
        state["phase_transition_evidence"] = True
        state["Gates"] = {
            "P5-Architecture": "approved",
            "P5.3-TestQuality": "pass",
            "P5.5-TechnicalDebt": "not-applicable",
            "P5.6-RollbackSafety": "not-applicable",
        }
        session_path.write_text(json.dumps({"SESSION_STATE": state}, indent=2) + "\n", encoding="utf-8")

        rc_cont1 = session_reader.main(["--materialize", f"--commands-home={commands_home}"])
        assert rc_cont1 == 0, f"/continue (Phase 5 routing) failed"

        state = _read_state(session_path)
        phase_after_p5 = str(state.get("Phase") or "")
        assert phase_after_p5.startswith("6"), (
            f"After Phase 5 routing, must be in Phase 6, got Phase={phase_after_p5}"
        )

        capsys.readouterr()
        rc_cont2 = session_reader.main(["--materialize", f"--commands-home={commands_home}"])
        assert rc_cont2 == 0, f"/continue (Phase 6 routing) failed"

        state = _read_state(session_path)
        stable_digest = "sha256:" + hashlib.sha256(b"phase6:e2e:stable-digest").hexdigest()
        state["RulebookLoadEvidence"] = {
            "core": "deferred",
            "profile": "deferred",
            "templates": "deferred",
            "addons": {},
        }
        state["ImplementationReview"] = {
            "implementation_review_complete": False,
            "completion_status": "phase6-in-progress",
            "iteration": 0,
            "min_self_review_iterations": 1,
            "max_iterations": 1,
            "prev_impl_digest": stable_digest,
            "curr_impl_digest": stable_digest,
            "revision_delta": "none",
        }
        state["implementation_review_complete"] = False
        state["phase_transition_evidence"] = True
        state["phase6_state"] = "phase6_in_progress"
        state["review_package_presented"] = False
        state["review_package_plan_body_present"] = True
        state["review_package_review_object"] = "Final Phase-6 implementation review decision"
        state["review_package_ticket"] = state.get("Ticket", "")
        state["review_package_approved_plan_summary"] = "JWT authentication implementation"
        state["review_package_plan_body"] = "Implement JWT endpoint with RS256."
        state["review_package_implementation_scope"] = ""
        state["review_package_constraints"] = ""
        state["review_package_decision_semantics"] = "approve | changes_requested | reject"
        state["review_package_evidence_summary"] = "All acceptance tests pass"
        state["session_materialization_event_id"] = "evt-phase6-001"
        state["session_state_revision"] = 1
        session_path.write_text(json.dumps({"SESSION_STATE": state}, indent=2) + "\n", encoding="utf-8")

        capsys.readouterr()
        rc_cont2 = session_reader.main(["--materialize", f"--commands-home={commands_home}"])
        assert rc_cont2 == 0, f"/continue (Phase 6 internal review loop) failed"

        state = _read_state(session_path)
        assert state.get("implementation_review_complete") is True, (
            f"Internal review loop must complete with stable digest, got implementation_review_complete={state.get('implementation_review_complete')}"
        )
        assert state.get("phase6_state") == "phase6_completed", (
            f"Phase 6 state must be phase6_completed, got {state.get('phase6_state')}"
        )
        assert str(state.get("ImplementationReview", {}).get("iteration", 0)) == "1", (
            f"Review loop must complete at iteration 1 (stable digest), got iteration={state.get('ImplementationReview', {}).get('iteration')}"
        )

        state["review_package_presented"] = True
        state["review_package_loop_status"] = "completed"
        state["session_materialized_at"] = "2026-03-21T12:00:01Z"
        state["review_package_last_state_change_at"] = "2026-03-21T12:00:00Z"
        source = "|".join([
            str(state.get("review_package_review_object") or ""),
            str(state.get("review_package_ticket") or ""),
            str(state.get("review_package_approved_plan_summary") or ""),
            str(state.get("review_package_plan_body") or ""),
            str(state.get("review_package_implementation_scope") or ""),
            str(state.get("review_package_constraints") or ""),
            str(state.get("review_package_decision_semantics") or ""),
        ])
        digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
        state["review_package_presentation_receipt"] = {
            "receipt_type": "governance_review_presentation_receipt",
            "requirement_scope": "R-REVIEW-DECISION-001",
            "content_digest": digest,
            "rendered_at": "2026-03-21T12:00:01Z",
            "render_event_id": "evt-phase6-001",
            "gate": "Evidence Presentation Gate",
            "session_id": str(state.get("session_run_id") or "e2e-workflow-test"),
            "state_revision": "2",
            "source_command": "/continue",
            "digest": digest,
            "presented_at": "2026-03-21T12:00:01Z",
            "contract": "guided-ui.v1",
            "materialization_event_id": "evt-phase6-001",
        }
        session_path.write_text(json.dumps({"SESSION_STATE": state}, indent=2) + "\n", encoding="utf-8")

        state = _read_state(session_path)
        assert state.get("active_gate") == "Evidence Presentation Gate", (
            f"Must be at Evidence Presentation Gate before /review-decision, got {state.get('active_gate')}"
        )

        capsys.readouterr()
        module_rd = _load_review_decision()
        rc_rd = module_rd.main(["--decision", "approve", "--quiet"])
        rd_payload = json.loads(capsys.readouterr().out.strip())
        assert rc_rd == 0, f"/review-decision approve failed: {rd_payload}"
        assert rd_payload.get("status") == "ok"
        assert rd_payload.get("decision") == "approve"

        state = _read_state(session_path)
        assert state.get("workflow_complete") is True
        assert state.get("WorkflowComplete") is True
        assert state.get("active_gate") == "Workflow Complete"
        assert state.get("governance_status") == "complete"
        assert state.get("next_action_command") == "/implement"

        capsys.readouterr()

        def _mock_start_impl(*, session_path, events_path, actor, note):
            return {
                "status": "ok",
                "phase": "6-PostFlight",
                "next": "6",
                "active_gate": "Implementation Started",
                "next_gate_condition": "Implementation started. Continue work and produce repository artifacts.",
                "implementation_started": True,
                "implementation_llm_response_valid": True,
                "implementation_llm_validation_violations": [],
                "implementation_validation": {
                    "executor_invoked": True,
                    "executor_succeeded": True,
                    "changed_files": ["src/auth/jwt_auth.py"],
                    "is_compliant": True,
                },
            }

        module_impl = _load_implement()
        monkeypatch.setattr(module_impl, "start_implementation", _mock_start_impl)
        rc_impl = module_impl.main(["--quiet"])
        impl_payload = json.loads(capsys.readouterr().out.strip())
        assert rc_impl == 0, f"/implement (mocked) should return rc=0, got rc={rc_impl}"
        assert impl_payload.get("status") == "ok", (
            f"/implement chain must reach ok status, got {impl_payload}"
        )
        assert impl_payload.get("implementation_started") is True, (
            f"implementation_started must be True, got {impl_payload}"
        )
        assert impl_payload.get("implementation_llm_response_valid") is True, (
            f"LLM response must be schema-valid, got {impl_payload}"
        )
        assert impl_payload.get("implementation_llm_validation_violations") == [], (
            f"LLM validation violations must be empty, got {impl_payload}"
        )
        val = impl_payload.get("implementation_validation", {})
        assert val.get("executor_invoked") is True
        assert val.get("executor_succeeded") is True
        assert val.get("is_compliant") is True
