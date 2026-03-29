"""
test_governance_transition_truth.py — Transition truth: Phase / Gate / next_action invariants.

Every state has exactly ONE allowed next_action. The resolver must be deterministic.
Phase progression: Phase 4 → Phase 5 → Phase 6. Any deviation is a regression.

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
        token = str(cmd or "").strip()
        if token.startswith("cat "):
            path = Path(token[4:].strip())
            if path.exists():
                return path.read_text(encoding="utf-8")
        if token.startswith("echo '") and token.endswith("'"):
            return token[6:-1]
        if token.startswith('echo "') and token.endswith('"'):
            return token[6:-1]
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


@pytest.mark.e2e_governance
class TestE2EResponseContract:
    """Verify every governance command response obeys the response contract rules.

    Contract rules (from governance rulebook):
    1. Every response must have required fields: schema, status, phase, active_gate,
       next_gate_condition, next_action.
    2. next_action must name exactly ONE command (no ambiguity).
    3. status=error/blocked implies next_action=/continue (fail-closed, no forward progress).
    4. status=OK implies next_action is a meaningful forward step (not /continue
       unless the gate itself is a wait state).
    5. next_action command is deterministic from (active_gate, phase, next_gate_condition).
    6. next_action command must be one of the canonical command set.
    7. No response mixes "ok" status with a blocker hint in next_gate_condition.
    """

    def test_session_reader_snapshot_has_required_fields(self, tmp_path, monkeypatch, capsys):
        """/continue (session_reader) response snapshot has all required fields."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)

        module = _load_module("session_reader", "session_reader.py")
        capsys.readouterr()
        rc = module.main(["--materialize", f"--commands-home={commands_home}"])
        assert rc == 0, "/continue must succeed at Evidence Presentation Gate"

        output = capsys.readouterr().out
        assert "Current phase is" in output, "Narrative output must show current phase sentence"
        assert "active gate" in output, "Output must show active gate"
        if "Next action:" in output:
            assert output.strip().splitlines()[-1].startswith("Next action: ")

    def test_next_action_is_derived_from_active_gate_deterministically(self, tmp_path, monkeypatch):
        """The same (active_gate, phase) always produces the same next_action command."""
        from governance_runtime.engine.next_action_resolver import resolve_next_action

        cases = [
            (
                {"active_gate": "Ticket Input Gate", "phase": "Phase 4", "next_gate_condition": "run /ticket"},
                "/ticket",
            ),
            (
                {"active_gate": "Workflow Complete", "phase": "Phase 6", "next_gate_condition": "governance complete"},
                "/implement",
            ),
            (
                {"active_gate": "Evidence Presentation Gate", "phase": "Phase 6", "next_gate_condition": "run /review-decision <approve|changes_requested|reject>"},
                "/review-decision",
            ),
            (
                {"active_gate": "Plan Record Preparation Gate", "phase": "Phase 5", "next_gate_condition": "run /plan", "plan_record_versions": 0},
                "/plan",
            ),
        ]
        for snapshot, expected_cmd in cases:
            snapshot["status"] = "OK"
            render = resolve_next_action(snapshot)
            assert render.command == expected_cmd, (
                f"active_gate={snapshot['active_gate']!r} must derive {expected_cmd}, "
                f"got {render.command!r}"
            )

    def test_status_error_implies_next_action_is_continue(self, tmp_path, monkeypatch):
        """/continue with status=error must not suggest a forward command."""
        from governance_runtime.engine.next_action_resolver import resolve_next_action

        snapshot_error = {
            "status": "error",
            "phase": "Phase 5",
            "active_gate": "Binding Evidence Gate",
            "next_gate_condition": "BLOCKED",
        }
        render_error = resolve_next_action(snapshot_error)
        assert render_error.command == "/continue", (
            f"status=error must derive /continue, got {render_error.command!r}"
        )
        assert render_error.kind == "recovery", (
            f"kind must be 'recovery' for status=error, got {render_error.kind!r}"
        )

        snapshot_blocked = {
            "status": "blocked",
            "phase": "Phase 5",
            "active_gate": "Binding Evidence Gate",
            "next_gate_condition": "BLOCKED",
        }
        render_blocked = resolve_next_action(snapshot_blocked)
        assert render_blocked.command == "/continue", (
            f"status=blocked must derive /continue, got {render_blocked.command!r}"
        )
        assert render_blocked.kind == "blocked", (
            f"kind must be 'blocked' for status=blocked, got {render_blocked.kind!r}"
        )

    def test_workflow_complete_gate_always_suggests_implement(self, tmp_path, monkeypatch):
        """"Workflow Complete" gate must always derive /implement, never /continue."""
        from governance_runtime.engine.next_action_resolver import resolve_next_action

        snapshot = {
            "status": "OK",
            "phase": "Phase 6",
            "active_gate": "Workflow Complete",
            "next_gate_condition": "Governance complete. Run /implement to start implementation.",
        }
        render = resolve_next_action(snapshot)
        assert render.command == "/implement", (
            f"Workflow Complete must derive /implement, got {render.command!r}"
        )

    def test_ticket_input_gate_always_suggests_ticket(self, tmp_path, monkeypatch):
        """"Ticket Input Gate" must always derive /ticket, never /continue."""
        from governance_runtime.engine.next_action_resolver import resolve_next_action

        snapshot = {
            "status": "OK",
            "phase": "Phase 4",
            "active_gate": "Ticket Input Gate",
            "next_gate_condition": "Provide ticket and task details.",
        }
        render = resolve_next_action(snapshot)
        assert render.command == "/ticket", (
            f"Ticket Input Gate must derive /ticket, got {render.command!r}"
        )

    def test_evidence_presentation_gate_always_suggests_review_decision(self, tmp_path, monkeypatch):
        """"Evidence Presentation Gate" must derive /review-decision when next_gate_condition mentions it."""
        from governance_runtime.engine.next_action_resolver import resolve_next_action

        snapshot = {
            "status": "OK",
            "phase": "Phase 6",
            "active_gate": "Evidence Presentation Gate",
            "next_gate_condition": "run /review-decision <approve|changes_requested|reject>.",
        }
        render = resolve_next_action(snapshot)
        assert render.command == "/review-decision", (
            f"Evidence Presentation Gate must derive /review-decision, got {render.command!r}"
        )

    def test_next_action_command_is_always_canonical(self, tmp_path, monkeypatch):
        """next_action command must always be one of the canonical command set."""
        from governance_runtime.engine.next_action_resolver import resolve_next_action

        CANONICAL_COMMANDS = frozenset({
            "/ticket", "/plan", "/continue", "/review-decision",
            "/implement", "/implementation-decision", "/continue",
        })

        gates_and_phases = [
            ({"active_gate": "Ticket Input Gate", "phase": "Phase 4", "status": "OK"}),
            ({"active_gate": "Plan Record Preparation Gate", "phase": "Phase 5", "status": "OK"}),
            ({"active_gate": "Evidence Presentation Gate", "phase": "Phase 6", "status": "OK"}),
            ({"active_gate": "Workflow Complete", "phase": "Phase 6", "status": "OK"}),
            ({"active_gate": "Rulebook Load Gate", "phase": "Phase 1.3", "status": "OK"}),
            ({"active_gate": "Binding Evidence Gate", "phase": "Phase 1.1", "status": "OK"}),
            ({"active_gate": "Unknown Gate", "phase": "Phase 2", "status": "error"}),
        ]
        for snapshot in gates_and_phases:
            render = resolve_next_action(snapshot)
            assert render.command in CANONICAL_COMMANDS, (
                f"next_action command {render.command!r} is not canonical. "
                f"Snapshot: {snapshot!r}"
            )

    def test_phase5_completion_next_action_is_continue(self, tmp_path, monkeypatch, capsys):
        """/plan completion must set next_action=/continue (Phase 5 self-review loop entry)."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        mock_plan_response: dict[str, object] = {
            "objective": "Build JWT bearer-token authentication endpoint for secure API access.",
            "target_state": "The /auth/login endpoint accepts credentials and returns a signed JWT token.",
            "target_flow": "1. Create auth module with JWT support. 2. Add /auth/login route. 3. Return JWT on success.",
            "state_machine": "JWT auth: Unauthenticated -> Authenticating -> Authenticated -> JWT Issued -> Ready.",
            "blocker_taxonomy": "No major blockers identified; all required dependencies are available.",
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
        session_path.write_text(json.dumps({"SESSION_STATE": state}, indent=2) + "\n", encoding="utf-8")

        module_ticket = _load_module("phase4_intake_persist", "phase4_intake_persist.py")
        capsys.readouterr()
        module_ticket.main([
            "--ticket-text=Implement auth endpoint",
            "--task-text=Add JWT authentication",
            "--quiet",
        ])

        module_plan = _load_phase5()
        capsys.readouterr()
        rc_plan = module_plan.main(["--quiet"])
        assert rc_plan == 0, "/plan must succeed"
        plan_payload = json.loads(capsys.readouterr().out.strip())

        assert "next_action" in plan_payload, (
            "/plan response must include next_action field"
        )
        assert plan_payload["next_action"] == "run /continue.", (
            f"/plan completion must suggest /continue (Phase 5 review loop), "
            f"got {plan_payload['next_action']!r}"
        )

    def test_rework_clarification_gate_next_action_is_plan_or_ticket(self, tmp_path, monkeypatch):
        """"Rework Clarification Gate" with rework_clarification_input must derive /plan or /ticket."""
        from governance_runtime.engine.next_action_resolver import resolve_next_action

        snapshot_plan = {
            "status": "OK",
            "phase": "Phase 6",
            "active_gate": "rework clarification gate",
            "next_gate_condition": "run /plan for clarification",
            "rework_clarification_input": "bitte die architektur aendern",
        }
        render_plan = resolve_next_action(snapshot_plan)
        assert render_plan.command in ("/plan", "/ticket"), (
            f"Rework Clarification Gate with plan input must derive /plan or /ticket, got {render_plan.command!r}"
        )

        snapshot_ticket = {
            "status": "OK",
            "phase": "Phase 6",
            "active_gate": "rework clarification gate",
            "next_gate_condition": "run /ticket for clarification",
            "rework_clarification_input": "neue anforderung fuer rate limiting",
        }
        render_ticket = resolve_next_action(snapshot_ticket)
        assert render_ticket.command in ("/plan", "/ticket"), (
            f"Rework Clarification Gate with scope input must derive /plan or /ticket, got {render_ticket.command!r}"
        )

    def test_next_action_is_exactly_one_command_no_ambiguity(self, tmp_path, monkeypatch):
        """next_action label must describe exactly one command, not multiple alternatives."""
        from governance_runtime.engine.next_action_resolver import resolve_next_action

        gates = [
            "Ticket Input Gate",
            "Plan Record Preparation Gate",
            "Evidence Presentation Gate",
            "Workflow Complete",
        ]
        for gate in gates:
            snapshot = {
                "status": "OK",
                "phase": "Phase 6",
                "active_gate": gate,
                "next_gate_condition": "Awaiting next step.",
            }
            render = resolve_next_action(snapshot)
            label = render.label
            command_count = sum(
                1 for cmd in ("/ticket", "/plan", "/continue", "/review-decision", "/implement")
                if cmd in label
            )
            assert command_count == 1, (
                f"next_action label for gate {gate!r} must describe exactly ONE command, "
                f"got {command_count}: {label!r}"
            )

    def test_review_decision_response_has_next_action(self, tmp_path, monkeypatch, capsys):
        """/review-decision response must always include next_action field."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)

        module = _load_review_decision()
        capsys.readouterr()
        rc = module.main(["--decision", "approve", "--quiet"])
        assert rc == 0, "/review-decision approve must succeed"
        payload = json.loads(capsys.readouterr().out.strip())

        assert "next_action" in payload, "/review-decision response must include next_action"
        assert payload["next_action"], "next_action must be non-empty"

    def test_blocked_response_never_suggests_forward_progress(self, tmp_path, monkeypatch):
        """status=blocked/error responses must never suggest forward commands."""
        from governance_runtime.engine.next_action_resolver import resolve_next_action

        FORWARD_COMMANDS = {"/ticket", "/plan", "/review-decision", "/implement"}

        snapshot = {
            "status": "blocked",
            "phase": "Phase 5",
            "active_gate": "P5.3-TestQuality",
            "next_gate_condition": "BLOCKED_P5.3_TEST_QUALITY_GATE",
        }
        render = resolve_next_action(snapshot)
        assert render.command not in FORWARD_COMMANDS, (
            f"status=blocked must not suggest forward command, got {render.command!r}"
        )

    def test_plan_response_has_all_required_fields(self, tmp_path, monkeypatch, capsys):
        """/plan response must have status, phase, active_gate, next_action."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        mock_plan_response: dict[str, object] = {
            "objective": "Build JWT bearer-token authentication endpoint for secure API access.",
            "target_state": "The /auth/login endpoint accepts credentials and returns a signed JWT token.",
            "target_flow": "1. Create auth module with JWT support. 2. Add /auth/login route. 3. Return JWT on success.",
            "state_machine": "JWT auth: Unauthenticated -> Authenticating -> Authenticated -> JWT Issued -> Ready.",
            "blocker_taxonomy": "No major blockers identified; all required dependencies are available.",
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
        session_path.write_text(json.dumps({"SESSION_STATE": state}, indent=2) + "\n", encoding="utf-8")

        module_ticket = _load_module("phase4_intake_persist", "phase4_intake_persist.py")
        capsys.readouterr()
        module_ticket.main(["--ticket-text=Build auth", "--task-text=Add JWT", "--quiet"])

        module_plan = _load_phase5()
        capsys.readouterr()
        rc = module_plan.main(["--quiet"])
        payload = json.loads(capsys.readouterr().out.strip())

        assert rc == 0, f"/plan must succeed, got payload: {payload}"
        for field in ("status", "next_action", "plan_record_version", "phase_before", "phase_after"):
            assert field in payload, f"/plan response must include {field!r} field"
        assert payload["status"] == "ok", f"/plan status must be ok, got {payload.get('status')!r}"
        assert payload["next_action"], "next_action must be non-empty"

    def test_implement_response_has_next_action(self, tmp_path, monkeypatch, capsys):
        """/implement response must have next_action field."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)
        _write_phase6_approved_session(session_path)

        def _mock_start_impl(*, session_path, events_path, actor, note):
            return {
                "status": "ok",
                "phase": "6-PostFlight",
                "next": "6",
                "active_gate": "Implementation Started",
                "next_gate_condition": "Implementation started. Continue work.",
                "implementation_started": True,
                "implementation_llm_response_valid": True,
                "implementation_llm_validation_violations": [],
                "implementation_validation": {
                    "executor_invoked": True,
                    "executor_succeeded": True,
                    "changed_files": ["src/auth.py"],
                    "is_compliant": True,
                },
                "next_action": "run /continue.",
            }

        module_impl = _load_implement()
        monkeypatch.setattr(module_impl, "start_implementation", _mock_start_impl)
        capsys.readouterr()
        rc = module_impl.main(["--quiet"])
        payload = json.loads(capsys.readouterr().out.strip())

        assert rc == 0, f"/implement must succeed, got payload: {payload}"
        assert "next_action" in payload, "/implement response must include next_action"
        assert payload.get("next_action"), "next_action must be non-empty"

    def test_next_action_kind_is_consistent_with_status(self, tmp_path, monkeypatch):
        """When kind=blocked, status must not be OK. When kind=terminal, gate must be Workflow Complete."""
        from governance_runtime.engine.next_action_resolver import resolve_next_action

        snapshot_blocked = {
            "status": "blocked",
            "phase": "Phase 5",
            "active_gate": "P5.3-TestQuality",
            "next_gate_condition": "BLOCKED",
        }
        render_blocked = resolve_next_action(snapshot_blocked)
        assert render_blocked.kind in ("blocked", "error", "normal"), (
            f"kind must be blocked/error/normal for status=blocked, got {render_blocked.kind!r}"
        )

        snapshot_ok = {
            "status": "OK",
            "phase": "Phase 6",
            "active_gate": "Workflow Complete",
            "next_gate_condition": "Governance complete.",
        }
        render_ok = resolve_next_action(snapshot_ok)
        assert render_ok.kind in ("terminal", "normal"), (
            f"kind must be terminal/normal for status=OK at Workflow Complete, got {render_ok.kind!r}"
        )


