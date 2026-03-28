from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from governance_runtime.contracts.enforcement import FAIL_CLOSED_MISSING_CONTRACT, EnforcementResult
from governance_runtime.entrypoints import implement_start as entrypoint
from governance_runtime.engine.implementation_validation import (
    RC_CHECK_SELECTOR_INVALID,
    RC_GOVERNANCE_ONLY_CHANGES,
    RC_NO_REPO_CHANGES,
    RC_TARGETED_CHECKS_FAILED,
    RC_TARGETED_CHECKS_MISSING,
)

_ORIGINAL_RUN_LLM_EDIT_STEP = entrypoint._run_llm_edit_step
_ORIGINAL_RUN_TARGETED_CHECKS = entrypoint._run_targeted_checks


@pytest.fixture(autouse=True)
def _default_executor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        entrypoint,
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
        entrypoint,
        "_run_targeted_checks",
        lambda _repo_root, _requirements: (
            (
                entrypoint.CheckResult(
                    name="tests/test_service.py::test_happy",
                    passed=True,
                    exit_code=0,
                    output_path="checks.log",
                ),
            ),
            True,
        ),
    )


def _write_session(path: Path, *, phase: str = "6-PostFlight", decision: str = "approve") -> None:
    payload = {
        "schema": "opencode-session-state.v1",
        "SESSION_STATE": {
            "phase": phase,
            "active_gate": "Workflow Complete",
            "workflow_complete": decision == "approve",
            "WorkflowComplete": decision == "approve",
            "UserReviewDecision": {"decision": decision},
            "requirement_contracts_present": True,
            "requirement_contracts_count": 2,
            "Ticket": "Implement approved plan in domain files",
            "Task": "Update service behavior",
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")


def _write_plan(path: Path) -> None:
    payload = {
        "status": "active",
        "versions": [{"version": 1, "plan_record_text": "Approved plan summary"}],
    }
    path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")


def _write_contracts(path: Path) -> None:
    payload = {
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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")


def _wire_active_paths(monkeypatch: pytest.MonkeyPatch, session_path: Path, events_path: Path) -> None:
    monkeypatch.setattr(entrypoint, "_resolve_active_session_path", lambda: (session_path, events_path))


def _set_pipeline_mode_bindings(monkeypatch: pytest.MonkeyPatch, workspace_dir: Path) -> None:
    (workspace_dir / "governance-config.json").write_text(
        json.dumps(
            {
                "pipeline_mode": True,
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
    monkeypatch.setenv("AI_GOVERNANCE_EXECUTION_BINDING", "mock-executor")
    monkeypatch.setenv("AI_GOVERNANCE_REVIEW_BINDING", "mock-review")


def test_happy_executor_diff_plus_checks_passes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    session_path = tmp_path / "SESSION_STATE.json"
    events_path = tmp_path / "events.jsonl"
    _write_session(session_path)
    _write_plan(tmp_path / "plan-record.json")
    _write_contracts(tmp_path / ".governance" / "contracts" / "compiled_requirements.json")
    _wire_active_paths(monkeypatch, session_path, events_path)
    _set_pipeline_mode_bindings(monkeypatch, tmp_path)

    rc = entrypoint.main(["--quiet"])
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 0
    assert out["status"] == "ok"
    assert out["active_gate"] == "Implementation Review Complete"
    assert out["implementation_validation"]["is_compliant"] is True
    assert out["implementation_domain_changed_files"] == ["src/service.py"]


def test_happy_event_persists_binding_evidence(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    session_path = tmp_path / "SESSION_STATE.json"
    events_path = tmp_path / "events.jsonl"
    _write_session(session_path)
    _write_plan(tmp_path / "plan-record.json")
    _write_contracts(tmp_path / ".governance" / "contracts" / "compiled_requirements.json")
    _wire_active_paths(monkeypatch, session_path, events_path)
    monkeypatch.setenv("OPENCODE", "1")

    captured: list[dict[str, object]] = []

    def _spy_append_event(path: Path, event: dict[str, object]) -> bool:
        captured.append(dict(event))
        return True

    monkeypatch.setattr(entrypoint, "_append_event", _spy_append_event)

    rc = entrypoint.main(["--quiet"])
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 0
    assert out["status"] == "ok"
    started = [row for row in captured if row.get("event") == "IMPLEMENTATION_STARTED"]
    assert started
    assert started[-1]["pipeline_mode"] is False
    assert started[-1]["binding_role"] == "execution"
    assert started[-1]["binding_source"] == "active_chat_binding"
    assert started[-1]["binding_resolved"] is True
    assert started[-1]["invoke_backend_available"] is True


def test_bad_executor_no_changes_blocks(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    session_path = tmp_path / "SESSION_STATE.json"
    events_path = tmp_path / "events.jsonl"
    _write_session(session_path)
    _write_plan(tmp_path / "plan-record.json")
    _write_contracts(tmp_path / ".governance" / "contracts" / "compiled_requirements.json")
    _wire_active_paths(monkeypatch, session_path, events_path)
    _set_pipeline_mode_bindings(monkeypatch, tmp_path)

    monkeypatch.setattr(
        entrypoint,
        "_run_llm_edit_step",
        lambda **_kwargs: {
            "executor_invoked": True,
            "exit_code": 0,
            "stdout_path": "stdout.log",
            "stderr_path": "stderr.log",
            "changed_files": [],
            "reason_code": "",
            "message": "",
        },
    )

    rc = entrypoint.main(["--quiet"])
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 2
    assert out["status"] == "blocked"
    assert RC_NO_REPO_CHANGES in out["reason_codes"]


def test_corner_governance_only_changes_block(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    session_path = tmp_path / "SESSION_STATE.json"
    events_path = tmp_path / "events.jsonl"
    _write_session(session_path)
    _write_plan(tmp_path / "plan-record.json")
    _write_contracts(tmp_path / ".governance" / "contracts" / "compiled_requirements.json")
    _wire_active_paths(monkeypatch, session_path, events_path)
    _set_pipeline_mode_bindings(monkeypatch, tmp_path)

    monkeypatch.setattr(
        entrypoint,
        "_run_llm_edit_step",
        lambda **_kwargs: {
            "executor_invoked": True,
            "exit_code": 0,
            "stdout_path": "stdout.log",
            "stderr_path": "stderr.log",
            "changed_files": [".governance/implementation/llm_edit_context.json"],
            "reason_code": "",
            "message": "",
        },
    )

    rc = entrypoint.main(["--quiet"])
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 2
    assert out["status"] == "blocked"
    assert RC_GOVERNANCE_ONLY_CHANGES in out["reason_codes"]


def test_edge_missing_checks_blocks(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    session_path = tmp_path / "SESSION_STATE.json"
    events_path = tmp_path / "events.jsonl"
    _write_session(session_path)
    _write_plan(tmp_path / "plan-record.json")
    _write_contracts(tmp_path / ".governance" / "contracts" / "compiled_requirements.json")
    _wire_active_paths(monkeypatch, session_path, events_path)
    _set_pipeline_mode_bindings(monkeypatch, tmp_path)

    monkeypatch.setattr(entrypoint, "_run_targeted_checks", lambda _root, _reqs: ((), False))

    rc = entrypoint.main(["--quiet"])
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 2
    assert out["status"] == "blocked"
    assert RC_TARGETED_CHECKS_MISSING in out["reason_codes"]


def test_edge_failing_checks_blocks(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    session_path = tmp_path / "SESSION_STATE.json"
    events_path = tmp_path / "events.jsonl"
    _write_session(session_path)
    _write_plan(tmp_path / "plan-record.json")
    _write_contracts(tmp_path / ".governance" / "contracts" / "compiled_requirements.json")
    _wire_active_paths(monkeypatch, session_path, events_path)
    _set_pipeline_mode_bindings(monkeypatch, tmp_path)

    monkeypatch.setattr(
        entrypoint,
        "_run_targeted_checks",
        lambda _root, _reqs: (
            (
                entrypoint.CheckResult(
                    name="tests/test_service.py::test_happy",
                    passed=False,
                    exit_code=1,
                    output_path="checks.log",
                ),
            ),
            True,
        ),
    )

    rc = entrypoint.main(["--quiet"])
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 2
    assert out["status"] == "blocked"
    assert RC_TARGETED_CHECKS_FAILED in out["reason_codes"]


def test_happy_targeted_checks_fallback_runs_when_selectors_invalid(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "test_service.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    observed: list[list[str]] = []

    def _fake_run(command, **_kwargs):  # type: ignore[no-untyped-def]
        observed.append([str(token) for token in command])
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="1 passed\n", stderr="")

    monkeypatch.setattr(entrypoint.subprocess, "run", _fake_run)

    checks, declared = _ORIGINAL_RUN_TARGETED_CHECKS(
        tmp_path,
        [
            {
                "acceptance_tests": [
                    "tests/test_contract_missing_owner.py::test_missing_owner",
                ],
                "code_hotspots": ["src/service.py"],
            }
        ],
    )

    assert declared is True
    assert observed
    assert observed[-1][:4] == ["python3", "-m", "pytest", "-q"]
    assert observed[-1][-1] == "tests/test_service.py"
    assert checks
    assert checks[0].name == "tests/test_service.py"
    assert checks[0].passed is True


def test_happy_targeted_checks_ignore_invalid_selector_when_valid_exists(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    valid_file = tests_dir / "test_service.py"
    valid_file.write_text("def test_happy():\n    assert True\n", encoding="utf-8")
    valid_selector = "tests/test_service.py::test_happy"

    observed: list[list[str]] = []

    def _fake_run(command, **_kwargs):  # type: ignore[no-untyped-def]
        observed.append([str(token) for token in command])
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="1 passed\n", stderr="")

    monkeypatch.setattr(entrypoint.subprocess, "run", _fake_run)

    checks, declared = _ORIGINAL_RUN_TARGETED_CHECKS(
        tmp_path,
        [
            {
                "acceptance_tests": [
                    "tests/test_contract_missing_owner.py::test_missing_owner",
                    valid_selector,
                ],
                "code_hotspots": ["src/service.py"],
            }
        ],
    )

    assert declared is True
    assert observed
    assert observed[-1][:4] == ["python3", "-m", "pytest", "-q"]
    assert valid_selector in observed[-1]
    assert "tests/test_contract_missing_owner.py::test_missing_owner" not in observed[-1]
    assert [item.name for item in checks] == [valid_selector]
    assert checks[0].passed is True


def test_bad_phase_guard(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    session_path = tmp_path / "SESSION_STATE.json"
    events_path = tmp_path / "events.jsonl"
    _write_session(session_path, phase="5.4-BusinessRules")
    _write_plan(tmp_path / "plan-record.json")
    _write_contracts(tmp_path / ".governance" / "contracts" / "compiled_requirements.json")
    _wire_active_paths(monkeypatch, session_path, events_path)

    rc = entrypoint.main(["--quiet"])
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 2
    assert out["status"] == "error"


def test_bad_missing_required_contract_enforcement(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    session_path = tmp_path / "SESSION_STATE.json"
    events_path = tmp_path / "events.jsonl"
    _write_session(session_path)
    _write_plan(tmp_path / "plan-record.json")
    _write_contracts(tmp_path / ".governance" / "contracts" / "compiled_requirements.json")
    _wire_active_paths(monkeypatch, session_path, events_path)

    monkeypatch.setattr(
        entrypoint,
        "require_complete_contracts",
        lambda repo_root, required_ids: EnforcementResult(
            ok=False,
            reason=FAIL_CLOSED_MISSING_CONTRACT,
            details=("missing_required_contract:R-IMPLEMENT-001",),
        ),
    )

    rc = entrypoint.main(["--quiet"])
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 2
    assert out["status"] == "error"
    assert FAIL_CLOSED_MISSING_CONTRACT in out["message"]


def test_security_no_internal_domain_patch_helpers_exist() -> None:
    assert not hasattr(entrypoint, "_apply_target_file_patch")
    assert not hasattr(entrypoint, "_extract_literal_replacements")
    assert not hasattr(entrypoint, "_write_execution_code_artifact")


def test_security_local_writes_are_governance_or_state_only(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys,
) -> None:
    session_path = tmp_path / "SESSION_STATE.json"
    events_path = tmp_path / "events.jsonl"
    _write_session(session_path)
    _write_plan(tmp_path / "plan-record.json")
    _write_contracts(tmp_path / ".governance" / "contracts" / "compiled_requirements.json")
    _wire_active_paths(monkeypatch, session_path, events_path)

    writes: list[Path] = []
    text_writes: list[Path] = []
    json_writes: list[Path] = []
    event_writes: list[Path] = []

    real_write_json_atomic = entrypoint._write_json_atomic

    def _spy_write_json_atomic(path: Path, payload: dict[str, object]) -> None:
        json_writes.append(path)
        real_write_json_atomic(path, payload)

    def _spy_write_validation_report(path: Path, report) -> None:  # type: ignore[no-untyped-def]
        writes.append(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n", encoding="utf-8")

    real_write_text_atomic = entrypoint._write_text_atomic

    def _spy_write_text_atomic(path: Path, text: str) -> None:
        text_writes.append(path)
        real_write_text_atomic(path, text)

    def _spy_append_event(path: Path, event: dict[str, object]) -> bool:
        event_writes.append(path)
        return True

    monkeypatch.setattr(entrypoint, "_write_json_atomic", _spy_write_json_atomic)
    monkeypatch.setattr(entrypoint, "_write_text_atomic", _spy_write_text_atomic)
    monkeypatch.setattr(entrypoint, "write_validation_report", _spy_write_validation_report)
    monkeypatch.setattr(entrypoint, "_append_event", _spy_append_event)

    # Use the real executor-step implementation for this test so _write_text_atomic
    # coverage includes context/stdout/stderr local diagnostic writes.
    monkeypatch.setattr(entrypoint, "_run_llm_edit_step", _ORIGINAL_RUN_LLM_EDIT_STEP)
    monkeypatch.delenv("OPENCODE_IMPLEMENT_LLM_CMD", raising=False)
    monkeypatch.delenv("OPENCODE", raising=False)
    monkeypatch.delenv("OPENCODE_MODEL", raising=False)
    monkeypatch.delenv("OPENCODE_MODEL_PROVIDER", raising=False)

    rc = entrypoint.main(["--quiet"])
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 2
    assert out["status"] == "blocked"
    assert json_writes == [session_path]
    assert event_writes
    assert all(path == events_path for path in event_writes)
    if writes:
        assert len(writes) == 1
        report_path = writes[0]
        rel = report_path.relative_to(tmp_path).as_posix()
        assert rel.startswith(".governance/implementation/")
    if "active OpenCode chat binding is required in direct mode" in str(out.get("message") or ""):
        assert text_writes == []
    else:
        assert len(text_writes) >= 2
    for path in text_writes:
        rel_text = path.relative_to(tmp_path).as_posix()
        assert rel_text.startswith(".governance/implementation/")


def test_bad_desktop_llm_binding_without_callable_bridge_blocks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path
    monkeypatch.delenv("OPENCODE_IMPLEMENT_LLM_CMD", raising=False)
    monkeypatch.setenv("OPENCODE", "1")
    monkeypatch.setattr(entrypoint, "_resolve_desktop_executor_bridge_cmd", lambda **_kwargs: "")

    result = _ORIGINAL_RUN_LLM_EDIT_STEP(
        repo_root=repo_root,
        state={"phase": "6-PostFlight", "active_gate": "Workflow Complete"},
        ticket_text="t",
        task_text="task",
        plan_text="plan",
        required_hotspots=["src/service.py"],
    )

    assert result["executor_invoked"] is False
    assert result["exit_code"] == 2
    assert result["reason_code"] == entrypoint.RC_EXECUTOR_NOT_CONFIGURED
    assert result.get("blocked") is True
    assert result["changed_files"] == []


def test_happy_override_executor_precedence_over_desktop_default(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path
    monkeypatch.setenv("OPENCODE", "1")
    monkeypatch.setattr(entrypoint, "_parse_changed_files_from_git_status", lambda _repo: ["src/service.py"])

    observed: list[str] = []

    def _fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        observed.append(str(cmd))
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="ok\n", stderr="")

    monkeypatch.setattr(entrypoint.subprocess, "run", _fake_run)

    result = _ORIGINAL_RUN_LLM_EDIT_STEP(
        repo_root=repo_root,
        state={"phase": "6-PostFlight", "active_gate": "Workflow Complete"},
        ticket_text="t",
        task_text="task",
        plan_text="plan",
        required_hotspots=["src/service.py"],
        pipeline_mode=True,
        execution_binding="python3 -c \"print('override')\"",
    )

    assert observed
    assert any("python3 -c" in cmd for cmd in observed)
    assert any("override" in cmd for cmd in observed)
    assert result["executor_invoked"] is True
    assert result["exit_code"] == 0


def test_direct_mode_ignores_execution_env_binding_even_when_set(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path
    monkeypatch.setenv("OPENCODE", "1")
    monkeypatch.setenv("AI_GOVERNANCE_EXECUTION_BINDING", "python3 -c \"print('poison-env-binding')\"")
    monkeypatch.setenv("AI_GOVERNANCE_REVIEW_BINDING", "python3 -c \"print('unused-review')\"")
    monkeypatch.setattr(
        entrypoint,
        "_resolve_desktop_executor_bridge_cmd",
        lambda **_kwargs: "python3 -c \"print('{\\\"result\\\":\\\"ok\\\"}')\"",
    )
    monkeypatch.setattr(entrypoint, "_parse_changed_files_from_git_status", lambda _repo: [])

    observed: list[str] = []

    def _fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        observed.append(str(cmd))
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout='{"result":"ok"}\n', stderr="")

    monkeypatch.setattr(entrypoint.subprocess, "run", _fake_run)

    result = _ORIGINAL_RUN_LLM_EDIT_STEP(
        repo_root=repo_root,
        state={"phase": "6-PostFlight", "active_gate": "Workflow Complete"},
        ticket_text="t",
        task_text="task",
        plan_text="plan",
        required_hotspots=["src/service.py"],
        pipeline_mode=False,
    )

    assert observed
    assert "poison-env-binding" not in observed[0]
    assert "result" in str(result.get("message") or "") or result["exit_code"] == 0
    assert result["executor_invoked"] is True


def test_happy_desktop_binding_resolves_callable_bridge_executor(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path
    monkeypatch.delenv("OPENCODE_IMPLEMENT_LLM_CMD", raising=False)
    monkeypatch.setenv("OPENCODE", "1")
    monkeypatch.setattr(
        entrypoint,
        "_resolve_desktop_executor_bridge_cmd",
        lambda **_kwargs: "python3 -c \"print('{\\\"result\\\":\\\"ok\\\"}')\"",
    )
    states = iter([[], ["src/service.py"]])
    monkeypatch.setattr(entrypoint, "_parse_changed_files_from_git_status", lambda _repo: next(states))

    result = _ORIGINAL_RUN_LLM_EDIT_STEP(
        repo_root=repo_root,
        state={"phase": "6-PostFlight", "active_gate": "Workflow Complete"},
        ticket_text="t",
        task_text="task",
        plan_text="plan",
        required_hotspots=["src/service.py"],
    )

    assert result["executor_invoked"] is True
    assert result["exit_code"] == 0
    assert result["changed_files"] == ["src/service.py"]
    assert result.get("bridge_mode") is True


def test_bad_no_executor_binding_blocks_with_not_configured_reason(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path
    monkeypatch.delenv("OPENCODE_IMPLEMENT_LLM_CMD", raising=False)
    monkeypatch.delenv("OPENCODE", raising=False)
    monkeypatch.delenv("OPENCODE_MODEL", raising=False)
    monkeypatch.delenv("OPENCODE_MODEL_PROVIDER", raising=False)

    result = _ORIGINAL_RUN_LLM_EDIT_STEP(
        repo_root=repo_root,
        state={"phase": "6-PostFlight", "active_gate": "Workflow Complete"},
        ticket_text="t",
        task_text="task",
        plan_text="plan",
        required_hotspots=["src/service.py"],
    )

    assert result["executor_invoked"] is False
    assert result["reason_code"] == entrypoint.RC_EXECUTOR_NOT_CONFIGURED


def test_bad_mandate_schema_unavailable_blocks_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path
    monkeypatch.setattr(entrypoint, "_load_mandates_schema", lambda: None)

    result = _ORIGINAL_RUN_LLM_EDIT_STEP(
        repo_root=repo_root,
        state={"phase": "6-PostFlight", "active_gate": "Workflow Complete"},
        ticket_text="t",
        task_text="task",
        plan_text="plan",
        required_hotspots=["src/service.py"],
        pipeline_mode=True,
        execution_binding="python3 -c \"print('{\\\"result\\\":\\\"ok\\\"}')\"",
    )

    assert result.get("blocked") is True
    assert result.get("reason") == "mandate-schema-unavailable"
    assert result.get("reason_code") == "MANDATE-SCHEMA-UNAVAILABLE"


def test_edge_implement_start_with_desktop_binding_but_no_bridge_blocks_cleanly(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys,
) -> None:
    session_path = tmp_path / "SESSION_STATE.json"
    events_path = tmp_path / "events.jsonl"
    _write_session(session_path)
    _write_plan(tmp_path / "plan-record.json")
    _write_contracts(tmp_path / ".governance" / "contracts" / "compiled_requirements.json")
    _wire_active_paths(monkeypatch, session_path, events_path)

    monkeypatch.setattr(entrypoint, "_run_llm_edit_step", _ORIGINAL_RUN_LLM_EDIT_STEP)
    monkeypatch.setattr(entrypoint, "_resolve_desktop_executor_bridge_cmd", lambda **_kwargs: "")
    monkeypatch.setattr(entrypoint, "_load_effective_authoring_policy_text", lambda *args, **_kwargs: ("", ""))
    monkeypatch.delenv("OPENCODE_IMPLEMENT_LLM_CMD", raising=False)
    monkeypatch.setenv("OPENCODE", "1")

    rc = entrypoint.main(["--quiet"])
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 2
    assert out["status"] == "blocked"
    assert out["reason_code"] == entrypoint.RC_EXECUTOR_NOT_CONFIGURED
    assert out["reason_codes"] == [entrypoint.RC_EXECUTOR_NOT_CONFIGURED]
    assert out["binding_resolved"] is True
    assert out["invoke_backend_available"] is False
    assert out["implementation_validation"]["checks"] == []
    assert out["implementation_validation"]["plan_coverage"] == []


def test_bad_effective_authoring_policy_unavailable_blocks_with_executor(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path
    commands_home = tmp_path / "commands"
    commands_home.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("OPENCODE", "1")
    monkeypatch.delenv("OPENCODE_IMPLEMENT_LLM_CMD", raising=False)
    monkeypatch.setattr(
        entrypoint,
        "_load_effective_authoring_policy_text",
        lambda **_kwargs: ("", "BLOCKED-EFFECTIVE-POLICY-UNAVAILABLE"),
    )

    result = _ORIGINAL_RUN_LLM_EDIT_STEP(
        repo_root=repo_root,
        state={"phase": "6-PostFlight", "active_gate": "Workflow Complete"},
        ticket_text="t",
        task_text="task",
        plan_text="plan",
        required_hotspots=["src/service.py"],
        commands_home=commands_home,
    )

    assert result.get("blocked") is True
    assert result.get("reason") == "effective-policy-unavailable"
    assert result.get("reason_code") == "BLOCKED-EFFECTIVE-POLICY-UNAVAILABLE"


def test_happy_bridge_command_includes_model_and_context_placeholder(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cli_bin = tmp_path / "opencode-cli"
    cli_bin.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    cli_bin.chmod(0o755)
    monkeypatch.setenv("OPENCODE_CLI_BIN", str(cli_bin))
    monkeypatch.setattr(
        entrypoint,
        "resolve_active_opencode_model",
        lambda **_kwargs: {"provider": "openai", "model_id": "gpt-5.3-codex"},
    )

    cmd = entrypoint._resolve_desktop_executor_bridge_cmd(repo_root=tmp_path)
    assert "run --continue" in cmd
    assert "--format json" in cmd
    assert "--agent build" not in cmd
    assert "--model" in cmd
    assert "openai/gpt-5.3-codex" in cmd
    assert "{context_file}" in cmd


def test_bridge_mode_unsets_opencode_server_session_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path
    monkeypatch.setenv("OPENCODE", "1")
    monkeypatch.setenv("OPENCODE_CLIENT", "desktop")
    monkeypatch.setenv("OPENCODE_PID", "123")
    monkeypatch.setenv("OPENCODE_SERVER_USERNAME", "opencode")
    monkeypatch.setenv("OPENCODE_SERVER_PASSWORD", "secret")
    monkeypatch.setattr(
        entrypoint,
        "_resolve_desktop_executor_bridge_cmd",
        lambda **_kwargs: "python3 -c \"print('{\\\"result\\\":\\\"ok\\\"}')\"",
    )
    monkeypatch.setattr(entrypoint, "_parse_changed_files_from_git_status", lambda _repo: [])

    captured_env: dict[str, str] = {}

    def _fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        env = kwargs.get("env") or {}
        captured_env.update({str(k): str(v) for k, v in env.items()})
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout='{"result":"ok"}\n', stderr="")

    monkeypatch.setattr(entrypoint.subprocess, "run", _fake_run)

    result = _ORIGINAL_RUN_LLM_EDIT_STEP(
        repo_root=repo_root,
        state={"phase": "6-PostFlight", "active_gate": "Workflow Complete"},
        ticket_text="t",
        task_text="task",
        plan_text="plan",
        required_hotspots=[],
        pipeline_mode=False,
        execution_binding="",
    )

    assert result["executor_invoked"] is True
    assert "OPENCODE" not in captured_env
    assert "OPENCODE_CLIENT" not in captured_env
    assert "OPENCODE_PID" not in captured_env
    assert "OPENCODE_SERVER_USERNAME" not in captured_env
    assert "OPENCODE_SERVER_PASSWORD" not in captured_env


def test_bridge_command_reads_materialized_context_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path
    config_root = tmp_path / ".governance"
    config_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(entrypoint, "_parse_changed_files_from_git_status", lambda _repo: [])
    monkeypatch.setattr(entrypoint, "_capture_repo_change_baseline", lambda _repo: {"baseline": "ok"})

    execution_cmd = (
        "python3 -c \"import hashlib,json,sys; "
        "ctx=json.load(open(sys.argv[1], encoding='utf-8')); "
        "mandate_path=ctx.get('authoring_mandate_file',''); "
        "expected=ctx.get('authoring_mandate_sha256',''); "
        "content=open(mandate_path, encoding='utf-8').read(); "
        "actual=hashlib.sha256(content.encode('utf-8')).hexdigest(); "
        "assert actual==expected; "
        "print('{\\\"result\\\":\\\"ok\\\"}')\" {context_file}"
    )

    result = _ORIGINAL_RUN_LLM_EDIT_STEP(
        repo_root=repo_root,
        state={"phase": "6-PostFlight", "active_gate": "Workflow Complete"},
        ticket_text="t",
        task_text="task",
        plan_text="plan",
        required_hotspots=[],
        pipeline_mode=True,
        execution_binding=execution_cmd,
        config_root=config_root,
    )

    assert result["executor_invoked"] is True
    assert result["exit_code"] == 0


def test_happy_changed_files_use_executor_delta_not_preexisting_noise(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path
    execution_cmd = "python3 -c \"print('{\\\"result\\\":\\\"ok\\\"}')\""

    states = iter([
        ["docs/already_dirty.md"],
        ["docs/already_dirty.md", "src/service.py"],
    ])
    monkeypatch.setattr(entrypoint, "_parse_changed_files_from_git_status", lambda _repo: next(states))

    result = _ORIGINAL_RUN_LLM_EDIT_STEP(
        repo_root=repo_root,
        state={"phase": "6-PostFlight", "active_gate": "Workflow Complete"},
        ticket_text="t",
        task_text="task",
        plan_text="plan",
        required_hotspots=["src/service.py"],
        pipeline_mode=True,
        execution_binding=execution_cmd,
    )

    assert result["executor_invoked"] is True
    assert result["changed_files"] == ["src/service.py"]


def test_happy_hotspot_hash_delta_detects_real_change_on_preexisting_dirty_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path
    src = repo_root / "src"
    src.mkdir(parents=True, exist_ok=True)
    target = src / "service.py"
    target.write_text("before\n", encoding="utf-8")

    execution_cmd = (
        "python3 -c \"from pathlib import Path; "
        "Path('src/service.py').write_text('after\\n', encoding='utf-8'); "
        "print('{\\\"result\\\":\\\"ok\\\"}')\""
    )
    monkeypatch.setattr(
        entrypoint,
        "_parse_changed_files_from_git_status",
        lambda _repo: ["src/service.py"],
    )

    result = _ORIGINAL_RUN_LLM_EDIT_STEP(
        repo_root=repo_root,
        state={"phase": "6-PostFlight", "active_gate": "Workflow Complete"},
        ticket_text="t",
        task_text="task",
        plan_text="plan",
        required_hotspots=["src/service.py"],
        pipeline_mode=True,
        execution_binding=execution_cmd,
    )

    assert result["executor_invoked"] is True
    assert result["changed_files"] == ["src/service.py"]


def test_bad_approval_required_before_implement_start(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys,
) -> None:
    session_path = tmp_path / "SESSION_STATE.json"
    events_path = tmp_path / "events.jsonl"
    _write_session(session_path, decision="changes_requested")
    _write_plan(tmp_path / "plan-record.json")
    _write_contracts(tmp_path / ".governance" / "contracts" / "compiled_requirements.json")
    _wire_active_paths(monkeypatch, session_path, events_path)

    rc = entrypoint.main(["--quiet"])
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 2
    assert out["status"] == "error"
    assert "approved final review decision" in out["message"]


class TestImplementFlowTruthMatrix:
    def test_happy_main_implements_new_hotspot_file(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
        session_path = tmp_path / "SESSION_STATE.json"
        events_path = tmp_path / "events.jsonl"
        _write_session(session_path)
        _write_plan(tmp_path / "plan-record.json")
        payload = {
            "schema": "governance-compiled-requirements.v1",
            "requirements": [
                {
                    "id": "PLAN-STEP-001",
                    "title": "Create new service implementation",
                    "code_hotspots": ["src/new_service.py"],
                    "acceptance_tests": ["tests/test_service.py::test_happy"],
                }
            ],
        }
        contracts = tmp_path / ".governance" / "contracts" / "compiled_requirements.json"
        contracts.parent.mkdir(parents=True, exist_ok=True)
        contracts.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
        _wire_active_paths(monkeypatch, session_path, events_path)

        monkeypatch.setattr(entrypoint, "_run_llm_edit_step", _ORIGINAL_RUN_LLM_EDIT_STEP)
        monkeypatch.delenv("OPENCODE_IMPLEMENT_LLM_CMD", raising=False)
        monkeypatch.setenv("OPENCODE", "1")
        monkeypatch.setattr(entrypoint, "_load_effective_authoring_policy_text", lambda *args, **_kwargs: ("", ""))
        monkeypatch.setattr(
            entrypoint,
            "_resolve_desktop_executor_bridge_cmd",
            lambda **_kwargs: "python3 -c \"from pathlib import Path; Path('src').mkdir(exist_ok=True); Path('src/new_service.py').write_text('def run():\\n    return 1\\n', encoding='utf-8'); print('{\\\"result\\\":\\\"ok\\\"}')\"",
        )
        monkeypatch.setattr(entrypoint, "_parse_changed_files_from_git_status", lambda _repo: [])
        monkeypatch.setattr(
            entrypoint,
            "_run_targeted_checks",
            lambda _repo_root, _requirements: (
                (
                    entrypoint.CheckResult(
                        name="tests/test_service.py::test_happy",
                        passed=True,
                        exit_code=0,
                        output_path="checks.log",
                    ),
                ),
                True,
            ),
        )

        rc = entrypoint.main(["--quiet"])
        out = json.loads(capsys.readouterr().out.strip())

        assert rc == 0
        assert out["status"] == "ok"
        assert out["implementation_domain_changed_files"] == ["src/new_service.py"]
        assert (tmp_path / "src" / "new_service.py").exists()

    def test_bad_main_blocks_when_executor_fails(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
        session_path = tmp_path / "SESSION_STATE.json"
        events_path = tmp_path / "events.jsonl"
        _write_session(session_path)
        _write_plan(tmp_path / "plan-record.json")
        _write_contracts(tmp_path / ".governance" / "contracts" / "compiled_requirements.json")
        _wire_active_paths(monkeypatch, session_path, events_path)
        _set_pipeline_mode_bindings(monkeypatch, tmp_path)

        monkeypatch.setattr(
            entrypoint,
            "_run_llm_edit_step",
            lambda **_kwargs: {
                "executor_invoked": True,
                "exit_code": 2,
                "stdout_path": "stdout.log",
                "stderr_path": "stderr.log",
                "changed_files": ["src/service.py"],
                "reason_code": "",
                "message": "",
            },
        )

        rc = entrypoint.main(["--quiet"])
        out = json.loads(capsys.readouterr().out.strip())

        assert rc == 2
        assert out["status"] == "blocked"
        assert "IMPLEMENTATION_LLM_EXECUTOR_FAILED" in out["reason_codes"]

    def test_corner_main_blocks_when_targeted_checks_fail(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
        session_path = tmp_path / "SESSION_STATE.json"
        events_path = tmp_path / "events.jsonl"
        _write_session(session_path)
        _write_plan(tmp_path / "plan-record.json")
        _write_contracts(tmp_path / ".governance" / "contracts" / "compiled_requirements.json")
        _wire_active_paths(monkeypatch, session_path, events_path)
        _set_pipeline_mode_bindings(monkeypatch, tmp_path)

        monkeypatch.setattr(
            entrypoint,
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
            entrypoint,
            "_run_targeted_checks",
            lambda _repo_root, _requirements: (
                (
                    entrypoint.CheckResult(
                        name="tests/test_service.py::test_happy",
                        passed=False,
                        exit_code=1,
                        output_path="checks.log",
                    ),
                ),
                True,
            ),
        )

        rc = entrypoint.main(["--quiet"])
        out = json.loads(capsys.readouterr().out.strip())

        assert rc == 2
        assert out["status"] == "blocked"
        assert RC_TARGETED_CHECKS_FAILED in out["reason_codes"]

    def test_edge_main_blocks_when_hotspot_coverage_missing(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
        session_path = tmp_path / "SESSION_STATE.json"
        events_path = tmp_path / "events.jsonl"
        _write_session(session_path)
        _write_plan(tmp_path / "plan-record.json")
        _write_contracts(tmp_path / ".governance" / "contracts" / "compiled_requirements.json")
        _wire_active_paths(monkeypatch, session_path, events_path)
        _set_pipeline_mode_bindings(monkeypatch, tmp_path)

        monkeypatch.setattr(
            entrypoint,
            "_run_llm_edit_step",
            lambda **_kwargs: {
                "executor_invoked": True,
                "exit_code": 0,
                "stdout_path": "stdout.log",
                "stderr_path": "stderr.log",
                "changed_files": ["src/other.py"],
                "reason_code": "",
                "message": "",
            },
        )

        rc = entrypoint.main(["--quiet"])
        out = json.loads(capsys.readouterr().out.strip())

        assert rc == 2
        assert out["status"] == "blocked"
        assert "IMPLEMENTATION_PLAN_COVERAGE_MISSING" in out["reason_codes"]

def test_edge_main_surfaces_non_executor_precheck_reason(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys,
) -> None:
    session_path = tmp_path / "SESSION_STATE.json"
    events_path = tmp_path / "events.jsonl"
    _write_session(session_path)
    _write_plan(tmp_path / "plan-record.json")
    _write_contracts(tmp_path / ".governance" / "contracts" / "compiled_requirements.json")
    _wire_active_paths(monkeypatch, session_path, events_path)
    _set_pipeline_mode_bindings(monkeypatch, tmp_path)

    monkeypatch.setattr(
        entrypoint,
        "_run_llm_edit_step",
        lambda **_kwargs: {
            "blocked": True,
            "reason_code": "BLOCKED-EFFECTIVE-POLICY-UNAVAILABLE",
            "reason": "effective-policy-unavailable",
        },
    )

    rc = entrypoint.main(["--quiet"])
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 2
    assert out["status"] == "blocked"
    assert out["reason_code"] == "BLOCKED-EFFECTIVE-POLICY-UNAVAILABLE"


def test_happy_implementation_context_uses_canonical_task_and_plan_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys,
) -> None:
    session_path = tmp_path / "SESSION_STATE.json"
    events_path = tmp_path / "events.jsonl"
    payload = {
        "schema": "opencode-session-state.v1",
        "SESSION_STATE": {
            "phase": "6-PostFlight",
            "active_gate": "Workflow Complete",
            "workflow_complete": True,
            "WorkflowComplete": True,
            "UserReviewDecision": {"decision": "approve"},
            "requirement_contracts_present": True,
            "requirement_contracts_count": 1,
            "Ticket": "Ticket from legacy key",
            "task": "Task from canonical alias",
            "plan_record_versions": 1,
            "plan_record_status": "active",
            "phase5_plan_record_digest": "Approved plan fallback from state digest",
        },
    }
    session_path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
    _write_contracts(tmp_path / ".governance" / "contracts" / "compiled_requirements.json")
    _wire_active_paths(monkeypatch, session_path, events_path)
    _set_pipeline_mode_bindings(monkeypatch, tmp_path)

    captured: dict[str, object] = {}

    def _capture_context(**kwargs):  # type: ignore[no-untyped-def]
        captured.update(kwargs)
        return {
            "blocked": True,
            "reason_code": "BLOCKED-EFFECTIVE-POLICY-UNAVAILABLE",
            "reason": "effective-policy-unavailable",
        }

    monkeypatch.setattr(entrypoint, "_run_llm_edit_step", _capture_context)

    rc = entrypoint.main(["--quiet"])
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 2
    assert out["status"] == "blocked"
    assert captured["ticket_text"] == "Ticket from legacy key"
    assert captured["task_text"] == "Task from canonical alias"
    assert captured["plan_text"] == "Approved plan fallback from state digest"


def test_bad_precheck_event_persists_binding_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys,
) -> None:
    session_path = tmp_path / "SESSION_STATE.json"
    events_path = tmp_path / "events.jsonl"
    _write_session(session_path)
    _write_plan(tmp_path / "plan-record.json")
    _write_contracts(tmp_path / ".governance" / "contracts" / "compiled_requirements.json")
    _wire_active_paths(monkeypatch, session_path, events_path)
    monkeypatch.setenv("OPENCODE", "1")

    monkeypatch.setattr(
        entrypoint,
        "_run_llm_edit_step",
        lambda **_kwargs: {
            "blocked": True,
            "reason_code": "BLOCKED-EFFECTIVE-POLICY-UNAVAILABLE",
            "reason": "effective-policy-unavailable",
        },
    )

    captured: list[dict[str, object]] = []

    def _spy_append_event(path: Path, event: dict[str, object]) -> bool:
        captured.append(dict(event))
        return True

    monkeypatch.setattr(entrypoint, "_append_event", _spy_append_event)

    rc = entrypoint.main(["--quiet"])
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 2
    assert out["status"] == "blocked"
    precheck = [row for row in captured if row.get("event") == "IMPLEMENTATION_BLOCKED_PRECHECK"]
    assert precheck
    assert precheck[-1]["pipeline_mode"] is False
    assert precheck[-1]["binding_role"] == "execution"
    assert precheck[-1]["binding_source"] == "active_chat_binding"
    assert precheck[-1]["binding_resolved"] is True
    assert precheck[-1]["invoke_backend_available"] is True


def test_bad_pipeline_missing_binding_emits_resolution_vs_invoke_false_false(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys,
) -> None:
    session_path = tmp_path / "SESSION_STATE.json"
    events_path = tmp_path / "events.jsonl"
    _write_session(session_path)
    _write_plan(tmp_path / "plan-record.json")
    _write_contracts(tmp_path / ".governance" / "contracts" / "compiled_requirements.json")
    _wire_active_paths(monkeypatch, session_path, events_path)

    (tmp_path / "governance-config.json").write_text(
        json.dumps(
            {
                "pipeline_mode": True,
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

    rc = entrypoint.main(["--quiet"])
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 2
    assert out["status"] == "blocked"
    assert out["reason_code"] == entrypoint.RC_EXECUTOR_NOT_CONFIGURED
    assert out["binding_resolved"] is False
    assert out["invoke_backend_available"] is False


def test_edge_direct_mode_bridge_run_surfaces_selector_invalid_reason_codes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys,
) -> None:
    session_path = tmp_path / "SESSION_STATE.json"
    events_path = tmp_path / "events.jsonl"
    _write_session(session_path)
    _write_plan(tmp_path / "plan-record.json")

    payload = {
        "schema": "governance-compiled-requirements.v1",
        "requirements": [
            {
                "id": "PLAN-STEP-001",
                "title": "Update service behavior",
                "code_hotspots": ["src/service.py"],
                "acceptance_tests": ["tests/test_service.py::test_missing"],
            }
        ],
    }
    contracts = tmp_path / ".governance" / "contracts" / "compiled_requirements.json"
    contracts.parent.mkdir(parents=True, exist_ok=True)
    contracts.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")

    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "service.py").write_text("def run():\n    return 0\n", encoding="utf-8")

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    (tests_dir / "test_service.py").write_text("def test_existing():\n    assert True\n", encoding="utf-8")

    _wire_active_paths(monkeypatch, session_path, events_path)

    monkeypatch.setattr(entrypoint, "_run_llm_edit_step", _ORIGINAL_RUN_LLM_EDIT_STEP)
    monkeypatch.setattr(entrypoint, "_run_targeted_checks", _ORIGINAL_RUN_TARGETED_CHECKS)
    monkeypatch.setattr(entrypoint, "_load_effective_authoring_policy_text", lambda *args, **_kwargs: ("", ""))
    monkeypatch.setattr(
        entrypoint,
        "_resolve_desktop_executor_bridge_cmd",
        lambda **_kwargs: (
            "python3 -c \"from pathlib import Path; "
            "Path('src/service.py').write_text('def run():\\n    return 1\\n', encoding='utf-8'); "
            "print('{\\\"objective\\\":\\\"ok\\\"}')\""
        ),
    )
    monkeypatch.setattr(entrypoint, "_parse_changed_files_from_git_status", lambda _repo: [])
    monkeypatch.setenv("OPENCODE", "1")
    monkeypatch.setenv("OPENCODE_CLIENT", "desktop")
    monkeypatch.setenv("OPENCODE_PID", "4242")
    monkeypatch.setenv("OPENCODE_SERVER_USERNAME", "opencode")
    monkeypatch.setenv("OPENCODE_SERVER_PASSWORD", "secret")

    rc = entrypoint.main(["--quiet"])
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 2
    assert out["status"] == "blocked"
    assert out["reason_code"] == RC_CHECK_SELECTOR_INVALID
    assert out["reason_codes"] == [RC_CHECK_SELECTOR_INVALID, RC_TARGETED_CHECKS_FAILED]
    assert out["active_gate"] == "Implementation Blocked"
    assert out["next_gate_condition"].startswith("Implementation validation failed.")


def test_workspace_authority_prefers_active_session_workspace_for_binding_resolution(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys,
) -> None:
    session_path = tmp_path / "SESSION_STATE.json"
    events_path = tmp_path / "events.jsonl"
    _write_session(session_path)
    _write_plan(tmp_path / "plan-record.json")
    _write_contracts(tmp_path / ".governance" / "contracts" / "compiled_requirements.json")
    _wire_active_paths(monkeypatch, session_path, events_path)
    _set_pipeline_mode_bindings(monkeypatch, tmp_path)

    foreign_workspace = tmp_path / "foreign-workspace"
    foreign_workspace.mkdir(parents=True, exist_ok=True)
    foreign_session = foreign_workspace / "SESSION_STATE.json"
    foreign_session.write_text("{}\n", encoding="utf-8")

    monkeypatch.setattr(
        entrypoint,
        "resolve_active_session_paths",
        lambda: (foreign_session, "fp", tmp_path.parent, foreign_workspace),
    )

    observed: dict[str, object] = {}

    def _fake_resolve_governance_binding(**kwargs):  # type: ignore[no-untyped-def]
        observed["workspace_root"] = kwargs.get("workspace_root")
        return type(
            "Binding",
            (),
            {
                "binding_value": "mock-executor",
                "source": "env:AI_GOVERNANCE_EXECUTION_BINDING",
            },
        )()

    monkeypatch.setattr(entrypoint, "resolve_governance_binding", _fake_resolve_governance_binding)
    monkeypatch.setattr(
        entrypoint,
        "_run_llm_edit_step",
        lambda **_kwargs: {
            "blocked": True,
            "reason_code": "BLOCKED-EFFECTIVE-POLICY-UNAVAILABLE",
            "reason": "effective-policy-unavailable",
            "binding_resolved": True,
            "invoke_backend_available": True,
        },
    )

    rc = entrypoint.main(["--quiet"])
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 2
    assert out["status"] == "blocked"
    assert observed["workspace_root"] == tmp_path
