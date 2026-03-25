from __future__ import annotations

import pytest

from governance_runtime.kernel.guard_evaluator import GuardEvaluationError, GuardEvaluator


@pytest.fixture(autouse=True)
def _reset_guard_evaluator() -> None:
    GuardEvaluator.reset()


def test_transition_guard_true_for_implementation_started() -> None:
    state = {"implementation_started": True}
    assert GuardEvaluator.evaluate_event("implementation_started", state) is True


def test_transition_guard_false_for_implementation_started_when_missing() -> None:
    state = {}
    assert GuardEvaluator.evaluate_event("implementation_started", state) is False


def test_transition_guard_workflow_approved_requires_presentation_and_approve() -> None:
    ok_state = {
        "active_gate": "Evidence Presentation Gate",
        "user_review_decision": "approve",
    }
    bad_state = {
        "active_gate": "Evidence Presentation Gate",
        "user_review_decision": "changes_requested",
    }
    assert GuardEvaluator.evaluate_event("workflow_approved", ok_state) is True
    assert GuardEvaluator.evaluate_event("workflow_approved", bad_state) is False


def test_missing_transition_guard_fails_closed() -> None:
    with pytest.raises(GuardEvaluationError):
        GuardEvaluator.evaluate_event("nonexistent_event", {})