@pytest.mark.e2e_governance
class TestE2ENextActionUX:
    """Verify next_action fields are present, meaningful, and professional across all paths."""

    def test_plan_next_action_is_run_continue(self, tmp_path, monkeypatch, capsys):
        """/plan ok response must include a meaningful next_action."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        module = _load_phase5()
        module.main(["--plan-text", "Plan.", "--quiet"])
        payload = json.loads(capsys.readouterr().out.strip())
        assert "next_action" in payload
        assert len(payload["next_action"]) > 5

    def test_review_decision_approve_next_action_includes_implement(self, tmp_path, monkeypatch, capsys):
        """approve next_action must mention /implement."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)

        module = _load_review_decision()
        module.main(["--decision", "approve", "--quiet"])
        payload = json.loads(capsys.readouterr().out.strip())
        assert "/implement" in payload.get("next_action", "")

    def test_review_decision_reject_next_action_includes_ticket(self, tmp_path, monkeypatch, capsys):
        """reject next_action must mention /ticket."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)

        module = _load_review_decision()
        module.main(["--decision", "reject", "--quiet"])
        payload = json.loads(capsys.readouterr().out.strip())
        assert "ticket" in payload.get("next_action", "").lower()

    def test_review_decision_changes_requested_next_action_describes_clarification(
        self, tmp_path, monkeypatch, capsys
    ):
        """changes_requested next_action must describe the clarification requirement."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)

        module = _load_review_decision()
        module.main(["--decision", "changes_requested", "--quiet"])
        payload = json.loads(capsys.readouterr().out.strip())
        na = payload.get("next_action", "")
        assert len(na) > 5

    def test_session_state_next_action_command_after_approve(self, tmp_path, monkeypatch, capsys):
        """After approve, session state next_action_command must be /implement."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)

        module = _load_review_decision()
        module.main(["--decision", "approve", "--quiet"])

        state = _read_state(session_path)
        assert state.get("next_action_command") == "/implement"


@pytest.mark.e2e_governance
class TestE2EStateTransitionInvariants:
    """Verify state transitions obey the phase_api.yaml graph.

    Key invariants:
    1. Phase implies a specific active_gate (or range of gates).
    2. Allowed transitions: Phase 4 -> Phase 5 -> Phase 5.x -> Phase 6.
    3. Reject at Evidence Presentation Gate returns to Phase 4 Ticket Input Gate.
    4. Phase 5 advancement requires the required Gates entry to be approved.
    5. Workflow Complete gate is only reachable in Phase 6.
    """

    def test_phase4_implies_ticket_input_gate(self, tmp_path, monkeypatch, capsys):
        """Phase 4 must have Ticket Input Gate and /ticket is the required next action.

        Setup: Phase 4 with Ticket/Task missing triggers Ticket Input Gate.
        /ticket then advances to Phase 5 with Ticket and Task recorded.
        """
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        state = _read_state(session_path)
        state["phase"] = "4"
        state["active_gate"] = "Ticket Input Gate"
        state["next_gate_condition"] = "Provide ticket and task details."
        state.pop("Ticket", None)
        state.pop("Task", None)
        state.pop("TicketRecordDigest", None)
        state.pop("TaskRecordDigest", None)
        session_path.write_text(json.dumps({"SESSION_STATE": state}, indent=2) + "\n", encoding="utf-8")

        module_ticket = _load_module("phase4_intake_persist", "phase4_intake_persist.py")
        capsys.readouterr()
        rc = module_ticket.main([
            "--ticket-text=Implement auth endpoint for secure API access",
            "--task-text=Add JWT bearer token authentication",
            "--quiet",
        ])
        assert rc == 0, "/ticket must succeed"

        state = _read_state(session_path)
        phase_val = state.get("phase") or state.get("Phase") or ""
        assert str(phase_val).startswith("5"), (
            f"Phase after /ticket must advance to Phase 5, got Phase={phase_val!r}"
        )
        assert state.get("Ticket"), "Ticket must be set after /ticket"
        assert state.get("Task"), "Task must be set after /ticket"
        digest = str(state.get("TicketRecordDigest", ""))
        assert len(digest) == 64 and all(c in "0123456789abcdef" for c in digest), (
            f"TicketRecordDigest must be valid SHA256 hex (64 chars), got {digest!r}"
        )

    def test_phase5_requires_ticket_present(self, tmp_path, monkeypatch, capsys):
        """/plan must block when Ticket is missing (Phase 4 prerequisite)."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        state = _read_state(session_path)
        state["phase"] = "4"
        state["active_gate"] = "Ticket Input Gate"
        state.pop("Ticket", None)
        state.pop("Task", None)
        session_path.write_text(json.dumps({"SESSION_STATE": state}, indent=2) + "\n", encoding="utf-8")

        module_plan = _load_phase5()
        capsys.readouterr()
        rc = module_plan.main(["--quiet"])
        payload = json.loads(capsys.readouterr().out.strip())
        assert rc != 0, "/plan must fail when Ticket is missing"
        assert payload.get("status") in ("blocked", "error"), (
            f"/plan without ticket must be blocked, got status={payload.get('status')!r}"
        )

    def test_phase6_reject_returns_to_phase4(self, tmp_path, monkeypatch, capsys):
        """reject at Evidence Presentation Gate must return session to Phase 4 Ticket Input Gate."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)

        module = _load_review_decision()
        capsys.readouterr()
        rc = module.main(["--decision", "reject", "--quiet"])
        assert rc == 0, "/review-decision reject must succeed"

        state = _read_state(session_path)
        phase_val = state.get("phase") or state.get("Phase") or ""
        assert str(phase_val).startswith("4"), (
            f"reject must return to Phase 4, got Phase={phase_val!r}"
        )
        assert "ticket input gate" in str(state.get("active_gate", "")).lower(), (
            f"reject must set active_gate to Ticket Input Gate, got {state.get('active_gate')!r}"
        )

    def test_phase5_architecture_gate_blocks_without_approval(self, tmp_path, monkeypatch, capsys):
        """Phase 5 must not advance to Phase 6 without P5-Architecture=approved."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        mock_plan_response: dict[str, object] = {
            "objective": "Build JWT authentication endpoint for secure API access.",
            "target_state": "The /auth/login endpoint accepts credentials and returns a signed JWT token.",
            "target_flow": "1. Create auth module. 2. Add /auth/login route. 3. Return JWT on success.",
            "state_machine": "Unauthenticated -> Authenticated -> JWT Issued.",
            "blocker_taxonomy": "No major blockers identified.",
            "audit": "Auth logs recorded for every login attempt.",
            "go_no_go": "Go: all prerequisites are satisfied.",
            "test_strategy": "Integration tests for /auth/login.",
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
        session_path.write_text(json.dumps({"SESSION_STATE": state}, indent=2) + "\n", encoding="utf-8")

        module_ticket = _load_module("phase4_intake_persist", "phase4_intake_persist.py")
        capsys.readouterr()
        module_ticket.main(["--ticket-text=Build auth", "--task-text=Add JWT", "--quiet"])

        module_plan = _load_phase5()
        capsys.readouterr()
        module_plan.main(["--quiet"])

        state = _read_state(session_path)
        gates = state.get("Gates", {})
        if gates.get("P5-Architecture") != "approved":
            state["Gates"] = {"P5-Architecture": "pending"}
            session_path.write_text(json.dumps({"SESSION_STATE": state}, indent=2) + "\n", encoding="utf-8")

        capsys.readouterr()
        rc_cont = _load_module("session_reader", "session_reader.py").main(["--materialize", f"--commands-home={commands_home}"])
        assert rc_cont == 0, "/continue must succeed even without architecture approval"

        state = _read_state(session_path)
        phase_val = state.get("phase") or state.get("Phase") or ""
        assert not str(phase_val).startswith("6"), (
            f"Phase must NOT advance to 6 without P5-Architecture=approved, got Phase={phase_val!r}"
        )

    def test_workflow_complete_gate_only_in_phase6(self, tmp_path, monkeypatch):
        """Workflow Complete gate must only be reachable in Phase 6 contexts.

        The kernel must never set active_gate=Workflow Complete outside Phase 6.
        Verify via /review-decision approve path: it must land in Phase 6.
        """
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)

        module_rd = _load_review_decision()
        module_rd.main(["--decision", "approve", "--quiet"])

        state = _read_state(session_path)
        assert "workflow complete" in str(state.get("active_gate", "")).lower(), (
            f"approve must set active_gate to Workflow Complete, got {state.get('active_gate')!r}"
        )
        phase_val = state.get("phase") or state.get("Phase") or ""
        assert str(phase_val).startswith("6"), (
            f"Workflow Complete must be in Phase 6, got Phase={phase_val!r}"
        )

    def test_phase6_changes_requested_routes_to_rework_gate(self, tmp_path, monkeypatch, capsys):
        """changes_requested at Evidence Presentation Gate must enter Rework Clarification Gate."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)

        module = _load_review_decision()
        capsys.readouterr()
        rc = module.main(["--decision", "changes_requested", "--quiet"])
        assert rc == 0, "/review-decision changes_requested must succeed"

        state = _read_state(session_path)
        gate = str(state.get("active_gate", "")).lower()
        assert "rework" in gate or "clarification" in gate, (
            f"changes_requested must enter Rework Clarification Gate, got {state.get('active_gate')!r}"
        )

    def test_state_revision_increments_on_materialize(self, tmp_path, monkeypatch, capsys):
        """session_state_revision must increment with each /continue."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)

        state = _read_state(session_path)
        rev0 = int(str(state.get("session_state_revision", "0")).strip() or "0")
        session_path.write_text(json.dumps({"SESSION_STATE": state}, indent=2) + "\n", encoding="utf-8")

        _load_module("session_reader", "session_reader.py").main(["--materialize", f"--commands-home={commands_home}"])
        state = _read_state(session_path)
        rev1 = int(str(state.get("session_state_revision", "0")).strip() or "0")
        assert rev1 > rev0, (
            f"session_state_revision must increment after /continue: was {rev0}, now {rev1}"
        )

    def test_phase5_plan_record_persists_before_continuing(self, tmp_path, monkeypatch, capsys):
        """Phase 5 must persist plan-record.json before routing to Phase 6."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        mock_plan_response: dict[str, object] = {
            "objective": "Build JWT authentication endpoint.",
            "target_state": "The /auth/login endpoint accepts credentials and returns a JWT token.",
            "target_flow": "1. Create auth module. 2. Add /auth/login route. 3. Return JWT.",
            "state_machine": "Unauthenticated -> Authenticated -> JWT Issued.",
            "blocker_taxonomy": "No major blockers identified.",
            "audit": "Auth logs recorded for every login attempt.",
            "go_no_go": "Go: all prerequisites are satisfied.",
            "test_strategy": "Integration tests for /auth/login.",
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
        session_path.write_text(json.dumps({"SESSION_STATE": state}, indent=2) + "\n", encoding="utf-8")

        _load_module("phase4_intake_persist", "phase4_intake_persist.py").main(
            ["--ticket-text=Build auth", "--task-text=Add JWT", "--quiet"]
        )
        _load_phase5().main(["--quiet"])

        plan_record = workspace / "plan-record.json"
        assert plan_record.exists(), "plan-record.json must exist after /plan"
        pr = _read_json(plan_record)
        assert len(pr.get("versions", [])) >= 1, "plan-record.json must have at least one version"
        v = pr["versions"][0]
        digest = v.get("plan_record_digest", "")
        assert digest.startswith("sha256:"), (
            f"plan_record_digest must be sha256:..., got {digest!r}"
        )

    def test_ticket_record_digest_valid_after_ticket(self, tmp_path, monkeypatch, capsys):
        """TicketRecordDigest must be valid SHA256 after /ticket."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        state = _read_state(session_path)
        state["phase"] = "4"
        state["active_gate"] = "Ticket Input Gate"
        state.pop("Ticket", None)
        session_path.write_text(json.dumps({"SESSION_STATE": state}, indent=2) + "\n", encoding="utf-8")

        module_ticket = _load_module("phase4_intake_persist", "phase4_intake_persist.py")
        capsys.readouterr()
        module_ticket.main(["--ticket-text=Build auth", "--task-text=Add JWT", "--quiet"])

        state = _read_state(session_path)
        digest = str(state.get("TicketRecordDigest", ""))
        assert len(digest) == 64 and all(c in "0123456789abcdef" for c in digest), (
            f"TicketRecordDigest must be SHA256 hex (64 chars), got {digest!r}"
        )


