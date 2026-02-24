from __future__ import annotations

from governance.application.use_cases.session_state_helpers import with_kernel_result


def test_with_kernel_result_writes_session_state_kernel_block() -> None:
    updated = with_kernel_result(
        {"SESSION_STATE": {"RepoFingerprint": "abc"}},
        phase="3A-API-Inventory",
        next_token="3B-1",
        active_gate="API Inventory",
        next_gate_condition="Proceed",
        status="OK",
        spec_hash="deadbeef",
        spec_path="/tmp/commands/phase_api.yaml",
        log_paths={"phase_flow": "/tmp/commands/logs/flow.log.jsonl"},
        event_id="evt-1",
    )
    state = updated["SESSION_STATE"]
    assert isinstance(state, dict)
    assert state["Phase"] == "3A-API-Inventory"
    assert state["Next"] == "3B-1"
    assert state["status"] == "OK"
    assert state["log_paths"] == {"phase_flow": "/tmp/commands/logs/flow.log.jsonl"}
    kernel = state["Kernel"]
    assert isinstance(kernel, dict)
    assert kernel["PhaseApiSha256"] == "deadbeef"
    assert kernel["LastPhaseEventId"] == "evt-1"
