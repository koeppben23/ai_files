from __future__ import annotations

from governance_runtime.verification.builder_contract import validate_builder_result


def test_builder_contract_happy_path() -> None:
    result = validate_builder_result(
        {
            "changed_files": ["governance_runtime/entrypoints/session_reader.py"],
            "contracts_addressed": ["R-NEXT-ACTION-001"],
            "tests_added": ["tests/test_session_reader_guided_contract.py::test_guided_happy"],
            "contracts_unverified": [],
        }
    )
    assert result.ok is True
    assert result.errors == ()


def test_builder_contract_bad_unknown_keys_rejected() -> None:
    result = validate_builder_result({"status": "done"})
    assert result.ok is False
    assert any("unknown_keys" in err for err in result.errors)


def test_builder_contract_corner_banned_phrase_rejected() -> None:
    result = validate_builder_result(
        {
            "changed_files": ["core logic is there"],
            "contracts_addressed": [],
            "tests_added": [],
            "contracts_unverified": [],
        }
    )
    assert result.ok is False
    assert any("contains_banned_phrase" in err for err in result.errors)


def test_builder_contract_edge_requires_lists() -> None:
    result = validate_builder_result(
        {
            "changed_files": "x.py",
            "contracts_addressed": [],
            "tests_added": [],
            "contracts_unverified": [],
        }
    )
    assert result.ok is False
    assert any("changed_files:must_be_list" in err for err in result.errors)
