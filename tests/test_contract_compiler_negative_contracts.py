from __future__ import annotations

from governance.contracts.compiler import compile_plan_to_requirements


def test_compiler_emits_negative_contracts() -> None:
    compiled = compile_plan_to_requirements(plan_text="- exactly one next action\n- no yaml in normal mode")
    assert compiled.requirements
    assert compiled.negative_contracts
    assert len(compiled.negative_contracts) == len(compiled.requirements)
    assert all(item.get("blocking") is True for item in compiled.negative_contracts)
