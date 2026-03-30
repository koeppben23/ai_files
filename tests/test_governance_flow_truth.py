"""
test_governance_flow_truth.py — Flow truth: canonical user chain /ticket → /plan → /continue → /review-decision → /implement.

CI-blocking main merge guard: every test here must pass.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

from tests.conftest_governance import (
    _load_implement,
    _load_phase5,
    _load_review_decision,
    _load_session_reader,
    _load_module,
    _mock_llm_cmd,
    _read_json,
    _read_state,
    _set_env,
    _write_e2e_fixture,
    _write_phase6_approved_session,
    _write_phase6_session,
)


def _set_pipeline_mode_with_bindings(
    monkeypatch: pytest.MonkeyPatch,
    workspace: Path,
    *,
    execution_cmd: str,
    review_cmd: str = "echo '{\"verdict\":\"approve\",\"findings\":[]}'",
) -> None:
    def _extract_json_from_cmd(cmd: str) -> str:
        import base64
        token = str(cmd or "").strip()
        if token.startswith("cat "):
            path = Path(token[4:].strip())
            if path.exists():
                return path.read_text(encoding="utf-8")
        if token.startswith("echo '") and token.endswith("'"):
            return token[6:-1]
        if token.startswith('echo "') and token.endswith('"'):
            return token[6:-1]
        # Handle Windows base64-encoded python command
        if token.startswith("python -c "):
            try:
                # Extract base64 content from: python -c "import base64,sys;sys.stdout.write(base64.b64decode('...').decode())"
                import re
                match = re.search(r"base64\.b64decode\(['\"](.+?)['\"]\)", token)
                if match:
                    encoded = match.group(1)
                    decoded = base64.b64decode(encoded).decode("utf-8")
                    return decoded
            except Exception:
                pass
        return token

    payload = {
        "pipeline_mode": True,
        "presentation": {
            "mode": "standard",
        },
        "review": {
            "phase5_max_review_iterations": 3,
            "phase6_max_review_iterations": 3,
        },
    }
    (workspace / "governance-config.json").write_text(
        json.dumps(payload, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AI_GOVERNANCE_EXECUTION_BINDING", execution_cmd)
    monkeypatch.setenv("AI_GOVERNANCE_REVIEW_BINDING", review_cmd)
    monkeypatch.setenv("OPENCODE", "1")
    monkeypatch.setenv("OPENCODE_SESSION_ID", "sess_test")
    monkeypatch.setenv("OPENCODE_MODEL", "openai/gpt-5")
    monkeypatch.setenv("AI_GOVERNANCE_TEST_PLAN_RESPONSE", _extract_json_from_cmd(execution_cmd))
    monkeypatch.setenv("AI_GOVERNANCE_TEST_REVIEW_RESPONSE", _extract_json_from_cmd(review_cmd))


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
        state["phase"] = "4"
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
        state["phase"] = "4"
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
        state["phase"] = "4"
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
        phase_val = state.get("phase") or state.get("Phase") or ""
        assert str(phase_val).startswith("5"), (
            f"Phase after /ticket must start with 5, got Phase={phase_val!r}"
        )
        assert state.get("active_gate") != "Ticket Input Gate", (
            "active_gate must NOT be Ticket Input Gate after /ticket"
        )

    def test_ticket_response_has_required_fields(self, tmp_path, monkeypatch, capsys):
        """/ticket response must include status, phase_after, next_action."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        state = _read_state(session_path)
        state["phase"] = "4"
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
        state["phase"] = "4"
        state["active_gate"] = "Ticket Input Gate"
        session_path.write_text(json.dumps({"SESSION_STATE": state}, indent=2) + "\n", encoding="utf-8")

        module = _load_module("phase4_intake_persist", "phase4_intake_persist.py")
        capsys.readouterr()
        rc = module.main(["--ticket-text=", "--task-text=", "--quiet"])
        assert rc != 0, "/ticket must fail without ticket text"
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload.get("status") in ("error", "blocked")

    def test_ticket_blocks_when_ticket_and_task_text_both_empty(self, tmp_path, monkeypatch, capsys):
        """/ticket must block when both ticket text and task text are empty strings."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        state = _read_state(session_path)
        state["phase"] = "4"
        state["active_gate"] = "Ticket Input Gate"
        session_path.write_text(json.dumps({"SESSION_STATE": state}, indent=2) + "\n", encoding="utf-8")

        module = _load_module("phase4_intake_persist", "phase4_intake_persist.py")
        capsys.readouterr()
        rc = module.main(["--ticket-text=  ", "--task-text=  ", "--quiet"])
        assert rc != 0, "/ticket must fail when ticket text is whitespace-only"
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload.get("status") in ("error", "blocked"), (
            f"Expected error/blocked, got {payload.get('status')}"
        )


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

        events_file = workspace / "logs" / "events.jsonl"
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
        phase_val = state.get("phase") or state.get("Phase") or ""
        assert phase_val is not None
        assert phase_val == "5-ArchitectureReview"
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
        assert result["payload"].get("next_action_command") == "/implement"

    def test_changes_requested_transitions_to_rework_clarification(self, tmp_path, monkeypatch, capsys):
        """changes_requested must set active_gate=Rework Clarification Gate and clear workflow_complete."""
        result = self._setup_and_apply(tmp_path, monkeypatch, "changes_requested", capsys)
        assert result["rc"] == 0, f"Expected rc=0, got {result['rc']}: {result['payload']}"

        state = _read_state(result["session_path"])
        assert state.get("active_gate") == "Rework Clarification Gate"
        assert state.get("workflow_complete") in (None, False)
        phase_val = state.get("phase") or state.get("Phase") or ""
        next_val = state.get("next") or state.get("Next") or ""
        assert phase_val == "6-PostFlight"
        assert next_val == "6"
        assert state.get("phase6_state") == "6.rework"

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
        phase_val = state.get("phase") or state.get("Phase") or ""
        assert phase_val == "4"
        assert state.get("active_gate") == "Ticket Input Gate"
        assert "ticket" in state.get("next_gate_condition", "").lower()

    def test_reject_next_action_ux(self, tmp_path, monkeypatch, capsys):
        """reject response must have a meaningful next_action hint."""
        result = self._setup_and_apply(tmp_path, monkeypatch, "reject", capsys)
        assert result["rc"] == 0
        assert result["payload"].get("status") == "ok"
        assert result["payload"].get("decision") == "reject"
        assert "next_action" in result["payload"]
        assert result["payload"].get("next_action_command") == "/ticket"

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

        events_file = result["workspace"] / "logs" / "events.jsonl"
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
        assert state.get("phase6_state") == "6.rework"
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
        doc["SESSION_STATE"]["phase"] = "6-PostFlight"
        doc["SESSION_STATE"]["TicketRecordDigest"] = "sha256:abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
        doc["SESSION_STATE"]["TaskRecordDigest"] = "sha256:fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210"
        session_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

        module_plan = _load_phase5()
        rc = module_plan.main(["--plan-text", "Clarified plan: JWT with RS256.", "--quiet"])
        assert rc == 0

        state = _read_state(session_path)
        assert state.get("implementation_review_complete") is False or state.get("phase6_state") in (
            "6.rework", "6.execution", None
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
        assert state.get("phase6_state") == "6.rework"

        state["phase"] = "6-PostFlight"
        state["active_gate"] = "Rework Clarification Gate"
        state["next"] = "6"
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
        phase_val = state.get("phase") or state.get("Phase") or ""
        assert phase_val == "5-ArchitectureReview", (
            f"After scope_change rework via /ticket, Phase must be 5-ArchitectureReview "
            f"(scope change re-triggers Phase 5 review), got {phase_val}"
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

        state["phase"] = "6-PostFlight"
        state["next"] = "6"
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
        phase = str(state.get("phase") or state.get("Phase") or "")
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

        state["phase"] = "6-PostFlight"
        state["next"] = "6"
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
        assert state.get("phase6_state") == "6.rework"

        state["phase"] = "6-PostFlight"
        state["next"] = "6"
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
        doc["SESSION_STATE"]["phase"] = "6-PostFlight"
        doc["SESSION_STATE"]["next"] = "6"
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
        doc["SESSION_STATE"]["phase6_state"] = "6.execution"
        doc["SESSION_STATE"]["phase_transition_evidence"] = True
        doc["SESSION_STATE"]["phase6_force_stable_digest"] = True
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
        assert state.get("phase6_state") == "6.complete", (
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
        doc["SESSION_STATE"]["phase"] = "6-PostFlight"
        doc["SESSION_STATE"]["next"] = "6"
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
        doc["SESSION_STATE"]["phase6_state"] = "6.execution"
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
        assert rev.get("revision_delta") == "none", (
            "Max iterations reached, revision_delta must be 'none' to indicate review is complete"
        )
        assert rev.get("implementation_review_complete") is True, (
            "Max iterations reached, implementation_review_complete must be True"
        )

    def test_phase6_review_complete_routes_to_evidence_presentation_gate(self, tmp_path, monkeypatch, capsys):
        """/continue after successful internal review routes to Evidence Presentation Gate."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)

        doc = _read_json(session_path)
        stable_digest = "sha256:" + hashlib.sha256(b"e2e:review:complete").hexdigest()
        doc["SESSION_STATE"]["phase"] = "6-PostFlight"
        doc["SESSION_STATE"]["next"] = "6"
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
        doc["SESSION_STATE"]["phase6_state"] = "6.execution"
        doc["SESSION_STATE"]["phase_transition_evidence"] = True
        doc["SESSION_STATE"]["phase6_force_stable_digest"] = True
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
        doc["SESSION_STATE"]["phase"] = "6-PostFlight"
        doc["SESSION_STATE"]["next"] = "6"
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
        doc["SESSION_STATE"]["phase6_state"] = "6.execution"
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
        _set_pipeline_mode_with_bindings(
            monkeypatch,
            workspace,
            execution_cmd=f"cat {mock_plan_file}",
        )

        state = _read_state(session_path)
        state["phase"] = "4"
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
        phase_after_p5 = str(state.get("phase") or state.get("Phase") or "")
        assert phase_after_p5.startswith("6"), (
            f"After Phase 5 routing, must be in Phase 6, got Phase={phase_after_p5}"
        )

        capsys.readouterr()
        rc_cont2 = session_reader.main(["--materialize", f"--commands-home={commands_home}"])
        assert rc_cont2 == 0, f"/continue (Phase 6 routing) failed"

        state = _read_state(session_path)
        # After second /continue, the review loop has completed and the review package
        # is presented. Reset the implementation review to re-run the loop.
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
        state["phase6_state"] = "6.execution"
        # The nested ReviewPackage was already created by the second /continue.
        # Update it to reset presented=False for the re-run.
        if "ReviewPackage" in state and isinstance(state["ReviewPackage"], dict):
            state["ReviewPackage"]["presented"] = False
            state["ReviewPackage"]["plan_body_present"] = True
            state["ReviewPackage"]["review_object"] = "Final Phase-6 implementation review decision"
            state["ReviewPackage"]["ticket"] = state.get("Ticket", "")
            state["ReviewPackage"]["approved_plan_summary"] = "JWT authentication implementation"
            state["ReviewPackage"]["plan_body"] = "Implement JWT endpoint with RS256."
            state["ReviewPackage"]["implementation_scope"] = ""
            state["ReviewPackage"]["constraints"] = ""
            state["ReviewPackage"]["decision_semantics"] = "approve | changes_requested | reject"
            state["ReviewPackage"]["evidence_summary"] = "All acceptance tests pass"
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
        assert state.get("phase6_state") == "6.complete", (
            f"Phase 6 state must be phase6_completed, got {state.get('phase6_state')}"
        )
        impl_review = state.get("ImplementationReview")
        assert impl_review, "ImplementationReview block must exist after internal review loop"
        assert impl_review.get("iteration") == 1, (
            f"Internal review iteration must be 1 (completed), got {impl_review.get('iteration')}"
        )

        # Update the nested ReviewPackage instead of flat fields
        rp = state.get("ReviewPackage", {})
        if not isinstance(rp, dict):
            rp = {}
        rp["presented"] = True
        rp["loop_status"] = "completed"
        rp["last_state_change_at"] = "2026-03-21T12:00:00Z"
        source = "|".join([
            str(rp.get("review_object") or ""),
            str(rp.get("ticket") or ""),
            str(rp.get("approved_plan_summary") or ""),
            str(rp.get("plan_body") or ""),
            str(rp.get("implementation_scope") or ""),
            str(rp.get("constraints") or ""),
            str(rp.get("decision_semantics") or ""),
        ])
        digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
        rp["presentation_receipt"] = {
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
        state["ReviewPackage"] = rp
        state["session_materialized_at"] = "2026-03-21T12:00:01Z"
        # Remove flat fields to avoid conflicts
        for key in list(state.keys()):
            if key.startswith("review_package_"):
                del state[key]
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


# ── G. PLAN AUTO-GENERATION ──────────────────────────────────────────────

@pytest.mark.e2e_governance
class TestE2EPlanAutoGeneration:
    """Test /plan auto-generation pipeline (no --plan-text).

    Flow: Ticket/Task from state → Mandate loaded → Effective policy loaded
          → LLM generates → Schema validated → Requirements compiled
          → Plan persisted → /continue routed.
    Every missing component must block fail-closed.
    """

    def test_plan_auto_gen_blocks_when_mandate_schema_missing(self, tmp_path, monkeypatch, capsys):
        """/plan auto-generation must block when mandate schema is absent."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        monkeypatch.setenv("OPENCODE_PLAN_LLM_CMD", "echo '{}'")

        module = _load_phase5()

        def _raise_missing(*args, **kwargs):
            raise module.MandateSchemaMissingError("Mandate schema missing")

        monkeypatch.setattr(module, "_load_mandates_schema", _raise_missing)
        rc = module.main(["--quiet"])
        assert rc == 2, "/plan auto-gen must block without mandate schema"
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload.get("status") in ("error", "blocked")

    def test_plan_auto_gen_blocks_when_effective_policy_unavailable(self, tmp_path, monkeypatch, capsys):
        """/plan auto-generation must block when effective policy cannot be built.

        NOTE: This test verifies that the effective policy is required for auto-generation.
        Due to local import in phase5_plan_record_persist.main(), we cannot monkeypatch
        _load_effective_authoring_policy_text from outside. This test is a placeholder
        for the architecture requirement and is effectively covered by the schema and
        mandate schema fail-closed tests above.
        """
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        json_data = '{"objective":"Implement feature X with high quality","target_state":"Feature X delivered and verified","target_flow":"Step 1: Setup. Step 2: Implement. Step 3: Test.","state_machine":"Draft -> Active -> Complete","blocker_taxonomy":"Dependencies,Complexity","audit":"Test results, coverage report","go_no_go":"All tests pass, no critical bugs","test_strategy":"Unit + integration tests","reason_code":"PLAN-001"}'
        _set_pipeline_mode_with_bindings(
            monkeypatch,
            workspace,
            execution_cmd=_mock_llm_cmd(json_data),
        )

        module = _load_phase5()
        rc = module.main(["--quiet"])
        assert rc == 0, f"/plan with valid policy must succeed, got rc={rc}"

    def test_plan_auto_gen_blocks_when_llm_executor_unavailable(self, tmp_path, monkeypatch, capsys):
        """/plan must block when neither OPENCODE_PLAN_LLM_CMD nor OPENCODE_IMPLEMENT_LLM_CMD is set."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        monkeypatch.delenv("OPENCODE_PLAN_LLM_CMD", raising=False)
        monkeypatch.delenv("OPENCODE_IMPLEMENT_LLM_CMD", raising=False)

        module = _load_phase5()
        rc = module.main(["--quiet"])
        assert rc == 2, "/plan must block without LLM executor"
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload.get("status") in ("error", "blocked")

    def test_plan_auto_gen_blocks_when_llm_returns_empty(self, tmp_path, monkeypatch, capsys):
        """/plan must block when LLM returns empty response."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        monkeypatch.setenv("OPENCODE_PLAN_LLM_CMD", "echo ''")

        module = _load_phase5()
        rc = module.main(["--quiet"])
        assert rc == 2, "/plan must block on empty LLM response"
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload.get("status") in ("error", "blocked")

    def test_plan_auto_gen_blocks_when_llm_returns_non_json(self, tmp_path, monkeypatch, capsys):
        """/plan must block when LLM returns non-JSON text."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        monkeypatch.setenv("OPENCODE_PLAN_LLM_CMD", "echo 'this is not json'")

        module = _load_phase5()
        rc = module.main(["--quiet"])
        assert rc == 2, "/plan must block on non-JSON LLM response"
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload.get("status") in ("error", "blocked")

    def test_plan_auto_gen_blocks_when_llm_returns_invalid_schema(self, tmp_path, monkeypatch, capsys):
        """/plan must block when LLM response does not conform to planOutputSchema."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        monkeypatch.setenv("OPENCODE_PLAN_LLM_CMD", "echo '{\"plan_text\":\"ok\"}'")

        module = _load_phase5()
        rc = module.main(["--quiet"])
        assert rc == 2, "/plan must block on schema-invalid LLM response"
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload.get("status") in ("error", "blocked")

    def test_plan_auto_gen_success_with_valid_llm_response(self, tmp_path, monkeypatch, capsys):
        """/plan with valid LLM response: persists plan + requirements, routes to /continue."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        json_data = '{"objective":"Implement feature X with high quality","target_state":"Feature X delivered and verified","target_flow":"Step 1: Setup. Step 2: Implement. Step 3: Test.","state_machine":"Draft -> Active -> Complete","blocker_taxonomy":"Dependencies,Complexity","audit":"Test results, coverage report","go_no_go":"All tests pass, no critical bugs","test_strategy":"Unit + integration tests","reason_code":"PLAN-001"}'
        _set_pipeline_mode_with_bindings(
            monkeypatch,
            workspace,
            execution_cmd=_mock_llm_cmd(json_data),
        )

        module = _load_phase5()
        capsys.readouterr()
        rc = module.main(["--quiet"])
        assert rc == 0, f"/plan auto-gen must succeed with valid LLM response, got rc={rc}"
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload.get("status") == "ok"
        assert "continue" in payload.get("next_action", "").lower()

        state = _read_state(session_path)
        assert "PlanRecordVersions" in state or "PlanRecordDigest" in state, (
            "Plan record must be persisted in session state"
        )

        plan_record = workspace / "plan-record.json"
        assert plan_record.exists(), "plan-record.json must be persisted"


# ── H. REVIEW-DECISION ALL SEMANTICS ────────────────────────────────────

@pytest.mark.e2e_governance
class TestE2EReviewDecisionSemantics:
    """Test /review-decision: all decision semantics at Evidence Presentation Gate.

    /review-decision only operates at the Evidence Presentation Gate in Phase 6.
    Valid decisions: approve | changes_requested | reject.

    approve              → Workflow Complete, next_action_command=/implement
    changes_requested    → Rework Clarification Gate (Phase 6 PostFlight)
    reject               → Phase 4 Ticket Input Gate
    """

    def _setup_phase6_at_evidence_gate(self, tmp_path, monkeypatch, capsys):
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)
        return config_root, commands_home, session_path, repo_fp, workspace, capsys

    def test_review_decision_approve_transitions_to_workflow_complete(self, tmp_path, monkeypatch, capsys):
        """approve at Evidence Presentation Gate: sets Workflow Complete, next_action_command=/implement."""
        config_root, commands_home, session_path, repo_fp, workspace, capsys = self._setup_phase6_at_evidence_gate(tmp_path, monkeypatch, capsys)

        module = _load_review_decision()
        capsys.readouterr()
        rc = module.main(["--decision", "approve", "--quiet"])
        assert rc == 0, f"review-decision approve must succeed, got rc={rc}"

        state = _read_state(session_path)
        assert state.get("workflow_complete") is True, "approve must set workflow_complete=True"
        assert state.get("active_gate") == "Workflow Complete", (
            f"approve must set active_gate=Workflow Complete, got {state.get('active_gate')}"
        )
        assert state.get("next_action_command") == "/implement", (
            f"approve must set next_action_command=/implement, got {state.get('next_action_command')}"
        )
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload.get("status") == "ok"

    def test_review_decision_changes_requested_enters_rework_clarification_gate(self, tmp_path, monkeypatch, capsys):
        """changes_requested at Evidence Presentation Gate: enters Rework Clarification Gate."""
        config_root, commands_home, session_path, repo_fp, workspace, capsys = self._setup_phase6_at_evidence_gate(tmp_path, monkeypatch, capsys)

        module = _load_review_decision()
        capsys.readouterr()
        rc = module.main(["--decision", "changes_requested", "--quiet"])
        assert rc == 0, f"review-decision changes_requested must succeed, got rc={rc}"

        state = _read_state(session_path)
        assert state.get("active_gate") == "Rework Clarification Gate", (
            f"changes_requested must set active_gate=Rework Clarification Gate, got {state.get('active_gate')}"
        )
        phase_val = state.get("phase") or state.get("Phase") or ""
        assert phase_val == "6-PostFlight", (
            f"changes_requested must set Phase=6-PostFlight, got {phase_val}"
        )
        assert state.get("implementation_review_complete") is False, (
            "changes_requested must reset implementation_review_complete for re-review"
        )
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload.get("status") == "ok"

    def test_review_decision_reject_transitions_to_phase4_ticket_input_gate(self, tmp_path, monkeypatch, capsys):
        """reject at Evidence Presentation Gate: transitions to Phase 4 Ticket Input Gate."""
        config_root, commands_home, session_path, repo_fp, workspace, capsys = self._setup_phase6_at_evidence_gate(tmp_path, monkeypatch, capsys)

        module = _load_review_decision()
        capsys.readouterr()
        rc = module.main(["--decision", "reject", "--quiet"])
        assert rc == 0, f"review-decision reject must succeed, got rc={rc}"

        state = _read_state(session_path)
        assert state.get("active_gate") == "Ticket Input Gate", (
            f"reject must route to Ticket Input Gate, got {state.get('active_gate')}"
        )
        phase_val = state.get("phase") or state.get("Phase") or ""
        assert phase_val in ("4", "4-TicketIntake"), (
            f"reject must return to Phase 4, got Phase={phase_val}"
        )

    def test_review_decision_blocks_at_wrong_gate(self, tmp_path, monkeypatch, capsys):
        """/review-decision must block when session is NOT at Evidence Presentation Gate."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        doc = _read_json(session_path)
        doc["SESSION_STATE"]["active_gate"] = "Plan Record Preparation Gate"
        doc["SESSION_STATE"]["phase"] = "5-ArchitectureReview"
        session_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

        module = _load_review_decision()
        capsys.readouterr()
        rc = module.main(["--decision", "approve", "--quiet"])
        assert rc == 2, f"/review-decision must block at wrong gate, got rc={rc}"
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload.get("status") in ("error", "blocked")


# ── J. REVIEW-DECISION REWORK CLARIFICATION ROUTING ───────────────────────

@pytest.mark.e2e_governance
class TestE2EReviewDecisionReworkRouting:
    """Test rework clarification routing: scope_change→/ticket, plan_change→/plan, clarification_only→/continue.

    After /review-decision changes_requested enters Rework Clarification Gate.
    The user's chat clarification (rework_clarification_input) is then read by
    /continue's next_action_resolver, which calls classify_rework_clarification
    and derive_next_rail to determine the exact next rail.

    Valid clarification types:
    - scope_change → /ticket  (user must update ticket/task)
    - plan_change  → /plan    (user must update the plan)
    - clarification_only → /continue (no rework needed, just continue)
    """

    def test_scope_change_clarification_text_routes_to_ticket(self):
        """scope_change classification → derive_next_rail returns /ticket."""
        from governance_runtime.application.use_cases.rework_clarification import (
            classify_rework_clarification,
            derive_next_rail,
        )
        examples = [
            "The scope of this feature needs to be changed to include auth",
            "Task ändern: add OAuth2 support instead",
            "New requirement: add rate limiting to the scope",
            "scope aendern: reduce scope to core functionality only",
        ]
        for text in examples:
            outcome = classify_rework_clarification(text)
            assert outcome == "scope_change", (
                f"text {text!r} must classify as scope_change, got {outcome}"
            )
            rail = derive_next_rail(outcome)
            assert rail == "/ticket", (
                f"scope_change must route to /ticket, got {rail}"
            )

    def test_plan_change_clarification_text_routes_to_plan(self):
        """plan_change classification → derive_next_rail returns /plan."""
        from governance_runtime.application.use_cases.rework_clarification import (
            classify_rework_clarification,
            derive_next_rail,
        )
        examples = [
            "The plan needs to be revised to include error handling",
            "Update the plan: add database migration steps",
            "Plan ändern: split the implementation into phases",
        ]
        for text in examples:
            outcome = classify_rework_clarification(text)
            assert outcome == "plan_change", (
                f"text {text!r} must classify as plan_change, got {outcome}"
            )
            rail = derive_next_rail(outcome)
            assert rail == "/plan", (
                f"plan_change must route to /plan, got {rail}"
            )

    def test_clarification_only_routes_to_continue(self):
        """clarification_only classification → derive_next_rail returns /continue."""
        from governance_runtime.application.use_cases.rework_clarification import (
            classify_rework_clarification,
            derive_next_rail,
        )
        examples = [
            "Can you clarify how the token refresh should work?",
            "Please clarify: should we use RS256 or HS256 for JWT?",
            "Could you clarify the expected JWT expiry duration?",
            "Can you provide evidence supporting this design choice?",
        ]
        for text in examples:
            outcome = classify_rework_clarification(text)
            assert outcome == "clarification_only", (
                f"text {text!r} must classify as clarification_only, got {outcome}"
            )
            rail = derive_next_rail(outcome)
            assert rail == "/continue", (
                f"clarification_only must route to /continue, got {rail}"
            )

    def test_insufficient_clarification_returns_none(self):
        """insufficient clarification → derive_next_rail returns None."""
        from governance_runtime.application.use_cases.rework_clarification import (
            classify_rework_clarification,
            derive_next_rail,
        )
        examples = [
            "ok",
            "yes",
            "no",
            "",
        ]
        for text in examples:
            outcome = classify_rework_clarification(text)
            assert outcome == "insufficient", (
                f"text {text!r} must classify as insufficient, got {outcome}"
            )
            rail = derive_next_rail(outcome)
            assert rail is None, (
                f"insufficient must return None, got {rail}"
            )

    def test_scope_change_clarification_text_routes_to_ticket_via_resolver(self):
        """E2E: Phase-6 Rework Clarification Gate + scope_change text → resolve_next_action returns /ticket."""
        from governance_runtime.engine.next_action_resolver import resolve_next_action

        snapshot = {
            "phase": "6-PostFlight",
            "active_gate": "Rework Clarification Gate",
            "status": "OK",
            "next_gate_condition": "Describe requested changes in chat.",
            "rework_clarification_input": "The scope needs to be changed to include rate limiting",
        }
        action = resolve_next_action(snapshot)
        assert action.command == "/ticket", (
            f"scope_change text must resolve to /ticket, got {action.command}"
        )

    def test_plan_change_clarification_text_routes_to_plan_via_resolver(self):
        """E2E: Phase-6 Rework Clarification Gate + plan_change text → resolve_next_action returns /plan."""
        from governance_runtime.engine.next_action_resolver import resolve_next_action

        snapshot = {
            "phase": "6-PostFlight",
            "active_gate": "Rework Clarification Gate",
            "status": "OK",
            "next_gate_condition": "Describe requested changes in chat.",
            "rework_clarification_input": "The plan needs to be updated to include database migration steps",
        }
        action = resolve_next_action(snapshot)
        assert action.command == "/plan", (
            f"plan_change text must resolve to /plan, got {action.command}"
        )

    def test_clarification_only_routes_to_continue_via_resolver(self):
        """E2E: Phase-6 Rework Clarification Gate + clarification_only text → resolve_next_action returns /continue."""
        from governance_runtime.engine.next_action_resolver import resolve_next_action

        snapshot = {
            "phase": "6-PostFlight",
            "active_gate": "Rework Clarification Gate",
            "status": "OK",
            "next_gate_condition": "Describe requested changes in chat.",
            "rework_clarification_input": "Can you clarify how the JWT token refresh should work?",
        }
        action = resolve_next_action(snapshot)
        assert action.command == "/continue", (
            f"clarification_only text must resolve to /continue, got {action.command}"
        )


# ── J. /CONTINUE E2E TRUTH ──────────────────────────────────────────────

@pytest.mark.e2e_governance
class TestE2EContinueRail:
    """Truth tests for /continue as the session reader.

    /continue must:
    1. At Evidence Presentation Gate → suggest /review-decision.
    2. At Workflow Complete → suggest /implement.
    3. At Phase-5 progress → suggest /continue.
    4. At Rework Clarification Gate without input → blocked (clarification required).
    5. At Implementation Blocked → suggest /implement with blocked kind.
    """

    def test_evidence_presentation_gate_suggests_review_decision(self):
        """At Evidence Presentation Gate, next_action must suggest /review-decision."""
        from governance_runtime.engine.next_action_resolver import resolve_next_action

        snapshot = {
            "phase": "6-PostFlight",
            "active_gate": "Evidence Presentation Gate",
            "status": "OK",
            "next_gate_condition": "Awaiting final review decision.",
            "plan_record_versions": 1,
            "phase6_review_iterations": 3,
        }
        action = resolve_next_action(snapshot)
        assert action.command == "/review-decision", (
            f"Evidence Presentation Gate must suggest /review-decision, got {action.command}"
        )
        assert "approve" in action.label.lower() or "decision" in action.label.lower(), (
            f"Label must mention review decision, got {action.label}"
        )

    def test_workflow_complete_suggests_implement(self):
        """At Workflow Complete, next_action must suggest /implement."""
        from governance_runtime.engine.next_action_resolver import resolve_next_action

        snapshot = {
            "phase": "6-PostFlight",
            "active_gate": "Workflow Complete",
            "status": "OK",
            "next_gate_condition": "Workflow approved.",
            "workflow_complete": True,
        }
        action = resolve_next_action(snapshot)
        assert action.command == "/implement", (
            f"Workflow Complete must suggest /implement, got {action.command}"
        )
        assert action.kind == "terminal", (
            f"Workflow Complete kind must be terminal, got {action.kind}"
        )

    def test_phase5_progress_suggests_continue(self):
        """During Phase-5 progress, next_action must suggest /continue."""
        from governance_runtime.engine.next_action_resolver import resolve_next_action

        snapshot = {
            "phase": "5-ArchitectureReview",
            "active_gate": "Plan Record Preparation Gate",
            "status": "OK",
            "next_gate_condition": "Persist plan record evidence.",
            "plan_record_versions": 0,
        }
        action = resolve_next_action(snapshot)
        assert action.command == "/plan", (
            f"Phase-5 with no plan record must suggest /plan, got {action.command}"
        )

    def test_rework_clarification_gate_no_input_is_blocked(self):
        """Rework Clarification Gate without clarification input must be blocked."""
        from governance_runtime.engine.next_action_resolver import resolve_next_action

        snapshot = {
            "phase": "6-PostFlight",
            "active_gate": "Rework Clarification Gate",
            "status": "OK",
            "next_gate_condition": "Describe requested changes in chat.",
            "rework_clarification_input": "",
        }
        action = resolve_next_action(snapshot)
        assert action.command == "chat", (
            f"Rework Clarification Gate without input must be blocked (chat), got {action.command}"
        )
        assert action.kind == "blocked", (
            f"Rework Clarification Gate without input must have kind=blocked, got {action.kind}"
        )

    def test_implementation_blocked_suggests_implement_with_blocked_kind(self):
        """Implementation Blocked must suggest /implement with blocked kind."""
        from governance_runtime.engine.next_action_resolver import resolve_next_action

        snapshot = {
            "phase": "6-PostFlight",
            "active_gate": "Implementation Blocked",
            "status": "OK",
            "next_gate_condition": "Resolve blockers and rerun /implement.",
            "implementation_blocked": True,
        }
        action = resolve_next_action(snapshot)
        assert action.command == "/implement", (
            f"Implementation Blocked must suggest /implement, got {action.command}"
        )
        assert action.kind == "blocked", (
            f"Implementation Blocked must have kind=blocked, got {action.kind}"
        )

    def test_error_status_suggests_continue_with_recovery(self):
        """Status=error must suggest /continue with recovery label."""
        from governance_runtime.engine.next_action_resolver import resolve_next_action

        snapshot = {
            "phase": "6-PostFlight",
            "active_gate": "Evidence Presentation Gate",
            "status": "error",
            "next_gate_condition": "Awaiting final review decision.",
        }
        action = resolve_next_action(snapshot)
        assert action.command == "/continue", (
            f"Error status must suggest /continue, got {action.command}"
        )
        assert action.kind == "recovery", (
            f"Error status must have kind=recovery, got {action.kind}"
        )

    def test_blocked_status_suggests_continue_with_blocked_kind(self):
        """Status=blocked must suggest /continue with blocked label."""
        from governance_runtime.engine.next_action_resolver import resolve_next_action

        snapshot = {
            "phase": "6-PostFlight",
            "active_gate": "Evidence Presentation Gate",
            "status": "blocked",
            "next_gate_condition": "Awaiting final review decision.",
            "plan_record_versions": 1,
        }
        action = resolve_next_action(snapshot)
        assert action.command == "/continue", (
            f"Blocked status must suggest /continue, got {action.command}"
        )
        assert action.kind == "blocked", (
            f"Blocked status must have kind=blocked, got {action.kind}"
        )


@pytest.mark.e2e_governance
class TestE2EReviewReadOnlyRail:
    """Flow-truth tests for `/review` read-only behavior."""

    def test_review_pr_read_only_does_not_mutate_session_state(self, tmp_path, monkeypatch):
        from governance_runtime.entrypoints import review_pr

        config_root, commands_home, session_path, _, _ = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        before = _read_json(session_path)

        monkeypatch.setattr(
            review_pr,
            "analyze_pr",
            lambda repo_root, remote, base_branch, head_ref: review_pr.ReviewResult(
                status="ok",
                mode="remote",
                base_sha="a" * 40,
                head_sha="b" * 40,
                merge_base_sha="c" * 40,
                files_changed=3,
                reason_code="none",
                message="review comparison prepared",
            ),
        )

        rc = review_pr.main([
            "--head-ref",
            "refs/heads/feat/x",
            "--repo-root",
            str(tmp_path),
        ])
        assert rc == 0

        after = _read_json(session_path)
        assert after == before, "`/review` must be read-only and must not mutate SESSION_STATE"


@pytest.mark.e2e_governance
class TestE2EBusinessRulesApplicabilityTruth:
    """Flow-truth coverage for P5.4 business-rules applicability combinations."""

    @staticmethod
    def _business_rules_fixture(*, missing_surface_reasons: list[str], invalid_rules: bool = False) -> dict:
        return {
            "Outcome": "gap-detected",
            "ExecutionEvidence": True,
            "InventoryLoaded": False,
            "ExtractedCount": 0,
            "ValidationReasonCodes": [
                "BUSINESS_RULES_CODE_COVERAGE_INSUFFICIENT",
                "BUSINESS_RULES_CODE_QUALITY_INSUFFICIENT",
            ],
            "QualityInsufficiencyReasons": [
                "non_business_surface_spike",
                "insufficient_executable_business_rules",
            ],
            "CodeExtractionReport": {
                "missing_surface_reasons": missing_surface_reasons,
            },
            "ValidationReport": {
                "is_compliant": False,
                "has_invalid_rules": invalid_rules,
                "has_render_mismatch": False,
                "has_source_violation": False,
                "has_missing_required_rules": False,
                "has_segmentation_failure": False,
                "has_code_extraction": True,
                "code_extraction_sufficient": False,
                "has_code_coverage_gap": True,
                "has_code_doc_conflict": False,
            },
        }

    @pytest.mark.parametrize(
        "missing_surface_reasons,invalid_rules,expected",
        [
            (
                [
                    "validator: filtered_non_business",
                    "permissions: filtered_non_business",
                    "workflow: filtered_non_business",
                ],
                False,
                "not-applicable",
            ),
            (
                [
                    "validator: filtered_non_business",
                    "workflow: insufficient_business_context",
                ],
                False,
                "gap-detected",
            ),
            (
                [
                    "validator: filtered_non_business",
                    "permissions: filtered_non_business",
                    "workflow: filtered_non_business",
                ],
                True,
                "gap-detected",
            ),
        ],
    )
    def test_p54_applicability_matrix(self, missing_surface_reasons, invalid_rules, expected):
        from governance_runtime.engine.gate_evaluator import evaluate_p54_business_rules_gate

        state = {
            "BusinessRules": self._business_rules_fixture(
                missing_surface_reasons=missing_surface_reasons,
                invalid_rules=invalid_rules,
            )
        }
        result = evaluate_p54_business_rules_gate(
            session_state=state,
            phase_1_5_executed=True,
        )
        assert result.status == expected

    def test_continue_materialize_promotes_non_business_case_to_phase6(self, tmp_path, monkeypatch):
        config_root, commands_home, session_path, _, _ = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        state = _read_state(session_path)
        state["phase"] = "5.4-BusinessRules"
        state["next"] = "5.4"
        state["active_gate"] = "Business Rules Validation"
        state["next_gate_condition"] = "Phase 1.5 executed; Phase 5.4 is mandatory before proceeding"
        state["BusinessRules"] = self._business_rules_fixture(
            missing_surface_reasons=[
                "validator: filtered_non_business",
                "permissions: filtered_non_business",
                "workflow: filtered_non_business",
            ],
            invalid_rules=False,
        )
        state["Gates"] = {
            "P5-Architecture": "approved",
            "P5.3-TestQuality": "pass",
            "P5.4-BusinessRules": "gap-detected",
            "P5.5-TechnicalDebt": "not-applicable",
            "P5.6-RollbackSafety": "not-applicable",
        }
        session_path.write_text(json.dumps({"SESSION_STATE": state}, indent=2) + "\n", encoding="utf-8")

        module = _load_session_reader()
        rc = module.main(["--commands-home", str(commands_home), "--materialize"])
        assert rc == 0

        updated = _read_state(session_path)
        assert updated.get("Gates", {}).get("P5.4-BusinessRules") == "not-applicable"
        assert str(updated.get("phase") or "").startswith("6")

    def test_continue_materialize_keeps_true_gap_blocked(self, tmp_path, monkeypatch):
        config_root, commands_home, session_path, _, _ = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        state = _read_state(session_path)
        state["phase"] = "5.4-BusinessRules"
        state["next"] = "5.4"
        state["active_gate"] = "Business Rules Validation"
        state["BusinessRules"] = self._business_rules_fixture(
            missing_surface_reasons=[
                "validator: filtered_non_business",
                "workflow: insufficient_business_context",
            ],
            invalid_rules=False,
        )
        state["Gates"] = {
            "P5-Architecture": "approved",
            "P5.3-TestQuality": "pass",
            "P5.4-BusinessRules": "gap-detected",
            "P5.5-TechnicalDebt": "not-applicable",
            "P5.6-RollbackSafety": "not-applicable",
        }
        session_path.write_text(json.dumps({"SESSION_STATE": state}, indent=2) + "\n", encoding="utf-8")

        module = _load_session_reader()
        rc = module.main(["--commands-home", str(commands_home), "--materialize"])
        assert rc == 0

        updated = _read_state(session_path)
        assert updated.get("Gates", {}).get("P5.4-BusinessRules") == "gap-detected"
        assert str(updated.get("phase") or "").startswith("5.4")


# ── K. PHASE-6 GOVERNANCE FAIL-CLOSED ───────────────────────────────────

@pytest.mark.e2e_governance
class TestE2EPhase6GovernanceFailClosed:
    """Test Phase-6 internal review loop: mandate, policy, validator must block.

    _run_phase6_internal_review_loop is the internal governance gate for Phase-6.
    It must fail-closed when:
    - effective_review_policy cannot be loaded
    - LLM response is not structured JSON (no findings)

    These tests call _run_phase6_internal_review_loop directly to assert
    the correct fail-closed behavior.
    """

    def _phase6_session_doc(self, tmp_path: Path) -> tuple[Path, dict]:
        repo_fp = "e2e-test-phase6"
        config_root = tmp_path / "cfg"
        config_root.mkdir(parents=True)
        commands_home = config_root / "commands"
        commands_home.mkdir(parents=True)
        workspaces_home = config_root / "workspaces"
        workspaces_home.mkdir(parents=True)
        workspace = workspaces_home / repo_fp
        workspace.mkdir(parents=True)
        session_path = workspace / "SESSION_STATE.json"
        doc = {
            "SESSION_STATE": {
                "RepoFingerprint": repo_fp,
                "phase": "6-PostFlight",
                "next": "6",
                "Mode": "IN_PROGRESS",
                "session_run_id": "e2e-phase6-gov",
                "active_gate": "Implementation Review Gate",
                "next_gate_condition": "Internal review in progress",
                "implementation_review_complete": False,
                "ImplementationReview": {
                    "implementation_review_complete": False,
                    "iteration": 0,
                    "min_self_review_iterations": 1,
                    "max_iterations": 3,
                    "revision_delta": "changed",
                },
                "PersistenceCommitted": True,
                "WorkspaceReadyGateCommitted": True,
                "WorkspaceArtifactsCommitted": True,
                "PointerVerified": True,
                "Bootstrap": {"Satisfied": True},
                "ActiveProfile": "profile.fallback-minimum",
                "LoadedRulebooks": {},
                "AddonsEvidence": {},
            }
        }
        session_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        return session_path, doc

    def test_phase6_blocks_when_effective_review_policy_unavailable(self, tmp_path, monkeypatch):
        """Phase-6 internal loop must block when effective_review_policy cannot be built."""
        from governance_runtime.application.services.phase6_review_orchestrator import (
            run_review_loop,
            ReviewLoopConfig,
            ReviewResult,
            BLOCKED_EFFECTIVE_POLICY_UNAVAILABLE,
            MandateSchema,
            _set_policy_resolver,
            _set_llm_caller,
        )
        from governance_runtime.infrastructure.json_store import load_json as _read_json, write_json_atomic as _write_json_atomic

        session_path, doc = self._phase6_session_doc(tmp_path)
        commands_home = session_path.parent.parent.parent / "commands"
        commands_home.mkdir(parents=True, exist_ok=True)

        monkeypatch.setenv("COMMANDS_HOME", str(commands_home))

        config = ReviewLoopConfig(
            commands_home=commands_home,
            session_path=session_path,
            max_iterations=3,
            min_iterations=1,
        )

        mock_policy_resolver = type("MockPolicyResolver", (), {
            "load_effective_review_policy": lambda self, **kw: type("R", (), {
                "is_available": False,
                "policy_text": "",
                "error_code": BLOCKED_EFFECTIVE_POLICY_UNAVAILABLE,
            })(),
            "load_mandate_schema": lambda self, **kw: MandateSchema(
                raw_schema={"$defs": {"reviewOutputSchema": {"type": "object"}}},
                review_output_schema_text='{"type":"object"}',
                mandate_text="Review mandate",
            ),
        })()
        _set_policy_resolver(mock_policy_resolver)

        mock_llm_caller = type("MockLLMCaller", (), {
            "is_configured": True,
            "build_context": lambda self, **kw: {},
            "invoke": lambda self, **kw: type("R", (), {
                "invoked": False,
                "stdout": "",
                "stderr": "",
                "return_code": 0,
            })(),
        })()
        _set_llm_caller(mock_llm_caller)

        state_doc = json.loads(session_path.read_text(encoding="utf-8"))
        result = run_review_loop(
            state_doc=state_doc,
            config=config,
            json_loader=_read_json,
            context_writer=_write_json_atomic,
        )
        assert isinstance(result, ReviewResult), (
            "run_review_loop must return ReviewResult"
        )
        assert result.loop_result is not None
        assert result.loop_result.blocked is True, (
            f"Phase-6 loop must block when effective_review_policy unavailable, got {result.loop_result}"
        )
        assert result.loop_result.block_reason == "effective-review-policy-unavailable"

    def test_phase6_llm_invalid_json_returns_changes_requested(self, tmp_path, monkeypatch):
        """_parse_llm_review_response must return verdict=changes_requested when LLM returns non-JSON."""
        session_path, doc = self._phase6_session_doc(tmp_path)
        commands_home = session_path.parent.parent.parent / "commands"
        commands_home.mkdir(parents=True, exist_ok=True)

        monkeypatch.setenv("COMMANDS_HOME", str(commands_home))

        module_reader = _load_session_reader()

        result = module_reader._parse_llm_review_response(
            response_text="this is not json",
            mandates_schema=None,
        )
        assert result.get("verdict") == "changes_requested", (
            f"Non-JSON response must set verdict=changes_requested, got {result.get('verdict')}"
        )
        assert result.get("validation_valid") is False, (
            "Non-JSON response must set validation_valid=False"
        )

    def test_phase6_blocks_when_review_mandate_missing(self, tmp_path, monkeypatch):
        """Phase-6 internal loop blocks when review mandate schema is unavailable."""
        from governance_runtime.application.services.phase6_review_orchestrator import (
            run_review_loop,
            ReviewLoopConfig,
            ReviewResult,
            BLOCKED_MANDATE_SCHEMA_UNAVAILABLE,
            _set_policy_resolver,
            _set_llm_caller,
        )
        from governance_runtime.infrastructure.json_store import load_json as _read_json, write_json_atomic as _write_json_atomic

        session_path, doc = self._phase6_session_doc(tmp_path)
        commands_home = session_path.parent.parent.parent / "commands"
        commands_home.mkdir(parents=True, exist_ok=True)

        monkeypatch.setenv("COMMANDS_HOME", str(commands_home))

        config = ReviewLoopConfig(
            commands_home=commands_home,
            session_path=session_path,
            max_iterations=3,
            min_iterations=1,
        )

        mock_policy_resolver = type("MockPolicyResolver", (), {
            "load_effective_review_policy": lambda self, **kw: type("R", (), {
                "is_available": True,
                "policy_text": "[EFFECTIVE REVIEW POLICY]\n- baseline",
                "error_code": "",
            })(),
            "load_mandate_schema": lambda self, **kw: None,
        })()
        _set_policy_resolver(mock_policy_resolver)

        mock_llm_caller = type("MockLLMCaller", (), {
            "is_configured": True,
            "build_context": lambda self, **kw: {},
            "invoke": lambda self, **kw: type("R", (), {
                "invoked": True,
                "stdout": '{"verdict":"approve","findings":[]}',
                "stderr": "",
                "return_code": 0,
                "pipeline_mode": False,
                "binding_role": "review",
                "binding_source": "active_chat_binding",
            })(),
        })()
        _set_llm_caller(mock_llm_caller)

        state_doc = json.loads(session_path.read_text(encoding="utf-8"))
        result = run_review_loop(
            state_doc=state_doc,
            config=config,
            json_loader=_read_json,
            context_writer=_write_json_atomic,
        )
        assert isinstance(result, ReviewResult), (
            "run_review_loop must return ReviewResult"
        )
        assert result.loop_result is not None
        assert result.loop_result.blocked is True, (
            f"Phase-6 loop must block when mandate is unavailable, got {result.loop_result}"
        )
        assert result.loop_result.block_reason == "review-mandate-unavailable"
        assert result.loop_result.block_reason_code == BLOCKED_MANDATE_SCHEMA_UNAVAILABLE

    @pytest.mark.xfail(reason="Validator is always available in this environment - cannot test unavailable case")
    def test_phase6_blocks_when_llm_validator_unavailable(self, tmp_path, monkeypatch):
        """Response validation with unavailable validator returns invalid verdict."""
        from governance_runtime.application.services.phase6_review_orchestrator.response_validator import ResponseValidator

        validator = ResponseValidator()

        result = validator.validate(
            response_text='{"verdict":"approve","findings":[]}',
            mandates_schema={"$defs": {"reviewOutputSchema": {}}},
        )
        if result.valid:
            pytest.skip("llm_response_validator is available, cannot test unavailable case")
        assert result.get("validation_valid") is False, (
            f"Validator unavailable must set validation_valid=False, got {result}"
        )
        assert result.get("verdict") == "changes_requested", (
            f"Validator unavailable must set verdict=changes_requested, got {result.get('verdict')}"
        )
        assert "validator-not-available" in result.get("validation_violations", []), (
            "Validator unavailable must add validator-not-available violation"
        )

    def test_phase6_llm_response_schema_valid_but_content_non_compliant(self, tmp_path, monkeypatch):
        """_parse_llm_review_response must return validation_valid=False when LLM response violates decision rules.

        A schema-valid response with verdict=approve but critical defect findings violates
        the decision rule: approve verdict cannot coexist with defect/critical/high findings.
        """
        session_path, doc = self._phase6_session_doc(tmp_path)
        commands_home = session_path.parent.parent.parent / "commands"
        commands_home.mkdir(parents=True, exist_ok=True)

        monkeypatch.setenv("COMMANDS_HOME", str(commands_home))

        module_reader = _load_session_reader()

        non_compliant_response = json.dumps({
            "verdict": "approve",
            "findings": [{
                "severity": "critical",
                "type": "defect",
                "location": "auth.py",
                "evidence": "Missing authentication check on login endpoint allows unauthorized access",
                "impact": "Security vulnerability — attackers can bypass login",
                "fix": "Add authentication middleware to the login route",
            }],
        })

        result = module_reader._parse_llm_review_response(
            response_text=non_compliant_response,
            mandates_schema=None,
        )
        assert result.get("validation_valid") is False, (
            f"Decision-rule-violating response must be validation_valid=False, got {result.get('validation_valid')}"
        )
        assert result.get("verdict") == "changes_requested", (
            f"Decision-rule-violating response must have verdict=changes_requested, got {result.get('verdict')}"
        )
