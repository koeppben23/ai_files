from __future__ import annotations

import yaml

from governance_runtime.kernel.phase_kernel import _build_guard_evaluation_state
from governance_runtime.kernel.phase_kernel import LEGACY_TRANSITION_GUARD_EVENTS


def _phase_api_events() -> set[str]:
    with open("governance_spec/phase_api.yaml", "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    events: set[str] = set()
    for phase in data.get("phases", []):
        for transition in phase.get("transitions", []) or []:
            when = str(transition.get("when", "")).strip().lower()
            if when:
                events.add(when)
    return events


def _guard_events() -> set[str]:
    with open("governance_spec/guards.yaml", "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    events: set[str] = set()
    for guard in data.get("guards", []):
        if guard.get("guard_type") != "transition":
            continue
        event = str(guard.get("event", "")).strip().lower()
        if event:
            events.add(event)
    return events


def _topology_phase6_events() -> set[str]:
    with open("governance_spec/topology.yaml", "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    events: set[str] = set()
    for state in data.get("states", []):
        state_id = str(state.get("id", "")).strip()
        if not state_id.startswith("6"):
            continue
        for transition in state.get("transitions", []) or []:
            event = str(transition.get("event", "")).strip().lower()
            if event:
                events.add(event)
    return events


def test_all_phase_api_transition_events_are_guarded_or_explicit_legacy() -> None:
    """No hidden double-truth: every transition event is either guarded or explicit legacy."""
    phase_events = _phase_api_events() - {"default"}
    guard_events = _guard_events()

    uncovered = sorted(phase_events - guard_events - set(LEGACY_TRANSITION_GUARD_EVENTS))
    assert not uncovered, f"Uncovered transition events (not in guards.yaml or legacy allowlist): {uncovered}"


def test_legacy_transition_events_are_tightly_scoped() -> None:
    """Legacy guard fallback set remains intentionally minimal."""
    assert LEGACY_TRANSITION_GUARD_EVENTS == {"implementation_presentation_ready"}


def test_phase6_topology_events_are_guarded_or_default() -> None:
    """Topology-authoritative Phase-6 events must be guarded (except default)."""
    phase6_events = _topology_phase6_events() - {"default"}
    guard_events = _guard_events()

    uncovered = sorted(phase6_events - guard_events)
    assert not uncovered, f"Uncovered Phase-6 topology events not in guards.yaml: {uncovered}"


def test_guard_state_normalization_does_not_invent_consumed_flag() -> None:
    """Normalization must not silently set rework_clarification_consumed=true."""
    state = {
        "Phase": "6-PostFlight",
        "phase6_state": "6.rework",
        "active_gate": "Rework Clarification Gate",
    }

    normalized = _build_guard_evaluation_state(
        state,
        entry=None,
        plan_record_versions=1,
    )

    assert normalized.get("phase6_state") == "6.rework"
    assert normalized.get("active_gate") == "Rework Clarification Gate"
    assert "rework_clarification_consumed" not in normalized


def test_guard_state_normalization_does_not_invent_phase6_state() -> None:
    """Normalization must not fabricate phase6_state when missing."""
    state = {
        "Phase": "6-PostFlight",
        "active_gate": "Implementation Internal Review",
    }

    normalized = _build_guard_evaluation_state(
        state,
        entry=None,
        plan_record_versions=1,
    )

    assert "phase6_state" not in normalized


def test_guard_state_normalization_keeps_explicit_status_and_flags() -> None:
    """Normalization preserves explicit business-critical status flags."""
    state = {
        "Phase": "5-ArchitectureReview",
        "active_gate": "Architecture Review Gate",
        "implementation_execution_status": "blocked",
        "technical_debt_proposed": True,
        "rollback_required": True,
    }

    normalized = _build_guard_evaluation_state(
        state,
        entry=None,
        plan_record_versions=1,
    )

    assert normalized.get("implementation_execution_status") == "blocked"
    assert normalized.get("technical_debt_proposed") is True
    assert normalized.get("rollback_required") is True


def test_guard_state_normalization_does_not_invent_workflow_complete() -> None:
    """workflow_complete must not be implicitly created when absent."""
    state = {
        "Phase": "6-PostFlight",
        "active_gate": "Implementation Internal Review",
    }

    normalized = _build_guard_evaluation_state(
        state,
        entry=None,
        plan_record_versions=1,
    )

    assert "workflow_complete" not in normalized


def test_guard_state_normalization_preserves_explicit_workflow_complete() -> None:
    """Explicit workflow_complete must be preserved for guard evaluation."""
    state = {
        "Phase": "6-PostFlight",
        "active_gate": "Evidence Presentation Gate",
        "workflow_complete": True,
    }

    normalized = _build_guard_evaluation_state(
        state,
        entry=None,
        plan_record_versions=1,
    )

    assert normalized.get("workflow_complete") is True