@pytest.mark.e2e_governance
class TestE2EReworkClassificationBoundary:
    """Test classify_rework_clarification() boundary cases: implicit/explicit scope,
    ambiguous plan, borderline clarification, vague insufficient."""

    def test_scope_change_explicit_scope_keywords(self):
        """Explicit scope-change tokens: 'new requirement', 'scope aender', 'task aender'."""
        from governance_runtime.application.use_cases.rework_clarification import (
            classify_rework_clarification,
            derive_next_rail,
        )

        for text in [
            "new requirement for rate limiting",
            "scope aendern auf bearer token",
            "task aenderung: otra priorität",
            "neue anforderung: MFA support",
        ]:
            result = classify_rework_clarification(text)
            assert result == "scope_change", (
                f"Text with explicit scope tokens must classify as scope_change: {text!r} -> {result}"
            )
            assert derive_next_rail(result) == "/ticket", (
                f"scope_change must derive /ticket, got {derive_next_rail(result)}"
            )

    def test_scope_change_implicit(self):
        """Implicit scope change: 'scope bleibt' suppresses scope_hit."""
        from governance_runtime.application.use_cases.rework_clarification import (
            classify_rework_clarification,
        )

        result = classify_rework_clarification("Scope bleibt, aber bitte anderes vorgehen")
        assert result == "plan_change", (
            f"'scope bleibt' + plan tokens must be plan_change, got {result}"
        )

    def test_plan_change_plan_keywords(self):
        """Plan-change tokens: 'plan', 'architektur', 'vorgehensweise', 'strategie'."""
        from governance_runtime.application.use_cases.rework_clarification import (
            classify_rework_clarification,
            derive_next_rail,
        )

        for text in [
            "Bitte die architektur ueberdenken",
            "Das vorgehensweise muss geaendert werden",
            "Die strategie fuer die implementierung anpassen",
            "Die struktur des plans aendern",
            "Die plan sequenz aendern",
            "Bitte den plan aendern auf JWT",
        ]:
            result = classify_rework_clarification(text)
            assert result == "plan_change", (
                f"Text with plan tokens must classify as plan_change: {text!r} -> {result}"
            )
            assert derive_next_rail(result) == "/plan", (
                f"plan_change must derive /plan, got {derive_next_rail(result)}"
            )

    def test_plan_change_with_scope_token(self):
        """'scope' token is higher priority than plan tokens."""
        from governance_runtime.application.use_cases.rework_clarification import (
            classify_rework_clarification,
        )

        result = classify_rework_clarification("Scope und plan beide relevant")
        assert result == "scope_change", (
            f"scope token must take priority over plan, got {result}"
        )

    def test_clarification_only_clarification_keywords(self):
        """Clarification-only: 'klarstellen', 'erklaeren', 'begruenden', 'praezisieren'."""
        from governance_runtime.application.use_cases.rework_clarification import (
            classify_rework_clarification,
            derive_next_rail,
        )

        for text in [
            "Bitte das klarstellen bitte sehr",
            "Die begruendung fuer die entscheidung erklaeren",
            "Die formulierung des textes praezisieren",
            "bitte das erklaeren wie das gemeint war",
            "Clarify the reasoning behind this decision",
        ]:
            result = classify_rework_clarification(text)
            assert result == "clarification_only", (
                f"Clarification tokens must classify as clarification_only: {text!r} -> {result}"
            )
            assert derive_next_rail(result) == "/continue", (
                f"clarification_only must derive /continue, got {derive_next_rail(result)}"
            )

    def test_clarification_only_at_minimum_length(self):
        """Clarification-only at minimum viable length: tokens present but barely."""
        from governance_runtime.application.use_cases.rework_clarification import (
            classify_rework_clarification,
        )

        result = classify_rework_clarification("Bitte klarstellen")
        assert result == "clarification_only", (
            f"'Bitte klarstellen' (12+ chars, clarification token) must be clarification_only, got {result}"
        )

    def test_insufficient_vague_only(self):
        """Vague tokens alone (<12 chars) are insufficient."""
        from governance_runtime.application.use_cases.rework_clarification import (
            classify_rework_clarification,
            derive_next_rail,
        )

        for text in ["ueberarbeiten", "nochmal", "anders machen", "fixen"]:
            result = classify_rework_clarification(text)
            assert result == "insufficient", (
                f"Vague tokens without context must be insufficient: {text!r} -> {result}"
            )
            assert derive_next_rail(result) is None, (
                f"insufficient must derive None, got {derive_next_rail(result)}"
            )

    def test_insufficient_too_short_no_tokens(self):
        """Empty or very short text with no recognized tokens is insufficient."""
        from governance_runtime.application.use_cases.rework_clarification import (
            classify_rework_clarification,
        )

        for text in ["", "  ", "ok", "ja"]:
            result = classify_rework_clarification(text)
            assert result == "insufficient", (
                f"Empty/short text with no tokens must be insufficient: {text!r} -> {result}"
            )

    def test_priority_order_scope_over_plan_over_clarification(self):
        """Priority order: scope > plan > clarification."""
        from governance_runtime.application.use_cases.rework_clarification import (
            classify_rework_clarification,
        )

        text = "neue anforderung mit anderer architektur und klarstellung"
        result = classify_rework_clarification(text)
        assert result == "scope_change", (
            f"scope has highest priority even with plan+clarification tokens: {result}"
        )

        text2 = "architektur mit klarstellung noetig"
        result2 = classify_rework_clarification(text2)
        assert result2 == "plan_change", (
            f"plan has priority over clarification: {result2}"
        )

    def test_is_rework_clarification_active_gate(self):
        """is_rework_clarification_active detects Rework Clarification Gate."""
        from governance_runtime.application.use_cases.rework_clarification import (
            is_rework_clarification_active,
        )

        assert is_rework_clarification_active(
            {"active_gate": "Rework Clarification Gate"}
        ) is True
        assert is_rework_clarification_active(
            {"active_gate": "Evidence Presentation Gate"}
        ) is False
        assert is_rework_clarification_active(
            {"phase6_state": "phase6_changes_requested"}
        ) is True
        assert is_rework_clarification_active(
            {"phase6_state": "phase6_completed"}
        ) is False

