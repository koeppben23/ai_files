from __future__ import annotations

import inspect

import yaml

from governance_runtime.kernel.phase_kernel import _build_guard_evaluation_state
from governance_runtime.kernel.phase_kernel import _transition_guard_passes
from governance_runtime.kernel.phase_kernel import execute
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
    """Legacy guard fallback is frozen off to prevent double-truth drift."""
    assert LEGACY_TRANSITION_GUARD_EVENTS == frozenset()


def test_transition_guard_path_contains_no_event_specific_hardcoded_fallbacks() -> None:
    """Guard path must not reintroduce hardcoded event if/elif branches."""
    source = inspect.getsource(_transition_guard_passes)
    assert "if event ==" not in source
    assert "legacy_transition_guard" not in source


def test_execute_contains_no_phase6_topology_correction_backdoor() -> None:
    """execute() must not rewrite Phase-6 targets after topology resolution."""
    source = inspect.getsource(execute)
    assert "topology-corrected" not in source
    assert "TopologyLoader._ensure_loaded()" not in source


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


def test_guard_state_normalization_keeps_explicit_active_gate_precedence() -> None:
    """Canonical active_gate input must not be replaced by alias values."""
    state = {
        "Phase": "6-PostFlight",
        "active_gate": "Evidence Presentation Gate",
        "ActiveGate": "Implementation Internal Review",
    }

    normalized = _build_guard_evaluation_state(
        state,
        entry=None,
        plan_record_versions=1,
    )

    assert normalized.get("active_gate") == "Evidence Presentation Gate"


def test_guard_state_normalization_does_not_invent_user_review_decision() -> None:
    """Invalid or absent user decision must not be fabricated into a valid decision."""
    state = {
        "Phase": "6-PostFlight",
        "active_gate": "Evidence Presentation Gate",
        "UserReviewDecision": {"decision": "maybe"},
    }

    normalized = _build_guard_evaluation_state(
        state,
        entry=None,
        plan_record_versions=1,
    )

    assert "user_review_decision" not in normalized


def test_guard_state_normalization_does_not_reconstruct_impl_status_from_gate_only() -> None:
    """Implementation status flags must not be synthesized from gate labels alone."""
    state = {
        "Phase": "6-PostFlight",
        "active_gate": "Implementation Blocked",
    }

    normalized = _build_guard_evaluation_state(
        state,
        entry=None,
        plan_record_versions=1,
    )

    assert "implementation_execution_status" not in normalized
    assert "implementation_hard_blockers" not in normalized


def test_guard_state_normalization_does_not_override_explicit_impl_status() -> None:
    """Explicit implementation status must win over unrelated gate text."""
    state = {
        "Phase": "6-PostFlight",
        "active_gate": "Implementation Blocked",
        "implementation_execution_status": "in_progress",
    }

    normalized = _build_guard_evaluation_state(
        state,
        entry=None,
        plan_record_versions=1,
    )

    assert normalized.get("implementation_execution_status") == "in_progress"


def test_guard_state_normalization_workflow_complete_is_not_string_coerced() -> None:
    """workflow_complete must remain input-driven bool, not string-coerced."""
    state = {
        "Phase": "6-PostFlight",
        "active_gate": "Evidence Presentation Gate",
        "workflow_complete": "true",
    }

    normalized = _build_guard_evaluation_state(
        state,
        entry=None,
        plan_record_versions=1,
    )

    assert normalized.get("workflow_complete") == "true"
