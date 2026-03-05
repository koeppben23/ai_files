"""Tests for Response Intent Resolver (Phase 3).

Eight test classes covering Happy/Bad/Edge/Corner cases:
    1. TestResolverDirectPolicy    — SSOT policy resolution
    2. TestResolverStructuralInference — PrimaryIntent inference from tokens
    3. TestResolverFailClosed      — Unknown/broken context → restrictive fallback
    4. TestResolverIntegration     — Orchestrator wiring
    5. TestConflictPrecedence      — Resolver vs keyword matcher precedence
    6. TestInheritanceIntegrity    — 5.x policy inheritance
    7. TestBackwardCompatibility   — Legacy calls without resolved_intent
    8. TestDriftDetection          — Keyword matcher drift logging
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Mapping
from unittest.mock import patch

import pytest

from governance.application.use_cases.resolve_output_intent import (
    IntentResolutionSource,
    PrimaryIntent,
    ResolvedOutputIntent,
    _RESTRICTIVE_FALLBACK_POLICY,
    _TOKEN_INTENT_MAP,
    _infer_primary_intent,
    resolve_output_intent,
)
from governance.domain.phase_state_machine import (
    PhaseOutputPolicy,
    PlanDiscipline,
    clear_phase_output_policy_cache,
    resolve_phase_output_policy,
    set_phase_api_loader,
)
from governance.engine.response_contract import (
    NextAction,
    Snapshot,
    _apply_resolved_intent_policy,
    _validate_output_class_for_phase,
    build_strict_response,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_phase_api_phases() -> list[Mapping[str, Any]]:
    """Return a minimal phase_api.yaml phases list with output_policy on token 5."""
    return [
        {"token": "0", "phase": "0-Init", "route_strategy": "next"},
        {"token": "1", "phase": "1-Bootstrap", "route_strategy": "next"},
        {"token": "1.1", "phase": "1.1-Bootstrap", "route_strategy": "next"},
        {"token": "1.2", "phase": "1.2-Bootstrap", "route_strategy": "next"},
        {"token": "1.5", "phase": "1.5-Bootstrap", "route_strategy": "next"},
        {"token": "2", "phase": "2-Discover", "route_strategy": "next"},
        {"token": "2.1", "phase": "2.1-DecisionPack", "route_strategy": "next"},
        {"token": "3A", "phase": "3A-ApiInventory", "route_strategy": "next"},
        {"token": "4", "phase": "4-Intake", "route_strategy": "stay"},
        {
            "token": "5",
            "phase": "5-Review",
            "route_strategy": "stay",
            "output_policy": {
                "allowed_output_classes": [
                    "plan", "review", "risk_analysis", "test_strategy",
                    "gate_check", "rollback_plan", "review_questions",
                    "consolidated_review_plan",
                ],
                "forbidden_output_classes": [
                    "implementation", "patch", "diff", "code_delivery",
                ],
                "plan_discipline": {
                    "first_output_is_draft": True,
                    "draft_not_review_ready": True,
                    "min_self_review_iterations": 1,
                },
            },
        },
        {"token": "5.3", "phase": "5.3-TestQualityGate", "route_strategy": "next"},
        {"token": "5.4", "phase": "5.4-BusinessRulesGate", "route_strategy": "next"},
        {"token": "5.5", "phase": "5.5-PlanCompliance", "route_strategy": "next"},
        {"token": "5.6", "phase": "5.6-RollbackSafety", "route_strategy": "next"},
        {"token": "6", "phase": "6-Summary", "route_strategy": "stay"},
    ]


@pytest.fixture(autouse=True)
def _setup_phase_api_loader():
    """Register a test loader for phase_api.yaml output policy resolution."""
    set_phase_api_loader(lambda: _make_phase_api_phases())
    yield
    clear_phase_output_policy_cache()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_session_state(phase: str = "5-Review") -> dict[str, object]:
    """Build minimal session state for contract builder tests."""
    return {
        "phase": phase,
        "Phase": phase,
        "effective_operating_mode": "user",
        "activation_hash": "test-activation-hash-001",
        "ruleset_hash": "test-ruleset-hash-001",
        "repo_fingerprint": "test-fingerprint-001",
    }


def _next_action() -> NextAction:
    return NextAction(type="command", command="show governance")


def _snapshot() -> Snapshot:
    return Snapshot(confidence="high", risk="low", scope="repo")


def _reason_payload() -> dict[str, object]:
    return {"status": "OK", "reason_code": "none"}


# ===========================================================================
# 1. TestResolverDirectPolicy
# ===========================================================================

class TestResolverDirectPolicy:
    """Verify that tokens with explicit output_policy in phase_api.yaml resolve correctly."""

    def test_token_5_resolves_to_phase_api_policy(self) -> None:
        """Happy: Token '5' has explicit output_policy → status=resolved, source=phase_api_policy."""
        result = resolve_output_intent(phase_token="5", route_strategy="stay")
        assert result.policy_resolution_status == "resolved"
        assert result.source == "phase_api_policy"
        assert result.effective_output_policy is not None
        assert "implementation" in result.effective_output_policy.forbidden_output_classes
        assert "plan" in result.effective_output_policy.allowed_output_classes

    def test_token_5_primary_intent_is_review_architecture(self) -> None:
        """Happy: Token '5' → primary_intent=review_architecture."""
        result = resolve_output_intent(phase_token="5", route_strategy="stay")
        assert result.primary_intent == "review_architecture"

    def test_token_4_has_no_output_policy(self) -> None:
        """Happy: Token '4' has no output_policy → status=unbounded."""
        result = resolve_output_intent(phase_token="4", route_strategy="stay")
        assert result.policy_resolution_status == "unbounded"
        assert result.effective_output_policy is None
        assert result.source == "structural_inference"

    def test_token_6_has_no_output_policy(self) -> None:
        """Happy: Token '6' has no output_policy → status=unbounded."""
        result = resolve_output_intent(phase_token="6", route_strategy="stay")
        assert result.policy_resolution_status == "unbounded"
        assert result.effective_output_policy is None

    def test_token_5_plan_discipline_is_populated(self) -> None:
        """Happy: Token '5' plan_discipline fields match SSOT."""
        result = resolve_output_intent(phase_token="5", route_strategy="stay")
        assert result.effective_output_policy is not None
        pd = result.effective_output_policy.plan_discipline
        assert pd.first_output_is_draft is True
        assert pd.draft_not_review_ready is True
        assert pd.min_self_review_iterations == 1

    def test_token_5_plan_record_preparation_gate_restricts_output_classes(self) -> None:
        """Phase 5 prep gate allows only plan authoring classes."""
        result = resolve_output_intent(
            phase_token="5",
            route_strategy="stay",
            active_gate="Plan Record Preparation Gate",
        )
        assert result.policy_resolution_status == "resolved"
        assert result.effective_output_policy is not None
        assert set(result.effective_output_policy.allowed_output_classes) == {
            "plan",
            "consolidated_review_plan",
        }
        assert "implementation" in result.effective_output_policy.forbidden_output_classes

    def test_token_5_architecture_review_gate_keeps_full_phase5_policy(self) -> None:
        """Phase 5 architecture review gate keeps full SSOT policy."""
        result = resolve_output_intent(
            phase_token="5",
            route_strategy="stay",
            active_gate="Architecture Review Gate",
        )
        assert result.effective_output_policy is not None
        assert "review" in result.effective_output_policy.allowed_output_classes

    def test_fallback_classification_not_used_for_resolved(self) -> None:
        """Happy: Resolved intent does NOT use fallback classification."""
        result = resolve_output_intent(phase_token="5", route_strategy="stay")
        assert result.fallback_classification_used is False

    def test_token_2_unbounded_with_repo_discovery_intent(self) -> None:
        """Edge: Token '2' → unbounded + repo_discovery intent."""
        result = resolve_output_intent(phase_token="2", route_strategy="next")
        assert result.policy_resolution_status == "unbounded"
        assert result.primary_intent == "repo_discovery"

    def test_token_3a_unbounded_with_api_inventory_intent(self) -> None:
        """Edge: Token '3A' → unbounded + api_inventory intent (case-insensitive)."""
        result = resolve_output_intent(phase_token="3a", route_strategy="next")
        assert result.policy_resolution_status == "unbounded"
        assert result.primary_intent == "api_inventory"


# ===========================================================================
# 2. TestResolverStructuralInference
# ===========================================================================

class TestResolverStructuralInference:
    """Verify PrimaryIntent inference from phase tokens (token-based, driftfree)."""

    def test_bootstrap_tokens_infer_system_bootstrap(self) -> None:
        """Happy: Tokens 0, 1, 1.1, 1.2, 1.5 → system_bootstrap."""
        for token in ("0", "1", "1.1", "1.2", "1.5"):
            result = resolve_output_intent(phase_token=token, route_strategy="next")
            assert result.primary_intent == "system_bootstrap", f"Failed for token {token}"

    def test_phase_2_infers_repo_discovery(self) -> None:
        """Happy: Tokens 2, 2.1 → repo_discovery."""
        for token in ("2", "2.1"):
            result = resolve_output_intent(phase_token=token, route_strategy="next")
            assert result.primary_intent == "repo_discovery", f"Failed for token {token}"

    def test_phase_3a_infers_api_inventory(self) -> None:
        """Happy: Token 3A → api_inventory."""
        result = resolve_output_intent(phase_token="3A", route_strategy="next")
        assert result.primary_intent == "api_inventory"

    def test_phase_4_infers_collect_input(self) -> None:
        """Happy: Token 4 → collect_input."""
        result = resolve_output_intent(phase_token="4", route_strategy="stay")
        assert result.primary_intent == "collect_input"

    def test_phase_5_stay_infers_review_architecture(self) -> None:
        """Happy: Token 5 + stay → review_architecture."""
        result = resolve_output_intent(phase_token="5", route_strategy="stay")
        assert result.primary_intent == "review_architecture"

    def test_phase_5x_infers_gate_evaluation(self) -> None:
        """Happy: Tokens 5.3, 5.4, 5.5, 5.6 → gate_evaluation (token-based rule)."""
        for token in ("5.3", "5.4", "5.5", "5.6"):
            result = resolve_output_intent(phase_token=token, route_strategy="next")
            assert result.primary_intent == "gate_evaluation", f"Failed for token {token}"

    def test_phase_5x_gate_evaluation_regardless_of_route_strategy(self) -> None:
        """Edge: 5.x tokens → gate_evaluation even with route_strategy='stay'."""
        result = resolve_output_intent(phase_token="5.3", route_strategy="stay")
        assert result.primary_intent == "gate_evaluation"

    def test_phase_6_infers_terminal_summary(self) -> None:
        """Happy: Token 6 → terminal_summary."""
        result = resolve_output_intent(phase_token="6", route_strategy="stay")
        assert result.primary_intent == "terminal_summary"

    def test_all_known_tokens_covered(self) -> None:
        """Corner: Every token in _TOKEN_INTENT_MAP produces a known PrimaryIntent."""
        for token, expected_intent in _TOKEN_INTENT_MAP.items():
            result = _infer_primary_intent(token)
            assert result == expected_intent, f"Token {token}: expected {expected_intent}, got {result}"

    def test_route_strategy_does_not_affect_primary_intent(self) -> None:
        """Edge: route_strategy has no effect on PrimaryIntent for any known token."""
        for token in ("0", "2", "4", "5", "5.3", "6"):
            r1 = resolve_output_intent(phase_token=token, route_strategy="stay")
            r2 = resolve_output_intent(phase_token=token, route_strategy="next")
            assert r1.primary_intent == r2.primary_intent, f"Mismatch for token {token}"


# ===========================================================================
# 3. TestResolverFailClosed
# ===========================================================================

class TestResolverFailClosed:
    """Verify fail-closed behavior for unknown/broken context."""

    def test_unknown_token_returns_unresolved(self) -> None:
        """Bad: Unknown token → unresolved + restrictive fallback policy."""
        result = resolve_output_intent(phase_token="99", route_strategy="stay")
        assert result.policy_resolution_status == "unresolved"
        assert result.source == "fail_closed_fallback"
        assert result.primary_intent == "unknown"
        assert result.effective_output_policy is not None
        assert "implementation" in result.effective_output_policy.forbidden_output_classes

    def test_empty_string_token_returns_unresolved(self) -> None:
        """Bad: Empty string token → unresolved."""
        result = resolve_output_intent(phase_token="", route_strategy="stay")
        assert result.policy_resolution_status == "unresolved"
        assert result.source == "fail_closed_fallback"

    def test_whitespace_only_token_returns_unresolved(self) -> None:
        """Edge: Whitespace-only token → unresolved."""
        result = resolve_output_intent(phase_token="   ", route_strategy="stay")
        assert result.policy_resolution_status == "unresolved"

    def test_none_route_strategy_handled_gracefully(self) -> None:
        """Edge: None route_strategy does not crash."""
        result = resolve_output_intent(phase_token="5", route_strategy="")
        assert result.policy_resolution_status == "resolved"

    def test_restrictive_fallback_policy_forbids_implementation(self) -> None:
        """Corner: Restrictive fallback policy forbids implementation, patch, diff, code_delivery."""
        policy = _RESTRICTIVE_FALLBACK_POLICY
        assert "implementation" in policy.forbidden_output_classes
        assert "patch" in policy.forbidden_output_classes
        assert "diff" in policy.forbidden_output_classes
        assert "code_delivery" in policy.forbidden_output_classes

    def test_restrictive_fallback_allows_plan_review_gate_check(self) -> None:
        """Corner: Restrictive fallback allows plan, review, gate_check."""
        policy = _RESTRICTIVE_FALLBACK_POLICY
        assert "plan" in policy.allowed_output_classes
        assert "review" in policy.allowed_output_classes
        assert "gate_check" in policy.allowed_output_classes

    def test_fallback_is_frozen_dataclass(self) -> None:
        """Corner: Restrictive fallback policy is immutable."""
        with pytest.raises(AttributeError):
            _RESTRICTIVE_FALLBACK_POLICY.allowed_output_classes = ()  # type: ignore[misc]

    def test_nonsensical_token_fails_closed(self) -> None:
        """Bad: Completely nonsensical token → unresolved."""
        result = resolve_output_intent(phase_token="xyz-broken!", route_strategy="stay")
        assert result.policy_resolution_status == "unresolved"
        assert result.primary_intent == "unknown"


# ===========================================================================
# 4. TestResolverIntegration
# ===========================================================================

class TestResolverIntegration:
    """Verify resolver integration with orchestrator and contract."""

    def test_resolved_output_intent_dto_is_frozen(self) -> None:
        """Happy: ResolvedOutputIntent is immutable."""
        result = resolve_output_intent(phase_token="5", route_strategy="stay")
        with pytest.raises(AttributeError):
            result.primary_intent = "unknown"  # type: ignore[misc]

    def test_resolved_output_intent_fields_complete(self) -> None:
        """Happy: All expected fields present on resolved intent."""
        result = resolve_output_intent(phase_token="5", route_strategy="stay")
        assert hasattr(result, "effective_output_policy")
        assert hasattr(result, "primary_intent")
        assert hasattr(result, "source")
        assert hasattr(result, "policy_resolution_status")
        assert hasattr(result, "fallback_classification_used")

    def test_build_strict_response_accepts_resolved_output_intent(self) -> None:
        """Happy: build_strict_response accepts resolved_output_intent kwarg."""
        intent = resolve_output_intent(phase_token="5", route_strategy="stay")
        session = _minimal_session_state("5-Review")
        # Should not raise — "review" action is allowed in phase 5
        result = build_strict_response(
            status="OK",
            session_state=session,
            next_action=_next_action(),
            snapshot=_snapshot(),
            reason_payload=_reason_payload(),
            requested_action="review the architecture",
            resolved_output_intent=intent,
        )
        assert result["status"] == "OK"

    def test_build_strict_response_blocks_forbidden_class_via_resolver(self) -> None:
        """Bad: build_strict_response rejects forbidden output class via resolved intent."""
        intent = resolve_output_intent(phase_token="5", route_strategy="stay")
        session = _minimal_session_state("5-Review")
        with pytest.raises(ValueError, match="forbidden.*resolved intent"):
            build_strict_response(
                status="OK",
                session_state=session,
                next_action=_next_action(),
                snapshot=_snapshot(),
                reason_payload=_reason_payload(),
                requested_action="implement the feature",
                resolved_output_intent=intent,
            )

    def test_resolved_intent_on_orchestrator_output_accessible(self) -> None:
        """Happy: EngineOrchestratorOutput has resolved_output_intent field."""
        from governance.application.use_cases.orchestrate_run import EngineOrchestratorOutput
        assert hasattr(EngineOrchestratorOutput, "resolved_output_intent")

    def test_kernel_result_has_route_strategy(self) -> None:
        """Happy: KernelResult dataclass includes route_strategy field."""
        from governance.kernel.phase_kernel import KernelResult
        import dataclasses
        field_names = {f.name for f in dataclasses.fields(KernelResult)}
        assert "route_strategy" in field_names

    def test_routed_phase_has_route_strategy(self) -> None:
        """Happy: RoutedPhase dataclass includes route_strategy field."""
        from governance.application.use_cases.phase_router import RoutedPhase
        import dataclasses
        field_names = {f.name for f in dataclasses.fields(RoutedPhase)}
        assert "route_strategy" in field_names


# ===========================================================================
# 5. TestConflictPrecedence
# ===========================================================================

class TestConflictPrecedence:
    """Verify precedence rules when resolver and keyword matcher disagree."""

    def test_resolved_policy_blocks_even_if_keyword_would_allow(self) -> None:
        """Happy: resolved + keyword matcher disagrees → resolver wins (blocks)."""
        # Phase 5 policy forbids implementation.
        # Construct a resolved intent that says "resolved" with phase 5 policy.
        intent = resolve_output_intent(phase_token="5", route_strategy="stay")
        assert intent.policy_resolution_status == "resolved"
        # "implement the feature" → classify_output_class returns "implementation" (forbidden)
        with pytest.raises(ValueError, match="forbidden.*resolved"):
            _apply_resolved_intent_policy(
                resolved_output_intent=intent,
                requested_action="implement the feature",
            )

    def test_resolved_allows_when_keyword_matches_allowed_class(self) -> None:
        """Happy: resolved + action is allowed → no block."""
        intent = resolve_output_intent(phase_token="5", route_strategy="stay")
        # "review the architecture" → classify_output_class returns "review" (allowed)
        _apply_resolved_intent_policy(
            resolved_output_intent=intent,
            requested_action="review the architecture",
        )  # Should not raise

    def test_unbounded_does_not_block_implementation(self) -> None:
        """Happy: unbounded + keyword flags implementation → no block, log only."""
        intent = resolve_output_intent(phase_token="4", route_strategy="stay")
        assert intent.policy_resolution_status == "unbounded"
        # "implement" would be flagged by keyword matcher, but unbounded → no block
        _apply_resolved_intent_policy(
            resolved_output_intent=intent,
            requested_action="implement the feature",
        )  # Should not raise

    def test_unresolved_blocks_implementation(self) -> None:
        """Bad: unresolved + keyword flags implementation → block allowed."""
        intent = resolve_output_intent(phase_token="99", route_strategy="stay")
        assert intent.policy_resolution_status == "unresolved"
        with pytest.raises(ValueError, match="forbidden.*restrictive fallback"):
            _apply_resolved_intent_policy(
                resolved_output_intent=intent,
                requested_action="implement the feature",
            )

    def test_unresolved_allows_review(self) -> None:
        """Edge: unresolved + review action → allowed by restrictive fallback."""
        intent = resolve_output_intent(phase_token="99", route_strategy="stay")
        _apply_resolved_intent_policy(
            resolved_output_intent=intent,
            requested_action="review the architecture",
        )  # Should not raise

    def test_unresolved_blocks_patch(self) -> None:
        """Bad: unresolved + patch action → blocked by restrictive fallback."""
        intent = resolve_output_intent(phase_token="99", route_strategy="stay")
        with pytest.raises(ValueError, match="forbidden.*restrictive fallback"):
            _apply_resolved_intent_policy(
                resolved_output_intent=intent,
                requested_action="apply patch to fix bug",
            )

    def test_unresolved_blocks_diff(self) -> None:
        """Bad: unresolved + diff action → blocked by restrictive fallback."""
        intent = resolve_output_intent(phase_token="99", route_strategy="stay")
        with pytest.raises(ValueError, match="forbidden.*restrictive fallback"):
            _apply_resolved_intent_policy(
                resolved_output_intent=intent,
                requested_action="show diff of changes",
            )

    def test_unresolved_blocks_code_delivery(self) -> None:
        """Bad: unresolved + code_delivery action → blocked by restrictive fallback."""
        intent = resolve_output_intent(phase_token="99", route_strategy="stay")
        with pytest.raises(ValueError, match="forbidden.*restrictive fallback"):
            _apply_resolved_intent_policy(
                resolved_output_intent=intent,
                requested_action="deliver code to production",
            )

    def test_none_intent_is_noop(self) -> None:
        """Corner: None resolved_output_intent → no-op (backward compat)."""
        _apply_resolved_intent_policy(
            resolved_output_intent=None,
            requested_action="implement the feature",
        )  # Should not raise

    def test_empty_action_does_not_block(self) -> None:
        """Edge: Empty requested_action → no classification, no block."""
        intent = resolve_output_intent(phase_token="5", route_strategy="stay")
        _apply_resolved_intent_policy(
            resolved_output_intent=intent,
            requested_action="",
        )  # Should not raise

    def test_none_action_does_not_block(self) -> None:
        """Edge: None requested_action → no classification, no block."""
        intent = resolve_output_intent(phase_token="5", route_strategy="stay")
        _apply_resolved_intent_policy(
            resolved_output_intent=intent,
            requested_action=None,
        )  # Should not raise


# ===========================================================================
# 6. TestInheritanceIntegrity
# ===========================================================================

class TestInheritanceIntegrity:
    """Verify 5.x tokens inherit output policy from token '5'."""

    def test_5_3_inherits_phase_5_policy(self) -> None:
        """Happy: Token 5.3 inherits output_policy from token 5."""
        result = resolve_output_intent(phase_token="5.3", route_strategy="next")
        assert result.policy_resolution_status == "resolved"
        assert result.source == "phase_api_policy"
        assert result.effective_output_policy is not None
        assert "implementation" in result.effective_output_policy.forbidden_output_classes

    def test_5_4_inherits_phase_5_policy(self) -> None:
        """Happy: Token 5.4 inherits output_policy from token 5."""
        result = resolve_output_intent(phase_token="5.4", route_strategy="next")
        assert result.policy_resolution_status == "resolved"
        assert result.effective_output_policy is not None

    def test_5_5_inherits_phase_5_policy(self) -> None:
        """Happy: Token 5.5 inherits output_policy from token 5."""
        result = resolve_output_intent(phase_token="5.5", route_strategy="next")
        assert result.policy_resolution_status == "resolved"
        assert result.effective_output_policy is not None

    def test_5_6_inherits_phase_5_policy(self) -> None:
        """Happy: Token 5.6 inherits output_policy from token 5."""
        result = resolve_output_intent(phase_token="5.6", route_strategy="next")
        assert result.policy_resolution_status == "resolved"
        assert result.effective_output_policy is not None

    def test_5_x_intents_are_gate_evaluation(self) -> None:
        """Happy: All 5.x sub-graph tokens have primary_intent=gate_evaluation."""
        for token in ("5.3", "5.4", "5.5", "5.6"):
            result = resolve_output_intent(phase_token=token, route_strategy="next")
            assert result.primary_intent == "gate_evaluation", f"Failed for token {token}"

    def test_5_x_plan_discipline_inherited(self) -> None:
        """Edge: 5.x tokens inherit plan_discipline from token 5."""
        for token in ("5.3", "5.4", "5.5", "5.6"):
            result = resolve_output_intent(phase_token=token, route_strategy="next")
            assert result.effective_output_policy is not None
            pd = result.effective_output_policy.plan_discipline
            assert pd.first_output_is_draft is True, f"Failed for token {token}"

    def test_inherited_policy_identical_to_parent(self) -> None:
        """Corner: Inherited policy is structurally identical to parent's policy."""
        parent = resolve_output_intent(phase_token="5", route_strategy="stay")
        for token in ("5.3", "5.4", "5.5", "5.6"):
            child = resolve_output_intent(phase_token=token, route_strategy="next")
            assert child.effective_output_policy == parent.effective_output_policy, (
                f"Token {token} policy differs from parent"
            )

    def test_non_5x_tokens_do_not_inherit(self) -> None:
        """Bad: Token '4' does not inherit from any parent output_policy."""
        result = resolve_output_intent(phase_token="4", route_strategy="stay")
        assert result.effective_output_policy is None
        assert result.policy_resolution_status == "unbounded"


