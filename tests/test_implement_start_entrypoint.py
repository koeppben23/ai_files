from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from governance_runtime.contracts.enforcement import FAIL_CLOSED_MISSING_CONTRACT, EnforcementResult
from governance_runtime.entrypoints import implement_start as entrypoint
from governance_runtime.engine.implementation_validation import (
    RC_GOVERNANCE_ONLY_CHANGES,
    RC_NO_REPO_CHANGES,
    RC_TARGETED_CHECKS_FAILED,
    RC_TARGETED_CHECKS_MISSING,
)

_ORIGINAL_RUN_LLM_EDIT_STEP = entrypoint._run_llm_edit_step


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


def test_happy_executor_diff_plus_checks_passes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    session_path = tmp_path / "SESSION_STATE.json"
    events_path = tmp_path / "events.jsonl"
    _write_session(session_path)
    _write_plan(tmp_path / "plan-record.json")
    _write_contracts(tmp_path / ".governance" / "contracts" / "compiled_requirements.json")
    _wire_active_paths(monkeypatch, session_path, events_path)

    rc = entrypoint.main(["--quiet"])
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 0
    assert out["status"] == "ok"
    assert out["active_gate"] == "Implementation Review Complete"
    assert out["implementation_validation"]["is_compliant"] is True
    assert out["implementation_domain_changed_files"] == ["src/service.py"]


def test_bad_executor_no_changes_blocks(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
    session_path = tmp_path / "SESSION_STATE.json"
    events_path = tmp_path / "events.jsonl"
    _write_session(session_path)
    _write_plan(tmp_path / "plan-record.json")
    _write_contracts(tmp_path / ".governance" / "contracts" / "compiled_requirements.json")
    _wire_active_paths(monkeypatch, session_path, events_path)

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
    assert event_writes == [events_path]
    if writes:
        assert len(writes) == 1
        report_path = writes[0]
        rel = report_path.relative_to(tmp_path).as_posix()
        assert rel.startswith(".governance/implementation/")
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
    assert "python3 -c" in observed[0]
    assert result["executor_invoked"] is True
    assert result["exit_code"] == 0


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
    assert "--model" in cmd
    assert "openai/gpt-5.3-codex" in cmd
    assert "{context_file}" in cmd


def test_happy_changed_files_use_executor_delta_not_preexisting_noise(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo_root = tmp_path
    monkeypatch.setenv("OPENCODE_IMPLEMENT_LLM_CMD", "python3 -c \"print('{\\\"result\\\":\\\"ok\\\"}')\"")

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

    def test_edge_main_surfaces_non_executor_precheck_reason(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys) -> None:
        session_path = tmp_path / "SESSION_STATE.json"
        events_path = tmp_path / "events.jsonl"
        _write_session(session_path)
        _write_plan(tmp_path / "plan-record.json")
        _write_contracts(tmp_path / ".governance" / "contracts" / "compiled_requirements.json")
        _wire_active_paths(monkeypatch, session_path, events_path)

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
