from __future__ import annotations

import time

from governance_runtime.application.services.phase5_presentation_contract import NEXT_ACTIONS
from governance_runtime.application.services.phase5_presentation_contract import build_presentation_contract
from governance_runtime.application.services.phase5_presentation_contract import english_violations


def _base_plan() -> dict[str, object]:
    return {
        "objective": "Deliver secure authentication endpoint with deterministic governance evidence.",
        "target_state": "The login endpoint validates credentials and returns a signed token with audit trace.",
        "target_flow": "1. Add endpoint. 2. Validate credentials. 3. Sign token. 4. Persist evidence.",
        "state_machine": "unauthenticated -> authenticated",
        "blocker_taxonomy": "Configuration mismatch, missing dependencies, invalid credentials.",
        "audit": "Audit trail includes command, timestamp, actor, and output digest.",
        "go_no_go": "Go only when tests pass and no blocker remains.",
        "test_strategy": "Unit and integration tests verify success and failure paths.",
        "reason_code": "PLAN-001",
    }


def test_build_presentation_contract_includes_canonical_next_actions() -> None:
    contract = build_presentation_contract(_base_plan())
    assert contract["language"] == "en"
    assert contract["next_actions"] == list(NEXT_ACTIONS)
    assert contract["title"] == "PHASE 5 · PLAN FOR APPROVAL"


def test_english_violations_detects_obvious_non_english_markers() -> None:
    plan = _base_plan()
    plan["objective"] = "Der Plan ist klar und die Umsetzung ist nicht freigegeben."
    violations = english_violations(plan)
    assert "non-english-content:objective" in violations


def test_english_violations_accepts_english_plan_fields() -> None:
    violations = english_violations(_base_plan())
    assert not violations


def test_build_presentation_contract_marks_re_review_delta() -> None:
    contract = build_presentation_contract(_base_plan(), re_review=True)
    assert contract["delta_since_last_review"] == "Updated since last review iteration."


def test_build_presentation_contract_clamps_lengths_and_limits_lists() -> None:
    plan = _base_plan()
    plan["target_flow"] = "; ".join([f"slice {idx}" for idx in range(20)])
    plan["risks"] = "; ".join([f"risk {idx}" for idx in range(20)])
    plan["open_questions"] = "; ".join([f"decision {idx}" for idx in range(20)])
    plan["target_state"] = "A" * 1200
    plan["go_no_go"] = "B" * 1200

    contract = build_presentation_contract(plan)

    assert len(contract["execution_slices"]) <= 7
    assert len(contract["risks_and_mitigations"]) <= 5
    assert len(contract["open_decisions"]) <= 5
    assert len(contract["scope"]) <= 400
    assert len(contract["release_gates"]) <= 400
    assert contract["next_actions"] == list(NEXT_ACTIONS)


def test_build_presentation_contract_performance_is_stable() -> None:
    plan = _base_plan()
    start = time.perf_counter()
    for _ in range(5000):
        build_presentation_contract(plan)
    elapsed = time.perf_counter() - start
    assert elapsed < 2.0
