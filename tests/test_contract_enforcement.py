from __future__ import annotations

from pathlib import Path

from governance_runtime.contracts.enforcement import FAIL_CLOSED_MISSING_CONTRACT, require_complete_contracts


def test_contract_enforcement_happy_repo_contracts_present() -> None:
    root = Path(__file__).resolve().parents[1]
    result = require_complete_contracts(repo_root=root, required_ids=("R-IMPLEMENT-001",))
    assert result.ok is True
    assert result.reason == "ready"


def test_contract_enforcement_bad_missing_required_scope() -> None:
    root = Path(__file__).resolve().parents[1]
    result = require_complete_contracts(repo_root=root, required_ids=("R-DOES-NOT-EXIST-999",))
    assert result.ok is False
    assert result.reason == FAIL_CLOSED_MISSING_CONTRACT
    assert any("missing_required_contract" in item for item in result.details)
