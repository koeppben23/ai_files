from __future__ import annotations

import pytest

from governance_runtime.application.use_cases.rework_clarification import (
    classify_rework_clarification,
    derive_next_rail,
)


@pytest.mark.governance
def test_happy_scope_change_maps_to_ticket() -> None:
    outcome = classify_rework_clarification("Scope erweitern, neue Anforderungen und Deliverables aufnehmen.")
    assert outcome == "scope_change"
    assert derive_next_rail(outcome) == "/ticket"


@pytest.mark.governance
def test_happy_plan_change_maps_to_plan() -> None:
    outcome = classify_rework_clarification("Task bleibt gleich, aber Plan und Architektur muessen angepasst werden.")
    assert outcome == "plan_change"
    assert derive_next_rail(outcome) == "/plan"


@pytest.mark.governance
def test_happy_clarification_only_maps_to_continue() -> None:
    outcome = classify_rework_clarification("Bitte nur die Begruendung klarer erklaeren, ohne inhaltliche Aenderung.")
    assert outcome == "clarification_only"
    assert derive_next_rail(outcome) == "/continue"


@pytest.mark.governance
def test_bad_vague_response_is_insufficient() -> None:
    outcome = classify_rework_clarification("passt nicht")
    assert outcome == "insufficient"
    assert derive_next_rail(outcome) is None


@pytest.mark.governance
def test_edge_scope_and_plan_mixed_prefers_ticket() -> None:
    outcome = classify_rework_clarification("Der Scope aendert sich und der Plan muss ebenfalls umgestellt werden.")
    assert outcome == "scope_change"
    assert derive_next_rail(outcome) == "/ticket"


@pytest.mark.governance
def test_corner_plan_and_clarification_prefers_plan() -> None:
    outcome = classify_rework_clarification("Bitte Strategie im Plan anpassen und danach klarer erklaeren.")
    assert outcome == "plan_change"
    assert derive_next_rail(outcome) == "/plan"
