import pytest
from governance.application.use_cases.bootstrap_persistence import _session_state_payload


def test_bootstrap_payload_pointer_verified_true_golden():
    state = _session_state_payload(
        repo_fingerprint="abcdef0123456789abcdef01",
        repo_name="myrepo",
        persistence_committed=True,
        workspace_ready_committed=True,
        workspace_artifacts_committed=True,
        effective_mode="user",
        write_policy_reasons=(),
        pointer_verified=True,
    )
    s = state["SESSION_STATE"]
    assert s["Phase"] == "1.2-Architecture"
    assert s["Mode"] == "IN_PROGRESS"
    assert s["Next"] == "P5-Architecture-in_progress"
    assert s["Bootstrap"]["Present"] is True
    assert s["Bootstrap"]["Satisfied"] is True
    assert s["Bootstrap"]["Evidence"] == "bootstrap-completed"
    assert s["CommitFlags"]["PointerVerified"] is True


def test_bootstrap_payload_not_satisfied_initial_block():
    state = _session_state_payload(
        repo_fingerprint="abcdef0123456789abcdef01",
        repo_name="myrepo",
        persistence_committed=False,
        workspace_ready_committed=False,
        workspace_artifacts_committed=False,
        effective_mode="user",
        write_policy_reasons=(),
        pointer_verified=False,
    )
    s = state["SESSION_STATE"]
    assert s["Phase"] == "1.1-Bootstrap"
    assert s["Mode"] == "BLOCKED"
    assert s["Next"] == "BLOCKED-START-REQUIRED"
    assert s["Bootstrap"]["Present"] is False
    assert s["Bootstrap"]["Satisfied"] is False
    assert s["Bootstrap"]["Evidence"] == "not-initialized"
    assert s["CommitFlags"]["PointerVerified"] is False
