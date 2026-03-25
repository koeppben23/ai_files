from __future__ import annotations

import pytest

from governance_runtime.kernel.guard_evaluator import GuardEvaluationError, GuardEvaluator
from governance_runtime.kernel.phase_api_spec import PhaseApiSpec, PhaseSpecEntry, TransitionRule
from governance_runtime.kernel.phase_kernel import RuntimeContext, execute


def _runtime_ctx(tmp_path):
    return RuntimeContext(
        requested_active_gate="",
        requested_next_gate_condition="Continue",
        repo_is_git_root=True,
        commands_home=tmp_path / "commands",
        workspaces_home=tmp_path / "workspaces",
        config_root=tmp_path / "cfg",
    )


def _patch_common(monkeypatch, tmp_path, spec: PhaseApiSpec) -> None:
    monkeypatch.setattr("governance_runtime.kernel.phase_kernel.load_phase_api", lambda _commands_home: spec)
    monkeypatch.setattr("governance_runtime.kernel.phase_kernel._resolve_paths", lambda _ctx: (tmp_path / "commands", tmp_path / "workspaces", tmp_path / "cfg", True, []))
    monkeypatch.setattr("governance_runtime.kernel.phase_kernel._persistence_gate_passed", lambda _state: (True, ""))
    monkeypatch.setattr("governance_runtime.kernel.phase_kernel._rulebook_gate_passed", lambda _state: (True, ""))
    monkeypatch.setattr("governance_runtime.kernel.phase_kernel._validate_phase_1_3_foundation", lambda _state: (True, ""))
    monkeypatch.setattr("governance_runtime.kernel.phase_kernel._validate_exit", lambda _entry, _state: (True, ""))
    monkeypatch.setattr(
        "governance_runtime.kernel.phase_kernel.can_promote_to_phase6",
        lambda **_kwargs: (True, type("obj", (object,), {"passed": True, "reason_code": "", "first_open_gate": None})()),
    )


def test_execute_non_phase6_uses_evaluator_first_guard_match(tmp_path, monkeypatch):
    """execute(): non-Phase6 uses evaluator-first and does not let default shadow guards."""
    spec = PhaseApiSpec(
        path=tmp_path / "phase_api.yaml",
        sha256="fake",
        stable_hash="fake",
        loaded_at="now",
        start_token="2.1",
        entries={
            "2.1": PhaseSpecEntry(
                token="2.1",
                phase="2.1-DecisionPack",
                active_gate="Decision Pack",
                next_gate_condition="Continue",
                next_token="3A",
                route_strategy="next",
                transitions=(
                    TransitionRule(when="default", next_token="3A", source="phase-2.1-to-3a"),
                    TransitionRule(when="business_rules_execute", next_token="1.5", source="phase-1.5-routing-required"),
                ),
                exit_required_keys=(),
            ),
            "1.5": PhaseSpecEntry(
                token="1.5",
                phase="1.5-BusinessRules",
                active_gate="Business Rules Bootstrap",
                next_gate_condition="Bootstrap rules",
                next_token="3A",
                route_strategy="next",
                transitions=(),
                exit_required_keys=(),
            ),
            "3A": PhaseSpecEntry(
                token="3A",
                phase="3A-API-Inventory",
                active_gate="API Inventory",
                next_gate_condition="Continue",
                next_token="4",
                route_strategy="next",
                transitions=(),
                exit_required_keys=(),
            ),
        },
    )

    _patch_common(monkeypatch, tmp_path, spec)

    monkeypatch.setattr(GuardEvaluator, "has_transition_guard", staticmethod(lambda event: event == "business_rules_execute"))
    monkeypatch.setattr(GuardEvaluator, "evaluate_event", staticmethod(lambda event, state: event == "business_rules_execute"))

    result = execute(
        current_token="2.1",
        session_state_doc={"SESSION_STATE": {"Phase": "2.1-DecisionPack", "phase_transition_evidence": True}},
        runtime_ctx=_runtime_ctx(tmp_path),
        readonly=True,
    )

    assert result.next_token == "1.5"
    assert result.source == "phase-1.5-routing-required"


def test_execute_non_phase6_legacy_fallback_implementation_presentation_ready(tmp_path, monkeypatch):
    """execute(): only explicit legacy fallback event remains supported."""
    spec = PhaseApiSpec(
        path=tmp_path / "phase_api.yaml",
        sha256="fake",
        stable_hash="fake",
        loaded_at="now",
        start_token="6",
        entries={
            "6": PhaseSpecEntry(
                token="6",
                phase="6-PostFlight",
                active_gate="Post Flight",
                next_gate_condition="Continue",
                next_token="6",
                route_strategy="stay",
                transitions=(
                    TransitionRule(when="default", next_token="6", source="phase-6-implementation-review-required"),
                    TransitionRule(when="implementation_presentation_ready", next_token="6.presentation", source="phase-6-implementation-presentation-ready"),
                ),
                exit_required_keys=(),
            ),
            "6.presentation": PhaseSpecEntry(
                token="6.presentation",
                phase="6-PostFlight",
                active_gate="Evidence Presentation Gate",
                next_gate_condition="Submit decision",
                next_token="6.approved",
                route_strategy="stay",
                transitions=(),
                exit_required_keys=(),
            ),
        },
    )

    _patch_common(monkeypatch, tmp_path, spec)
    monkeypatch.setattr(GuardEvaluator, "has_transition_guard", staticmethod(lambda _event: False))

    result = execute(
        current_token="6",
        session_state_doc={"SESSION_STATE": {"Phase": "6-PostFlight", "phase_transition_evidence": True, "active_gate": "Implementation Presentation Gate"}},
        runtime_ctx=_runtime_ctx(tmp_path),
        readonly=True,
    )

    assert result.next_token == "6.presentation"
    assert result.source == "phase-6-implementation-presentation-ready"


def test_execute_non_phase6_guard_evaluator_error_is_visible(tmp_path, monkeypatch):
    """execute(): evaluator failures on non-Phase6 path are not silent."""
    spec = PhaseApiSpec(
        path=tmp_path / "phase_api.yaml",
        sha256="fake",
        stable_hash="fake",
        loaded_at="now",
        start_token="2.1",
        entries={
            "2.1": PhaseSpecEntry(
                token="2.1",
                phase="2.1-DecisionPack",
                active_gate="Decision Pack",
                next_gate_condition="Continue",
                next_token="3A",
                route_strategy="next",
                transitions=(
                    TransitionRule(when="business_rules_execute", next_token="1.5", source="phase-1.5-routing-required"),
                    TransitionRule(when="default", next_token="3A", source="phase-2.1-to-3a"),
                ),
                exit_required_keys=(),
            ),
        },
    )

    _patch_common(monkeypatch, tmp_path, spec)

    monkeypatch.setattr(GuardEvaluator, "has_transition_guard", staticmethod(lambda event: event == "business_rules_execute"))

    def _boom(event, state):
        raise GuardEvaluationError("non-phase6 evaluator error")

    monkeypatch.setattr(GuardEvaluator, "evaluate_event", staticmethod(_boom))

    with pytest.raises(GuardEvaluationError, match="non-phase6 evaluator error"):
        execute(
            current_token="2.1",
            session_state_doc={"SESSION_STATE": {"Phase": "2.1-DecisionPack", "phase_transition_evidence": True}},
            runtime_ctx=_runtime_ctx(tmp_path),
            readonly=True,
        )
