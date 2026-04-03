from __future__ import annotations

from governance_runtime.contracts.compiler import compile_plan_to_requirements


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


def test_compiler_strict_machine_source_fail_closed_when_missing() -> None:
    compiled = compile_plan_to_requirements(
        plan_text="- implement gate flow",
        strict_source="machine_requirements",
    )
    assert compiled.requirements == ()
    assert "strict_source_missing" in compiled.notes


def test_compiler_uses_machine_requirements_as_only_authority_when_provided() -> None:
    compiled = compile_plan_to_requirements(
        plan_text="- Decision required: choose approve, changes_requested, or reject.",
        machine_requirements=[
            {
                "title": "Implement pipeline happy-path e2e",
                "kind": "required_behavior",
                "required_behavior": "Implement: pipeline happy-path e2e",
                "forbidden_behavior": "forbid state: pipeline happy-path e2e not satisfied",
                "code_hotspots": ["tests/test_governance_binding_e2e_flow.py"],
                "verification_methods": ["behavioral_verification", "static_verification"],
                "acceptance_tests": [
                    "tests/test_governance_binding_e2e_flow.py::test_happy_path"
                ],
            }
        ],
        strict_source="machine_requirements",
    )
    assert len(compiled.requirements) == 1
    item = compiled.requirements[0]
    assert item["title"] == "Implement pipeline happy-path e2e"
    assert item["acceptance_tests"] == ["tests/test_governance_binding_e2e_flow.py::test_happy_path"]
    assert "source=machine_requirements" in compiled.notes