# ===========================================================================
# 7. TestBackwardCompatibility
# ===========================================================================

class TestBackwardCompatibility:
    """Verify legacy calls without resolved_intent still work correctly."""

    def test_build_strict_response_without_resolved_intent(self) -> None:
        """Happy: Legacy call without resolved_output_intent uses keyword fallback."""
        session = _minimal_session_state("5-Review")
        # "review" action → allowed, should not raise
        result = build_strict_response(
            status="OK",
            session_state=session,
            next_action=_next_action(),
            snapshot=_snapshot(),
            reason_payload=_reason_payload(),
            requested_action="review the architecture",
        )
        assert result["status"] == "OK"

    def test_legacy_blocks_forbidden_class_via_keyword_fallback(self) -> None:
        """Bad: Legacy call blocks forbidden output class via keyword matcher."""
        session = _minimal_session_state("5-Review")
        with pytest.raises(ValueError, match="forbidden"):
            build_strict_response(
                status="OK",
                session_state=session,
                next_action=_next_action(),
                snapshot=_snapshot(),
                reason_payload=_reason_payload(),
                requested_action="implement the feature",
            )

    def test_legacy_no_action_passes(self) -> None:
        """Edge: Legacy call with no requested_action → passes."""
        session = _minimal_session_state("5-Review")
        result = build_strict_response(
            status="OK",
            session_state=session,
            next_action=_next_action(),
            snapshot=_snapshot(),
            reason_payload=_reason_payload(),
        )
        assert result["status"] == "OK"

    def test_legacy_phase_4_allows_implementation(self) -> None:
        """Happy: Legacy call in phase 4 allows implementation (no output_policy)."""
        session = _minimal_session_state("4-Intake")
        result = build_strict_response(
            status="OK",
            session_state=session,
            next_action=NextAction(type="reply_with_one_number", command="pick a ticket"),
            snapshot=_snapshot(),
            reason_payload=_reason_payload(),
            requested_action="implement the feature",
        )
        assert result["status"] == "OK"

    def test_apply_resolved_intent_policy_none_is_noop(self) -> None:
        """Corner: _apply_resolved_intent_policy with None is pure no-op."""
        _apply_resolved_intent_policy(
            resolved_output_intent=None,
            requested_action="implement the feature",
        )  # Must not raise


