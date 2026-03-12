from __future__ import annotations

from pathlib import Path

from governance.contracts.compiler import compile_plan_to_requirements
from governance.contracts.registry import discover_requirement_contract_files, load_and_validate_contracts


def test_compiler_happy_generates_atomic_requirements() -> None:
    result = compile_plan_to_requirements(plan_text="- first\n- second", scope_prefix="SEED")
    assert len(result.requirements) == 2
    assert result.requirements[0]["id"].startswith("R-SEED-001")


def test_compiler_bad_empty_plan_returns_note() -> None:
    result = compile_plan_to_requirements(plan_text="  ")
    assert result.requirements == ()
    assert "empty_plan_text" in result.notes


def test_registry_corner_discovers_seed_files() -> None:
    root = Path(__file__).resolve().parents[1]
    files = discover_requirement_contract_files(root)
    assert files
    assert any(path.name == "R-NEXT-ACTION-001.json" for path in files)


def test_registry_edge_load_and_validate_returns_valid_set() -> None:
    root = Path(__file__).resolve().parents[1]
    loaded = load_and_validate_contracts(root)
    assert loaded.contracts
    assert loaded.validation.ok is True, loaded.validation.errors
