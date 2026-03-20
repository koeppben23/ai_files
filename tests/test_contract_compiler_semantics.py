from __future__ import annotations

from governance_runtime.contracts.compiler import compile_plan_to_requirements


def test_compiler_groups_lines_into_semantic_segments() -> None:
    compiled = compile_plan_to_requirements(
        plan_text=(
            "# Required behavior\n"
            "- render guided output\n"
            "- no yaml in normal mode\n"
            "- persist presentation receipt"
        )
    )
    assert compiled.requirements
    assert "segments=3" in compiled.notes
    assert any(note.startswith("forbidden_behavior=") for note in compiled.notes)


def test_compiler_splits_independent_behaviors_into_atomic_requirements() -> None:
    compiled = compile_plan_to_requirements(
        plan_text="- exactly one next action\n- no recovery action in happy path\n- no yaml in normal mode"
    )
    titles = [str(item.get("title") or "") for item in compiled.requirements]
    assert len(titles) == 3
    assert any("next action" in title.lower() for title in titles)
    assert any("recovery" in title.lower() for title in titles)
    assert any("yaml" in title.lower() for title in titles)


def test_compiler_emits_negative_contracts_for_forbidden_behaviors() -> None:
    compiled = compile_plan_to_requirements(plan_text="- no yaml in normal mode")
    assert compiled.negative_contracts
    forbidden_values = [str(item.get("forbidden_state") or "").lower() for item in compiled.negative_contracts]
    assert any("no yaml in normal mode" in value for value in forbidden_values)


def test_compiler_assigns_verification_methods_deterministically() -> None:
    compiled_a = compile_plan_to_requirements(
        plan_text="- render next action label\n- persist presentation receipt"
    )
    compiled_b = compile_plan_to_requirements(
        plan_text="- render next action label\n- persist presentation receipt"
    )
    methods_a = [tuple(item.get("verification_methods") or []) for item in compiled_a.requirements]
    methods_b = [tuple(item.get("verification_methods") or []) for item in compiled_b.requirements]
    assert methods_a == methods_b
    assert any("user_surface_verification" in methods for methods in methods_a)
    assert any("receipts_verification" in methods for methods in methods_a)


def test_compiler_never_emits_empty_acceptance_tests() -> None:
    compiled = compile_plan_to_requirements(plan_text="- render review object")
    assert compiled.requirements
    assert all(isinstance(item.get("acceptance_tests"), list) and item.get("acceptance_tests") for item in compiled.requirements)


def test_compiler_seeds_unverified_completion_rows() -> None:
    compiled = compile_plan_to_requirements(plan_text="- enforce receipt gate")
    assert compiled.completion_seed
    assert all(row.get("overall") == "UNVERIFIED" for row in compiled.completion_seed)