# ===========================================================================
# 8. TestDriftDetection
# ===========================================================================

class TestDriftDetection:
    """Verify drift detection logging when keyword matcher differs from resolver."""

    def test_unbounded_logs_keyword_classification(self, caplog) -> None:
        """Happy: Unbounded phase logs keyword classification at DEBUG level."""
        intent = resolve_output_intent(phase_token="4", route_strategy="stay")
        with caplog.at_level(logging.DEBUG, logger="governance.engine.response_contract"):
            _apply_resolved_intent_policy(
                resolved_output_intent=intent,
                requested_action="implement the feature",
            )
        assert any("unbounded" in r.message and "no block" in r.message for r in caplog.records)

    def test_resolved_does_not_log_for_allowed_class(self, caplog) -> None:
        """Happy: Resolved phase with allowed action does not produce drift warnings."""
        intent = resolve_output_intent(phase_token="5", route_strategy="stay")
        with caplog.at_level(logging.DEBUG, logger="governance.engine.response_contract"):
            _apply_resolved_intent_policy(
                resolved_output_intent=intent,
                requested_action="review the architecture",
            )
        # No warning-level records expected
        warning_records = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warning_records) == 0

    def test_unresolved_logs_warning_on_resolver(self, caplog) -> None:
        """Bad: Unresolved token logs a warning during resolution."""
        with caplog.at_level(logging.WARNING, logger="governance.application.use_cases.resolve_output_intent"):
            resolve_output_intent(phase_token="99", route_strategy="stay")
        assert any("unresolved" in r.message for r in caplog.records)

    def test_empty_action_no_drift_log(self, caplog) -> None:
        """Edge: Empty action produces no drift log entries."""
        intent = resolve_output_intent(phase_token="4", route_strategy="stay")
        with caplog.at_level(logging.DEBUG, logger="governance.engine.response_contract"):
            _apply_resolved_intent_policy(
                resolved_output_intent=intent,
                requested_action="",
            )
        # No "unbounded" log because action is empty → no classification
        unbounded_logs = [r for r in caplog.records if "unbounded" in getattr(r, "message", "")]
        assert len(unbounded_logs) == 0

    def test_unknown_status_logs_warning(self, caplog) -> None:
        """Corner: Custom intent with unknown policy_resolution_status logs warning."""
        # Create a mock intent with an unexpected status
        weird_intent = ResolvedOutputIntent(
            effective_output_policy=None,
            primary_intent="unknown",
            source="fail_closed_fallback",
            policy_resolution_status="something_else",  # type: ignore[arg-type]
            fallback_classification_used=False,
        )
        with caplog.at_level(logging.WARNING, logger="governance.engine.response_contract"):
            _apply_resolved_intent_policy(
                resolved_output_intent=weird_intent,
                requested_action="implement something",
            )
        assert any("unknown policy_resolution_status" in r.message for r in caplog.records)
