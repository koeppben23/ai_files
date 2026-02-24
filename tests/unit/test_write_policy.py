from governance.domain.policies.write_policy import compute_write_policy


def test_force_read_only_blocks_writes() -> None:
    policy = compute_write_policy(force_read_only=True, mode="pipeline")
    assert policy.writes_allowed is False
    assert policy.reason == "force-read-only"
    assert policy.mode == "pipeline"


def test_default_policy_allows_writes() -> None:
    policy = compute_write_policy(force_read_only=False, mode="user")
    assert policy.writes_allowed is True
    assert policy.reason == "explicit-user-mode-allow"


def test_default_policy_allows_pipeline_mode() -> None:
    policy = compute_write_policy(force_read_only=False, mode="pipeline")
    assert policy.writes_allowed is True
    assert policy.reason == "explicit-pipeline-mode-allow"
