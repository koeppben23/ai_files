from governance.domain.policies.write_policy import compute_write_policy


def test_force_read_only_blocks_writes() -> None:
    policy = compute_write_policy(force_read_only=True)
    assert policy.writes_allowed is False


def test_default_policy_allows_writes() -> None:
    policy = compute_write_policy(force_read_only=False)
    assert policy.writes_allowed is True
