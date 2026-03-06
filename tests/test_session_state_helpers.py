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
        spec_loaded_at="2026-02-24T19:00:00+00:00",
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
    assert kernel["PhaseApiLoadedAt"] == "2026-02-24T19:00:00+00:00"
    assert kernel["LastPhaseEventId"] == "evt-1"


def test_with_kernel_result_clamps_phase5_iteration_to_max() -> None:
    updated = with_kernel_result(
        {
            "SESSION_STATE": {
                "Phase5Review": {
                    "iteration": 9,
                    "max_iterations": 3,
                }
            }
        },
        phase="5-ArchitectureReview",
        next_token="5",
        active_gate="Architecture Review Gate",
        next_gate_condition="Continue",
        status="OK",
        spec_hash="deadbeef",
        spec_path="/tmp/commands/phase_api.yaml",
        spec_loaded_at="2026-02-24T19:00:00+00:00",
        log_paths={},
        event_id="evt-2",
    )
    state = updated["SESSION_STATE"]
    assert isinstance(state, dict)
    phase5_review = state["Phase5Review"]
    assert isinstance(phase5_review, dict)
    assert phase5_review["iteration"] == 3
    assert phase5_review["max_iterations"] == 3


def test_with_kernel_result_clamps_implementation_iteration_to_max() -> None:
    updated = with_kernel_result(
        {
            "SESSION_STATE": {
                "ImplementationReview": {
                    "iteration": 7,
                    "max_iterations": 2,
                }
            }
        },
        phase="6-PostFlight",
        next_token="6",
        active_gate="Implementation Internal Review",
        next_gate_condition="Continue",
        status="OK",
        spec_hash="deadbeef",
        spec_path="/tmp/commands/phase_api.yaml",
        spec_loaded_at="2026-02-24T19:00:00+00:00",
        log_paths={},
        event_id="evt-3",
    )
    state = updated["SESSION_STATE"]
    assert isinstance(state, dict)
    impl_review = state["ImplementationReview"]
    assert isinstance(impl_review, dict)
    assert impl_review["iteration"] == 2
    assert impl_review["max_iterations"] == 2


def test_with_kernel_result_writes_plan_record_gate_materialization_fields() -> None:
    updated = with_kernel_result(
        {"SESSION_STATE": {}},
        phase="5-ArchitectureReview",
        next_token="5",
        active_gate="Architecture Review Gate",
        next_gate_condition="Continue self-review loop",
        status="OK",
        spec_hash="deadbeef",
        spec_path="/tmp/commands/phase_api.yaml",
        spec_loaded_at="2026-02-24T19:00:00+00:00",
        log_paths={},
        event_id="evt-4",
        plan_record_status="active",
        plan_record_versions=1,
    )
    state = updated["SESSION_STATE"]
    assert isinstance(state, dict)
    assert state["plan_record_status"] == "active"
    assert state["PlanRecordStatus"] == "active"
    assert state["plan_record_versions"] == 1
    assert state["PlanRecordVersions"] == 1
