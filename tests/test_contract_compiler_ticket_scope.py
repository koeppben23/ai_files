from __future__ import annotations

from governance.contracts.compiler import compile_plan_to_requirements


def test_happy_compiler_prefers_ticket_scope_over_governance_meta_plan() -> None:
    compiled = compile_plan_to_requirements(
        plan_text="- decision semantics\n- state-machine\n",
        ticket_text="- Move archived runs to workspaces/governance-records/<fp>/runs",
    )
    assert compiled.requirements
    titles = [str(item.get("title") or "") for item in compiled.requirements]
    assert any("archived runs" in title.lower() for title in titles)


def test_bad_compiler_falls_back_to_plan_when_only_legacy_meta_available() -> None:
    compiled = compile_plan_to_requirements(plan_text="- implement gate flow")
    assert compiled.requirements
