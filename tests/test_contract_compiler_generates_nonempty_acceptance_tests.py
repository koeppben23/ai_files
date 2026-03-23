from __future__ import annotations

from governance_runtime.contracts.compiler import compile_plan_to_requirements


def test_compiler_generates_nonempty_acceptance_tests() -> None:
    compiled = compile_plan_to_requirements(plan_text="- render review object")
    assert compiled.requirements
    assert all(isinstance(item.get("acceptance_tests"), list) and item.get("acceptance_tests") for item in compiled.requirements)
