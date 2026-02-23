from governance.domain.policies.gate_policy import rulebook_gate


def test_rulebook_gate_target_phase_placeholder() -> None:
    result = rulebook_gate(target_phase="4.1", loaded_rulebooks={"core": "x"})
    assert result.ok is False
