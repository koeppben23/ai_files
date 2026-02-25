from typing import Any, cast
from governance.application.use_cases.bootstrap_persistence import _is_valid_pointer_payload, _session_state_payload


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
        activation_intent_valid=True,
    )
    s = cast(dict[str, Any], state["SESSION_STATE"])
    assert s["Phase"] == "1.2-ActivationIntent"
    assert s["Mode"] == "IN_PROGRESS"
    assert s["Next"] == "1.3"
    assert s["ActivationIntent"]["Status"] == "valid"
    assert s["Intent"]["Path"] == ""
    assert s["Intent"]["Sha256"] == ""
    assert s["Intent"]["EffectiveScope"] == "unknown"
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
    s = cast(dict[str, Any], state["SESSION_STATE"])
    assert s["Phase"] == "1.1-Bootstrap"
    assert s["Mode"] == "BLOCKED"
    assert s["Next"] == "BLOCKED-START-REQUIRED"
    assert s["Bootstrap"]["Present"] is False
    assert s["Bootstrap"]["Satisfied"] is False
    assert s["Bootstrap"]["Evidence"] == "not-initialized"
    assert s["CommitFlags"]["PointerVerified"] is False


def test_pointer_payload_validation() -> None:
    valid = {
        "schema": "opencode-session-pointer.v1",
        "activeRepoFingerprint": "abcdef0123456789abcdef01",
        "activeSessionStateFile": "/tmp/session.json",
    }
    relative_only = {
        "schema": "opencode-session-pointer.v1",
        "activeRepoFingerprint": "abcdef0123456789abcdef01",
        "activeSessionStateRelativePath": "workspaces/abcdef0123456789abcdef01/SESSION_STATE.json",
    }
    invalid = {
        "schema": "opencode-session-pointer.v1",
        "activeRepoFingerprint": "wrong",
        "activeSessionStateFile": "/tmp/session.json",
    }
    assert _is_valid_pointer_payload(
        valid,
        expected_repo_fingerprint="abcdef0123456789abcdef01",
        expected_session_state_file="/tmp/session.json",
    ) is True
    assert _is_valid_pointer_payload(
        relative_only,
        expected_repo_fingerprint="abcdef0123456789abcdef01",
        expected_session_state_file="/tmp/session.json",
    ) is False
    assert _is_valid_pointer_payload(
        invalid,
        expected_repo_fingerprint="abcdef0123456789abcdef01",
        expected_session_state_file="/tmp/session.json",
    ) is False