# ── F. PERSISTED STATE CONTRACT ─────────────────────────────────────────

@pytest.mark.e2e_governance
class TestE2EPersistedStateContract:
    """Test persisted session state contract: gate/condition consistency.

    After any command succeeds, the persisted state must contain consistent
    active_gate, next_gate_condition, and Phase fields. Blocked/error
    responses must not persist forward-progress state changes.

    Note: next_action_command is only persisted by /review-decision (approve path).
    Other commands set next_action in response payload only.
    """

    def test_ticket_persists_gate_and_condition(self, tmp_path, monkeypatch, capsys):
        """After /ticket success, session state must persist active_gate, next_gate_condition, Phase."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        state = _read_state(session_path)
        state["phase"] = "4"
        state["active_gate"] = "Ticket Input Gate"
        session_path.write_text(json.dumps({"SESSION_STATE": state}, indent=2) + "\n", encoding="utf-8")

        module = _load_module("phase4_intake_persist", "phase4_intake_persist.py")
        capsys.readouterr()
        rc = module.main(["--ticket-text", "New feature", "--task-text", "Add X", "--quiet"])
        assert rc == 0, f"/ticket must succeed, got rc={rc}"

        state = _read_state(session_path)
        phase_val = state.get("phase") or state.get("Phase") or ""
        assert phase_val in ("5", "5-ArchitectureReview"), (
            f"/ticket must advance to Phase 5 (kernel routes to Architecture Review), got Phase={phase_val}"
        )
        assert state.get("active_gate") == "Plan Record Preparation Gate", (
            f"/ticket must set active_gate=Plan Record Preparation Gate, got {state.get('active_gate')}"
        )
        assert state.get("Ticket") == "New feature", "/ticket must persist Ticket text"

        payload = json.loads(capsys.readouterr().out.strip())
        assert payload.get("status") == "ok"
        assert "next_action" in payload, "response must include next_action"

    def test_plan_persists_gate_and_plan_record(self, tmp_path, monkeypatch, capsys):
        """After /plan success, session state must persist active_gate, Phase, and plan record fields."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        module_plan = _load_phase5()
        json_data = '{"objective":"Implement feature X with high quality","target_state":"Feature X delivered and verified","target_flow":"Step 1: Setup. Step 2: Implement. Step 3: Test.","state_machine":"Draft -> Active -> Complete","blocker_taxonomy":"Dependencies,Complexity","audit":"Test results, coverage report","go_no_go":"All tests pass, no critical bugs","test_strategy":"Unit + integration tests","reason_code":"PLAN-001"}'
        _set_pipeline_mode_with_bindings(
            monkeypatch,
            workspace,
            execution_cmd=_mock_llm_cmd(json_data),
        )
        capsys.readouterr()
        rc = module_plan.main(["--quiet"])
        assert rc == 0, f"/plan must succeed with valid schema, got rc={rc}"

        state = _read_state(session_path)
        assert state.get("active_gate") == "Architecture Review Gate", (
            f"/plan must keep active_gate=Architecture Review Gate, got {state.get('active_gate')}"
        )
        phase_val = state.get("phase") or state.get("Phase") or ""
        assert phase_val in ("5", "5-ArchitectureReview"), (
            f"/plan must keep Phase at 5, got {phase_val}"
        )
        assert "PlanRecordVersions" in state or "PlanRecordDigest" in state, (
            "/plan must persist plan record fields"
        )

    def test_phase6_review_decision_persists_next_action_command(self, tmp_path, monkeypatch, capsys):
        """After /review-decision approve, session state must contain next_action_command=/implement."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)
        _write_phase6_session(session_path, workspace, repo_fp)

        module = _load_review_decision()
        capsys.readouterr()
        rc = module.main(["--decision", "approve", "--quiet"])
        assert rc == 0, f"/review-decision approve must succeed, got rc={rc}"

        state = _read_state(session_path)
        assert "next_action_command" in state, (
            "next_action_command must be persisted after /review-decision approve"
        )
        assert state["next_action_command"] == "/implement", (
            f"after approve, next_action_command must be /implement, got {state['next_action_command']}"
        )

    def test_gate_condition_phase_triple_is_consistent_after_ticket(self, tmp_path, monkeypatch, capsys):
        """After /ticket, active_gate, next_gate_condition, and Phase must be consistent."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        state = _read_state(session_path)
        state["phase"] = "4"
        state["active_gate"] = "Ticket Input Gate"
        session_path.write_text(json.dumps({"SESSION_STATE": state}, indent=2) + "\n", encoding="utf-8")

        module = _load_module("phase4_intake_persist", "phase4_intake_persist.py")
        capsys.readouterr()
        rc = module.main(["--ticket-text", "Feature X", "--task-text", "Add X", "--quiet"])
        assert rc == 0

        state = _read_state(session_path)
        gate = state.get("active_gate", "")
        phase = state.get("phase") or state.get("Phase") or ""
        condition = state.get("next_gate_condition", "")

        assert gate == "Plan Record Preparation Gate", (
            f"after /ticket, active_gate must be Plan Record Preparation Gate, got {gate!r}"
        )
        assert phase in ("5", "5-ArchitectureReview"), (
            f"after /ticket, Phase must be 5, got {phase!r}"
        )
        assert condition != "", "next_gate_condition must be non-empty after /ticket"

    def test_blocked_response_does_not_advance_gate(self, tmp_path, monkeypatch, capsys):
        """Blocked/error responses must not advance the gate or phase."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        state_before = _read_state(session_path)
        gate_before = state_before.get("active_gate", "")
        phase_before = state_before.get("phase") or state_before.get("Phase") or ""

        (workspace / "governance-config.json").write_text(
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
        monkeypatch.delenv("AI_GOVERNANCE_EXECUTION_BINDING", raising=False)
        monkeypatch.delenv("AI_GOVERNANCE_REVIEW_BINDING", raising=False)
        monkeypatch.delenv("OPENCODE_PLAN_LLM_CMD", raising=False)
        monkeypatch.delenv("OPENCODE_IMPLEMENT_LLM_CMD", raising=False)

        module = _load_phase5()
        capsys.readouterr()
        rc = module.main(["--quiet"])
        assert rc == 2, "blocked /plan must return rc!=0"

        state = _read_state(session_path)
        assert state.get("active_gate") == gate_before, (
            f"blocked /plan must not change active_gate, was {gate_before!r}"
        )
        phase_after = state.get("phase") or state.get("Phase") or ""
        assert phase_after == phase_before, (
            f"blocked /plan must not change Phase, was {phase_before!r}"
        )

    def test_response_includes_next_action(self, tmp_path, monkeypatch, capsys):
        """All successful commands must include next_action in the response payload."""
        config_root, commands_home, session_path, repo_fp, workspace = _write_e2e_fixture(tmp_path)
        _set_env(monkeypatch, config_root, commands_home)

        state = _read_state(session_path)
        state["phase"] = "4"
        state["active_gate"] = "Ticket Input Gate"
        session_path.write_text(json.dumps({"SESSION_STATE": state}, indent=2) + "\n", encoding="utf-8")

        module = _load_module("phase4_intake_persist", "phase4_intake_persist.py")
        capsys.readouterr()
        rc = module.main(["--ticket-text", "Feature X", "--task-text", "Add X", "--quiet"])
        assert rc == 0

        payload = json.loads(capsys.readouterr().out.strip())
        assert payload.get("status") == "ok"
        assert "next_action" in payload, "successful response must include next_action"
        next_action = payload.get("next_action", "")
        assert len(next_action) > 0, "next_action must be non-empty"


@pytest.mark.e2e_governance
class TestE2ENextActionPhaseGateMatrix:
    """Complete phase/gate matrix for canonical next-action derivation."""

    @pytest.mark.parametrize(
        "snapshot,expected_command,expected_kind,expected_reason",
        [
            (
                {
                    "status": "OK",
                    "phase": "4",
                    "active_gate": "Ticket Input Gate",
                    "next_gate_condition": "Provide ticket/task details.",
                },
                "/ticket",
                "normal",
                "phase4-ticket-input",
            ),
            (
                {
                    "status": "OK",
                    "phase": "5-ArchitectureReview",
                    "active_gate": "Plan Record Preparation Gate",
                    "plan_record_versions": 0,
                    "next_gate_condition": "Plan record v1 missing.",
                },
                "/plan",
                "normal",
                "plan-record-missing",
            ),
            (
                {
                    "status": "OK",
                    "phase": "5-ArchitectureReview",
                    "active_gate": "Architecture Review Gate",
                    "plan_record_versions": 1,
                    "next_gate_condition": "Phase 5 progress.",
                },
                "/continue",
                "normal",
                "phase5-progress",
            ),
            (
                {
                    "status": "OK",
                    "phase": "6-PostFlight",
                    "active_gate": "Rework Clarification Gate",
                    "rework_clarification_input": "",
                    "next_gate_condition": "Clarify requested changes.",
                },
                "chat",
                "blocked",
                "rework-clarification-required",
            ),
            (
                {
                    "status": "OK",
                    "phase": "6-PostFlight",
                    "active_gate": "Rework Clarification Gate",
                    "rework_clarification_input": "Scope aendern: neue Anforderung fuer Ticket aufnehmen.",
                    "next_gate_condition": "Clarify requested changes.",
                },
                "/ticket",
                "normal",
                "rework-scope-change",
            ),
            (
                {
                    "status": "OK",
                    "phase": "6-PostFlight",
                    "active_gate": "Rework Clarification Gate",
                    "rework_clarification_input": "Bitte die Architektur und den Plan anpassen.",
                    "next_gate_condition": "Clarify requested changes.",
                },
                "/plan",
                "normal",
                "rework-plan-change",
            ),
            (
                {
                    "status": "OK",
                    "phase": "6-PostFlight",
                    "active_gate": "Rework Clarification Gate",
                    "rework_clarification_input": "Bitte klarstellen, warum die Entscheidung so getroffen wurde.",
                    "next_gate_condition": "Clarify requested changes.",
                },
                "/continue",
                "normal",
                "phase6-progress",
            ),
            (
                {
                    "status": "OK",
                    "phase": "6-PostFlight",
                    "active_gate": "Workflow Complete",
                    "next_gate_condition": "Workflow approved.",
                },
                "/implement",
                "terminal",
                "workflow-approved",
            ),
            (
                {
                    "status": "OK",
                    "phase": "6-PostFlight",
                    "active_gate": "Implementation Rework Clarification Gate",
                    "implementation_rework_clarification_input": "Acknowledged and updated.",
                },
                "/implement",
                "normal",
                "impl-rework-clarified",
            ),
            (
                {
                    "status": "OK",
                    "phase": "6-PostFlight",
                    "active_gate": "Implementation Started",
                },
                "execute",
                "implementation",
                "implementation-running",
            ),
            (
                {
                    "status": "OK",
                    "phase": "6-PostFlight",
                    "active_gate": "Implementation Execution In Progress",
                },
                "/continue",
                "normal",
                "implementation-loop-progress",
            ),
            (
                {
                    "status": "OK",
                    "phase": "6-PostFlight",
                    "active_gate": "Implementation Self Review",
                },
                "/continue",
                "normal",
                "implementation-loop-progress",
            ),
            (
                {
                    "status": "OK",
                    "phase": "6-PostFlight",
                    "active_gate": "Implementation Revision",
                },
                "/continue",
                "normal",
                "implementation-loop-progress",
            ),
            (
                {
                    "status": "OK",
                    "phase": "6-PostFlight",
                    "active_gate": "Implementation Verification",
                },
                "/continue",
                "normal",
                "implementation-loop-progress",
            ),
            (
                {
                    "status": "OK",
                    "phase": "6-PostFlight",
                    "active_gate": "Implementation Review Complete",
                },
                "/continue",
                "normal",
                "implementation-loop-progress",
            ),
            (
                {
                    "status": "OK",
                    "phase": "6-PostFlight",
                    "active_gate": "Implementation Blocked",
                },
                "/implement",
                "blocked",
                "implementation-blocked",
            ),
            (
                {
                    "status": "OK",
                    "phase": "6-PostFlight",
                    "active_gate": "Implementation Presentation Gate",
                },
                "/implementation-decision",
                "normal",
                "implementation-decision-available",
            ),
            (
                {
                    "status": "OK",
                    "phase": "6-PostFlight",
                    "active_gate": "Evidence Presentation Gate",
                },
                "/review-decision",
                "normal",
                "awaiting-final-decision",
            ),
            (
                {
                    "status": "error",
                    "phase": "6-PostFlight",
                    "active_gate": "Evidence Presentation Gate",
                },
                "/continue",
                "recovery",
                "error-status",
            ),
            (
                {
                    "status": "blocked",
                    "phase": "6-PostFlight",
                    "active_gate": "Evidence Presentation Gate",
                },
                "/continue",
                "blocked",
                "blocked-status",
            ),
        ],
    )
    def test_phase_gate_matrix_resolves_expected_next_action(
        self,
        snapshot,
        expected_command,
        expected_kind,
        expected_reason,
    ):
        from governance_runtime.engine.next_action_resolver import resolve_next_action

        action = resolve_next_action(snapshot)
        assert action.command == expected_command
        assert action.kind == expected_kind
        assert action.reason == expected_reason

    def test_phase4_next_action_label_includes_review_read_only_alternative(self):
        from governance_runtime.engine.next_action_resolver import resolve_next_action

        snapshot = {
            "status": "OK",
            "phase": "4",
            "active_gate": "Ticket Input Gate",
            "next_gate_condition": "Provide ticket/task details.",
        }
        action = resolve_next_action(snapshot)
        assert action.command == "/ticket"
        assert "/review" in action.label
        assert "read-only" in action.label.lower()
