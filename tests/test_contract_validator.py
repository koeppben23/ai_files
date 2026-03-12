from __future__ import annotations

from governance.contracts.validator import validate_requirement_contracts


def _base_contract(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": "R-TEST-001",
        "title": "Test requirement",
        "criticality": "release_blocking",
        "owner_test": "tests/test_x.py::test_owner",
        "live_proof_key": "LP-TEST-001",
        "required_behavior": ["must do x"],
        "forbidden_behavior": ["must not do y decision"],
        "user_visible_expectation": ["user sees x"],
        "state_expectation": ["state_x=true"],
        "code_hotspots": ["governance/entrypoints/session_reader.py"],
        "verification_methods": [
            "static_verification",
            "behavioral_verification",
            "user_surface_verification",
            "live_flow_verification",
            "receipts_verification",
        ],
        "acceptance_tests": ["tests/test_x.py::test_owner"],
        "done_rule": {
            "require_all_verifications_pass": True,
            "fail_closed_on_missing_evidence": True,
            "fail_on_forbidden_observation": True,
        },
    }
    payload.update(overrides)
    return payload


def test_validate_contracts_happy_path() -> None:
    result = validate_requirement_contracts([_base_contract()])
    assert result.ok is True
    assert result.errors == ()


def test_validate_contracts_bad_missing_acceptance_tests() -> None:
    result = validate_requirement_contracts([_base_contract(acceptance_tests=[])])
    assert result.ok is False
    assert any("invalid_non_empty_string_list:acceptance_tests" in err for err in result.errors)


def test_validate_contracts_corner_release_blocking_requires_live_flow() -> None:
    contract = _base_contract(
        verification_methods=[
            "static_verification",
            "behavioral_verification",
            "user_surface_verification",
            "receipts_verification",
        ]
    )
    result = validate_requirement_contracts([contract])
    assert result.ok is False
    assert any("release_blocking_requires_live_flow_verification" in err for err in result.errors)


def test_validate_contracts_edge_repo_wide_uniqueness_enforced() -> None:
    one = _base_contract(id="R-TEST-001", owner_test="tests/test_a.py::test_x", live_proof_key="LP-A")
    two = _base_contract(id="R-TEST-002", owner_test="tests/test_a.py::test_x", live_proof_key="LP-B")
    three = _base_contract(id="R-TEST-003", owner_test="tests/test_c.py::test_z", live_proof_key="LP-B")
    result = validate_requirement_contracts([one, two, three])
    assert result.ok is False
    assert any("duplicate_owner_test_repo_wide" in err for err in result.errors)
    assert any("duplicate_live_proof_key_repo_wide" in err for err in result.errors)
