from __future__ import annotations

import json
from pathlib import Path

import pytest

from governance.contracts.enforcement import FAIL_CLOSED_MISSING_CONTRACT, EnforcementResult
from governance.entrypoints import implement_start as entrypoint
from governance.engine.implementation_validation import (
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
            "Phase": phase,
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

    rc = entrypoint.main(["--quiet"])
    out = json.loads(capsys.readouterr().out.strip())

    assert rc == 2
    assert out["status"] == "blocked"
    assert json_writes == [session_path]
    assert event_writes == [events_path]
    assert len(writes) == 1
    report_path = writes[0]
    rel = report_path.relative_to(tmp_path).as_posix()
    assert rel.startswith(".governance/implementation/")
    assert len(text_writes) >= 3
    for path in text_writes:
        rel_text = path.relative_to(tmp_path).as_posix()
        assert rel_text.startswith(".governance/implementation/")
