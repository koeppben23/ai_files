from __future__ import annotations

from pathlib import Path

from governance_runtime.contracts.registry import load_and_validate_contracts


def test_seed_requirements_validate_happy_path() -> None:
    root = Path(__file__).resolve().parents[1]
    loaded = load_and_validate_contracts(root)
    assert loaded.contracts
    assert loaded.validation.ok is True, loaded.validation.errors


def test_r_next_action_001_owner() -> None:
    root = Path(__file__).resolve().parents[1]
    loaded = load_and_validate_contracts(root)
    target = next(c for c in loaded.contracts if c.get("id") == "R-NEXT-ACTION-001")
    assert target["owner_test"] == "tests/test_contract_seed_requirements.py::test_r_next_action_001_owner"


def test_r_output_001_owner() -> None:
    root = Path(__file__).resolve().parents[1]
    loaded = load_and_validate_contracts(root)
    target = next(c for c in loaded.contracts if c.get("id") == "R-OUTPUT-001")
    assert target["owner_test"] == "tests/test_contract_seed_requirements.py::test_r_output_001_owner"


def test_r_review_decision_001_owner() -> None:
    root = Path(__file__).resolve().parents[1]
    loaded = load_and_validate_contracts(root)
    target = next(c for c in loaded.contracts if c.get("id") == "R-REVIEW-DECISION-001")
    assert target["owner_test"] == "tests/test_contract_seed_requirements.py::test_r_review_decision_001_owner"


def test_r_implement_001_owner() -> None:
    root = Path(__file__).resolve().parents[1]
    loaded = load_and_validate_contracts(root)
    target = next(c for c in loaded.contracts if c.get("id") == "R-IMPLEMENT-001")
    assert target["owner_test"] == "tests/test_contract_seed_requirements.py::test_r_implement_001_owner"


def test_r_completion_001_owner() -> None:
    root = Path(__file__).resolve().parents[1]
    loaded = load_and_validate_contracts(root)
    target = next(c for c in loaded.contracts if c.get("id") == "R-COMPLETION-001")
    assert target["owner_test"] == "tests/test_contract_seed_requirements.py::test_r_completion_001_owner"


def test_r_merge_policy_001_owner() -> None:
    root = Path(__file__).resolve().parents[1]
    loaded = load_and_validate_contracts(root)
    target = next(c for c in loaded.contracts if c.get("id") == "R-MERGE-POLICY-001")
    assert target["owner_test"] == "tests/test_contract_seed_requirements.py::test_r_merge_policy_001_owner"


def test_r_review_pr_001_owner() -> None:
    root = Path(__file__).resolve().parents[1]
    loaded = load_and_validate_contracts(root)
    target = next(c for c in loaded.contracts if c.get("id") == "R-REVIEW-PR-001")
    assert target["owner_test"] == "tests/test_contract_seed_requirements.py::test_r_review_pr_001_owner"
