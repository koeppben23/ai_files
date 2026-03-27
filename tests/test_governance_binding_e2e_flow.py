from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from governance_runtime.application.services import phase6_review_orchestrator as phase6
from governance_runtime.entrypoints import implement_start as implement_entry
from governance_runtime.entrypoints import session_reader as session_reader_entry

from .test_phase5_plan_record_persist import (
    _load_module as _load_phase5_module,
    _set_pipeline_bindings,
    _write_fixture_state,
    _write_workspace_governance_config,
)


@pytest.mark.governance
def test_e2e_pipeline_flow_persists_binding_evidence_across_plan_implement_and_phase6(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    phase5 = _load_phase5_module()
    config_root, commands_home, session_path, _repo_fp = _write_fixture_state(tmp_path)
    workspace_dir = session_path.parent
    events_path = workspace_dir / "logs" / "events.jsonl"

    monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
    monkeypatch.setenv("COMMANDS_HOME", str(commands_home))
    _write_workspace_governance_config(workspace_dir, pipeline_mode=True)

    session_payload = json.loads(session_path.read_text(encoding="utf-8"))
    session_state = session_payload.get("SESSION_STATE", {})
    session_state["Ticket"] = "AUTH-123"
    session_state["Task"] = "Implement login endpoint"
    session_path.write_text(
        json.dumps(session_payload, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )

    generated_plan = json.dumps(
        {
            "objective": "Add authentication endpoint with JWT support",
            "target_state": "New /auth/login endpoint accepts credentials and returns JWT token",
            "target_flow": "1. Add auth route. 2. Validate credentials. 3. Generate JWT. 4. Return token.",
            "state_machine": "unauthenticated -> authenticated (on valid login)",
            "blocker_taxonomy": "Credential store must be available; JWT secret must be configured",
            "audit": "Login events logged with timestamp and user id",
            "go_no_go": "JWT library available; credential store reachable; tests pass",
            "test_strategy": "Unit tests for token generation; integration test for login flow",
            "reason_code": "PLAN-AUTH-001",
        },
        ensure_ascii=True,
    )
    review_result = json.dumps({"verdict": "approve", "findings": []}, ensure_ascii=True)
    execution_binding_cmd = "EXEC_BINDING_CMD"
    review_binding_cmd = "REVIEW_BINDING_CMD"
    _set_pipeline_bindings(
        monkeypatch,
        execution=execution_binding_cmd,
        review=review_binding_cmd,
    )

    def _fake_subprocess_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        token = str(cmd)
        if execution_binding_cmd in token:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=generated_plan, stderr="")
        if review_binding_cmd in token:
            return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=review_result, stderr="")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", _fake_subprocess_run)

    rc_phase5 = phase5.main(["--quiet"])
    _ = capsys.readouterr()
    assert rc_phase5 == 0

    after_phase5 = json.loads(session_path.read_text(encoding="utf-8"))["SESSION_STATE"]
    assert after_phase5["phase5_plan_execution_binding_source"] == "env:AI_GOVERNANCE_EXECUTION_BINDING"
    assert after_phase5["phase5_review_binding_source"] == "env:AI_GOVERNANCE_REVIEW_BINDING"

    contracts_path = workspace_dir / ".governance" / "contracts" / "compiled_requirements.json"
    contracts_payload = {
        "schema": "governance-compiled-requirements.v1",
        "requirements": [
            {
                "id": "PLAN-STEP-001",
                "title": "Update service behavior",
                "code_hotspots": ["src/service.py"],
                "acceptance_tests": ["tests/test_service.py::test_happy"],
            }
        ],
    }
    contracts_path.parent.mkdir(parents=True, exist_ok=True)
    contracts_path.write_text(json.dumps(contracts_payload, ensure_ascii=True), encoding="utf-8")

    phase6_state = json.loads(session_path.read_text(encoding="utf-8"))
    state = phase6_state["SESSION_STATE"]
    state["phase"] = "6-PostFlight"
    state["next"] = "6"
    state["active_gate"] = "Workflow Complete"
    state["workflow_complete"] = True
    state["WorkflowComplete"] = True
    state["UserReviewDecision"] = {"decision": "approve"}
    state["requirement_contracts_present"] = True
    state["requirement_contracts_source"] = str(contracts_path)
    phase6_state["SESSION_STATE"] = state
    session_path.write_text(
        json.dumps(phase6_state, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(implement_entry, "_resolve_active_session_path", lambda: (session_path, events_path))
    monkeypatch.setattr(
        implement_entry,
        "_run_llm_edit_step",
        lambda **_kwargs: {
            "executor_invoked": True,
            "exit_code": 0,
            "stdout_path": "stdout.log",
            "stderr_path": "stderr.log",
            "changed_files": ["src/service.py"],
            "reason_code": "",
            "message": "",
        },
    )
    monkeypatch.setattr(
        implement_entry,
        "_run_targeted_checks",
        lambda _repo_root, _requirements: (
            (
                implement_entry.CheckResult(
                    name="tests/test_service.py::test_happy",
                    passed=True,
                    exit_code=0,
                    output_path="checks.log",
                ),
            ),
            True,
        ),
    )
    monkeypatch.setattr(
        implement_entry,
        "resolve_active_session_paths",
        lambda: (session_path, events_path, state, workspace_dir),
    )

    rc_implement = implement_entry.main(["--quiet"])
    implement_out = json.loads(capsys.readouterr().out.strip())
    assert rc_implement == 0
    assert implement_out["pipeline_mode"] is True
    assert implement_out["binding_role"] == "execution"
    assert implement_out["binding_source"] == "env:AI_GOVERNANCE_EXECUTION_BINDING"

    class _MockPolicyResolver:
        def load_mandate_schema(self):
            return type(
                "Mandate",
                (),
                {
                    "mandate_text": "Review implementation",
                    "review_output_schema_text": "{}",
                    "raw_schema": {"type": "object"},
                },
            )()

        def load_effective_review_policy(self, **_kwargs):
            return type("Policy", (), {"is_available": True, "policy_text": "Use review policy"})()

    class _MockLLMCaller:
        def __init__(self) -> None:
            self.is_configured = True

        def set_workspace_root(self, _workspace_root: Path | None) -> None:
            return None

        def build_context(self, **_kwargs):
            return {}

        def invoke(self, **_kwargs):
            return type(
                "Response",
                (),
                {
                    "invoked": True,
                    "stdout": json.dumps({"verdict": "approve", "findings": []}, ensure_ascii=True),
                    "stderr": "",
                    "return_code": 0,
                    "pipeline_mode": True,
                    "binding_role": "review",
                    "binding_source": "env:AI_GOVERNANCE_REVIEW_BINDING",
                },
            )()

    class _MockResponseValidator:
        def validate(self, response_text: str, mandates_schema=None):
            _ = response_text
            _ = mandates_schema
            return type(
                "Validation",
                (),
                {
                    "valid": True,
                    "verdict": "approve",
                    "findings": [],
                    "is_approve": True,
                    "is_changes_requested": False,
                },
            )()

    phase6._set_policy_resolver(_MockPolicyResolver())
    phase6._set_llm_caller(_MockLLMCaller())
    phase6._set_response_validator(_MockResponseValidator())
    try:
        rc_materialize = session_reader_entry.main(["--commands-home", str(commands_home), "--materialize"])
    finally:
        phase6._reset_instances()
    _ = capsys.readouterr()
    assert rc_materialize == 0

    final_state = json.loads(session_path.read_text(encoding="utf-8"))["SESSION_STATE"]
    assert final_state["phase6_review_binding_role"] == "review"
    assert final_state["phase6_review_binding_source"] == "env:AI_GOVERNANCE_REVIEW_BINDING"
    assert final_state["phase6_review_pipeline_mode"] is True

    all_events = [
        json.loads(line)
        for line in events_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    started_events = [row for row in all_events if row.get("event") == "IMPLEMENTATION_STARTED"]
    assert started_events
    assert started_events[-1]["binding_role"] == "execution"
    assert started_events[-1]["binding_source"] == "env:AI_GOVERNANCE_EXECUTION_BINDING"

    phase6_events = [row for row in all_events if row.get("event") == "phase6-implementation-review-iteration"]
    assert phase6_events
    assert phase6_events[-1]["llm_review_binding_role"] == "review"
    assert phase6_events[-1]["llm_review_binding_source"] == "env:AI_GOVERNANCE_REVIEW_BINDING"
