from kernel.domain.models.session_state import CommitFlags, SessionState


def test_session_state_defaults() -> None:
    state = SessionState(repo_fingerprint="abc123", phase="1.1-Bootstrap", mode="BLOCKED")
    assert isinstance(state.flags, CommitFlags)
