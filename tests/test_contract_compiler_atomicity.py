from __future__ import annotations

from governance_runtime.contracts.compiler import compile_plan_to_requirements


def test_compiler_atomicity_separates_independent_statements() -> None:
    compiled = compile_plan_to_requirements(
        plan_text="- exactly one next action\n- no recovery action in happy path\n- no yaml in normal mode"
    )
    titles = [str(item.get("title")) for item in compiled.requirements]
    assert len(titles) == 3
    assert any("next action" in title.lower() for title in titles)
    assert any("recovery" in title.lower() for title in titles)
    assert any("yaml" in title.lower() for title in titles)
