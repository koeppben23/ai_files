"""Phase 7: Runtime Executor Substate Tests (v3)

Tests für die Phase 6 Substate-Detection-Funktionen im Runtime-Executor.
Überarbeitet mit kanonischen Resolver-Pfad und klarer Legacy-Bridge-Dokumentation.
"""

from __future__ import annotations

import pytest


class TestCanonicalPhase6SubstateResolver:
    """Tests für den kanonischen Phase 6 Substate Resolver."""

    def test_resolve_internal_review_from_phase6_state(self):
        """Happy: resolve_phase6_substate erkennt 6.internal_review vom kanonischen Feld."""
        from governance_runtime.kernel.phase_kernel import resolve_phase6_substate
        
        state = {"phase6_state": "6.internal_review"}
        assert resolve_phase6_substate(state) == "6.internal_review"

    def test_resolve_execution_from_phase6_state(self):
        """Happy: resolve_phase6_substate erkennt 6.execution vom kanonischen Feld."""
        from governance_runtime.kernel.phase_kernel import resolve_phase6_substate
        
        state = {"phase6_state": "6.execution"}
        assert resolve_phase6_substate(state) == "6.execution"

    def test_resolve_approved_from_phase6_state(self):
        """Happy: resolve_phase6_substate erkennt 6.approved vom kanonischen Feld."""
        from governance_runtime.kernel.phase_kernel import resolve_phase6_substate
        
        state = {"phase6_state": "6.approved"}
        assert resolve_phase6_substate(state) == "6.approved"

    def test_resolve_complete_from_phase6_state(self):
        """Happy: resolve_phase6_substate erkennt 6.complete vom kanonischen Feld."""
        from governance_runtime.kernel.phase_kernel import resolve_phase6_substate
        
        state = {"phase6_state": "6.complete"}
        assert resolve_phase6_substate(state) == "6.complete"

    def test_resolve_returns_6_when_no_phase6_indicators(self):
        """Happy: resolve_phase6_substate gibt "6" zurück wenn keine Phase-6-Indikatoren.
        
        Für leere/unbekannte States soll "6" (unknown) zurückgegeben werden,
        NICHT "6.internal_review". Die Bridge inferiert nur einen Substate,
        wenn echte Phase-6-Kontext-Indikatoren vorhanden sind.
        """
        from governance_runtime.kernel.phase_kernel import resolve_phase6_substate
        
        state = {}
        assert resolve_phase6_substate(state) == "6"
    
    def test_resolve_returns_internal_review_when_phase6_context_present(self):
        """Happy: resolve_phase6_substate gibt 6.internal_review bei Phase-6-Kontext.
        
        Wenn Phase-6-Kontext-Indikatoren vorhanden sind (phase_transition_evidence,
        ImplementationReview), aber phase6_state nicht gesetzt ist, soll die Bridge
        6.internal_review inferieren.
        """
        from governance_runtime.kernel.phase_kernel import resolve_phase6_substate
        
        state = {"phase_transition_evidence": True}
        assert resolve_phase6_substate(state) == "6.internal_review"

    def test_resolve_all_substates(self):
        """Happy: resolve_phase6_substate erkennt alle Substates."""
        from governance_runtime.kernel.phase_kernel import resolve_phase6_substate
        
        substates = [
            "6.internal_review", "6.presentation", "6.execution",
            "6.approved", "6.blocked", "6.rework", "6.rejected", "6.complete"
        ]
        
        for substate in substates:
            state = {"phase6_state": substate}
            assert resolve_phase6_substate(state) == substate, \
                f"Failed for {substate}"


class TestLegacyBridgePhase6SubstateDetection:
    """Tests für die LEGACY COMPATIBILITY BRIDGE Substate Detection.
    
    Diese Tests prüfen die Legacy-Heuristik, die nur für Rückwärtskompatibilität
    dient. Neue Code sollten resolve_phase6_substate() verwenden.
    """

    def test_legacy_detects_complete_from_workflow_flag(self):
        """Happy: Legacy erkennt 6.complete vom Workflow-Flag."""
        from governance_runtime.kernel.phase_kernel import _detect_phase6_substate_legacy
        
        state = {"workflow_complete": True}
        assert _detect_phase6_substate_legacy(state) == "6.complete"

    def test_legacy_detects_rejected_from_decision(self):
        """Happy: Legacy erkennt 6.rejected von Reject-Entscheidung."""
        from governance_runtime.kernel.phase_kernel import _detect_phase6_substate_legacy
        
        state = {"user_review_decision": "reject"}
        assert _detect_phase6_substate_legacy(state) == "6.rejected"

    def test_legacy_detects_execution_from_status(self):
        """Happy: Legacy erkennt 6.execution vom Execution-Status."""
        from governance_runtime.kernel.phase_kernel import _detect_phase6_substate_legacy
        
        state = {"implementation_execution_status": "in_progress"}
        assert _detect_phase6_substate_legacy(state) == "6.execution"

    def test_legacy_detects_blocked_from_hard_blockers(self):
        """Happy: Legacy erkennt 6.blocked von Hard-Blockers."""
        from governance_runtime.kernel.phase_kernel import _detect_phase6_substate_legacy
        
        state = {"implementation_hard_blockers": ["Critical Issue"]}
        assert _detect_phase6_substate_legacy(state) == "6.blocked"

    def test_legacy_detects_rework_from_clarification_required(self):
        """Happy: Legacy erkennt 6.rework von Rework-Clarification-Required."""
        from governance_runtime.kernel.phase_kernel import _detect_phase6_substate_legacy
        
        state = {"implementation_rework_clarification_required": True}
        assert _detect_phase6_substate_legacy(state) == "6.rework"

    def test_legacy_detects_approved_from_workflow_approved_flag(self):
        """Happy: Legacy erkennt 6.approved von workflow_approved flag."""
        from governance_runtime.kernel.phase_kernel import _detect_phase6_substate_legacy
        
        state = {"workflow_approved": True}
        assert _detect_phase6_substate_legacy(state) == "6.approved"

    def test_legacy_ignores_implementation_accepted_gate(self):
        """NEGATIVE: "Implementation Accepted" gate wird NICHT als Mapping-Quelle verwendet.
        
        "Implementation Accepted" ist ein LEGACY GATE-Wert.
        Er wird NICHT direkt auf einen Substate gemappt.
        
        Begründung:
        - "Implementation Accepted" bedeutet: Implementierungs-ERGEBNIS akzeptiert
          (post-execution, semantisch ≈ workflow_complete → 6.complete)
        - "workflow_approved" bedeutet: PLAN vor Implementierung genehmigt
          (pre-execution → 6.approved)
        
        Da workflow_complete bereits priorisiert wird, ist "Implementation Accepted"
        effektiv IGNORIERT. Dies verhindert semantische Verwirrung.
        
        Diese Entscheidung ist BEWUSST und TESTBAR.
        """
        from governance_runtime.kernel.phase_kernel import (
            _detect_phase6_substate_legacy,
            is_phase6_approved,
            is_phase6_terminal
        )
        
        state = {"active_gate": "Implementation Accepted"}
        result = _detect_phase6_substate_legacy(state)
        
        # "Implementation Accepted" maps to nothing directly
        assert result != "6.approved", \
            "Implementation Accepted should NOT map to 6.approved"
        assert result != "6.complete", \
            "Implementation Accepted should NOT map to 6.complete directly"
        assert is_phase6_approved(state) is False
        
        # Without workflow_complete=True, it's not terminal
        assert is_phase6_terminal(state) is False
        
        # The gate is effectively ignored; it falls through to other checks
        # (which will return other substates based on other state flags)

    def test_workflow_complete_takes_priority_over_implementation_accepted(self):
        """Happy: workflow_complete hat Priorität über "Implementation Accepted".
        
        Wenn beide gesetzt sind (workflow_complete und Implementation Accepted gate),
        wird workflow_complete verwendet (da es zuerst geprüft wird).
        
        Dies stellt sicher, dass die explizite workflow_complete-Flag
        als autoritative Quelle dient, nicht der Legacy-Gate-String.
        """
        from governance_runtime.kernel.phase_kernel import (
            _detect_phase6_substate_legacy,
            is_phase6_terminal
        )
        
        state = {
            "active_gate": "Implementation Accepted",
            "workflow_complete": True
        }
        result = _detect_phase6_substate_legacy(state)
        
        # workflow_complete is checked first, so this takes priority
        assert result == "6.complete", \
            "workflow_complete should take priority over Implementation Accepted"
        assert is_phase6_terminal(state) is True

    def test_legacy_returns_6_for_unknown_state(self):
        """Happy: Legacy gibt "6" für unbekannten State zurück.
        
        Ein komplett leerer State soll "6" (unknown) zurückgeben,
        NICHT "6.internal_review". Die Bridge soll nur dann einen
        konkreten Substate inferieren, wenn echte Phase-6-Indikatoren
        vorhanden sind.
        """
        from governance_runtime.kernel.phase_kernel import _detect_phase6_substate_legacy
        
        state = {}
        result = _detect_phase6_substate_legacy(state)
        assert result == "6", f"Empty state should return '6' (unknown), got {result}"
    
    def test_legacy_fallback_to_internal_review_with_phase_context(self):
        """Happy: Legacy Fallback zu 6.internal_review bei Phase-6-Kontext.
        
        Wenn Phase-6-Kontext vorhanden ist (phase_transition_evidence),
        soll die Bridge 6.internal_review inferieren.
        """
        from governance_runtime.kernel.phase_kernel import _detect_phase6_substate_legacy
        
        state = {"phase_transition_evidence": True}
        result = _detect_phase6_substate_legacy(state)
        assert result == "6.internal_review"


class TestPhase6SubstateHelpers:
    """Tests für die is_phase6_* Helper-Funktionen."""

    def test_is_terminal_returns_true_for_complete(self):
        """Happy: is_phase6_terminal True für 6.complete."""
        from governance_runtime.kernel.phase_kernel import is_phase6_terminal
        
        state = {"workflow_complete": True}
        assert is_phase6_terminal(state) is True

    def test_is_terminal_returns_false_for_execution(self):
        """Happy: is_phase6_terminal False für 6.execution."""
        from governance_runtime.kernel.phase_kernel import is_phase6_terminal
        
        state = {"implementation_execution_status": "in_progress"}
        assert is_phase6_terminal(state) is False

    def test_is_approved_returns_true_for_workflow_approved(self):
        """Happy: is_phase6_approved True für workflow_approved flag."""
        from governance_runtime.kernel.phase_kernel import is_phase6_approved
        
        state = {"workflow_approved": True}
        assert is_phase6_approved(state) is True

    def test_is_approved_returns_false_for_implementation_accepted(self):
        """NEGATIVE: is_phase6_approved False für "Implementation Accepted".
        
        "Implementation Accepted" bedeutet Ergebnis akzeptiert (post-execution).
        6.approved bedeutet Plan genehmigt (pre-execution).
        """
        from governance_runtime.kernel.phase_kernel import is_phase6_approved
        
        state = {"active_gate": "Implementation Accepted"}
        assert is_phase6_approved(state) is False

    def test_is_execution_returns_true_for_execution(self):
        """Happy: is_phase6_execution True für Execution Status."""
        from governance_runtime.kernel.phase_kernel import is_phase6_execution
        
        state = {"implementation_execution_status": "in_progress"}
        assert is_phase6_execution(state) is True

    def test_is_blocked_returns_true_for_blocked(self):
        """Happy: is_phase6_blocked True für Blocked Status."""
        from governance_runtime.kernel.phase_kernel import is_phase6_blocked
        
        state = {"implementation_hard_blockers": ["Critical"]}
        assert is_phase6_blocked(state) is True

    def test_is_rejected_returns_true_for_rejected(self):
        """Happy: is_phase6_rejected True für Reject Decision."""
        from governance_runtime.kernel.phase_kernel import is_phase6_rejected
        
        state = {"user_review_decision": "reject"}
        assert is_phase6_rejected(state) is True


class TestPhaseRankWithSubstates:
    """Tests für PHASE_RANK mit Phase 6 Substates."""

    def test_substates_have_higher_rank_than_base(self):
        """Happy: Substates haben höhere Rank als Base Phase 6."""
        from governance_runtime.domain.phase_state_machine import phase_rank
        
        base = phase_rank("6")
        for substate in ["6.internal_review", "6.presentation", "6.execution", 
                          "6.approved", "6.blocked", "6.rework", "6.rejected"]:
            assert phase_rank(substate) > base, f"{substate} should have higher rank than 6"

    def test_complete_has_highest_rank(self):
        """Happy: 6.complete hat höchste Rank (Terminalmarker)."""
        from governance_runtime.domain.phase_state_machine import phase_rank
        
        assert phase_rank("6.complete") == 99, "6.complete should have rank 99"

    def test_rejected_rank_below_complete(self):
        """Happy: 6.rejected Rank unter 6.complete."""
        from governance_runtime.domain.phase_state_machine import phase_rank
        
        assert phase_rank("6.rejected") < phase_rank("6.complete")
        assert phase_rank("6.rejected") > phase_rank("6")

    def test_substates_are_distinct(self):
        """Happy: Alle Substates haben unterschiedliche Ranks."""
        from governance_runtime.domain.phase_state_machine import phase_rank
        
        ranks = set()
        for substate in ["6.internal_review", "6.presentation", "6.execution", 
                          "6.approved", "6.blocked", "6.rework", "6.rejected"]:
            ranks.add(phase_rank(substate))
        
        assert len(ranks) == 7, "All Phase 6 substates should have distinct ranks"


class TestPhaseTokenWithSubstates:
    """Tests für PhaseToken Literal mit Phase 6 Substates."""

    def test_phase_token_includes_substates(self):
        """Happy: PhaseToken Literal enthält alle Substates."""
        from governance_runtime.domain.phase_state_machine import PhaseToken
        
        substates = [
            "6.internal_review", "6.presentation", "6.execution",
            "6.approved", "6.blocked", "6.rework", "6.rejected", "6.complete"
        ]
        
        for substate in substates:
            token: PhaseToken = substate
            assert token == substate

    def test_normalize_phase_token_recognizes_substates(self):
        """Happy: normalize_phase_token erkennt Substates."""
        from governance_runtime.domain.phase_state_machine import normalize_phase_token
        
        for substate in ["6.internal_review", "6.presentation", "6.execution",
                          "6.approved", "6.blocked", "6.rework", "6.rejected", "6.complete"]:
            assert normalize_phase_token(substate) == substate


class TestPhaseRequiresTicketInputRegression:
    """Regression tests for phase_requires_ticket_input."""

    def test_phase_4_requires_ticket(self):
        """Happy: Phase 4 requires ticket."""
        from governance_runtime.domain.phase_state_machine import phase_requires_ticket_input
        assert phase_requires_ticket_input("4") is True

    def test_phase_5_requires_ticket(self):
        """Happy: Phase 5 requires ticket."""
        from governance_runtime.domain.phase_state_machine import phase_requires_ticket_input
        assert phase_requires_ticket_input("5") is True

    def test_phase_5_substates_require_ticket(self):
        """Happy: Phase 5 substates require ticket."""
        from governance_runtime.domain.phase_state_machine import phase_requires_ticket_input
        assert phase_requires_ticket_input("5.3") is True
        assert phase_requires_ticket_input("5.6") is True

    def test_phase_6_does_not_require_ticket(self):
        """Happy: Phase 6 (base and all substates) does not require ticket."""
        from governance_runtime.domain.phase_state_machine import phase_requires_ticket_input
        assert phase_requires_ticket_input("6") is False
        for substate in ["6.internal_review", "6.presentation", "6.execution",
                          "6.approved", "6.blocked", "6.rework", "6.rejected", "6.complete"]:
            assert phase_requires_ticket_input(substate) is False, f"{substate} should not require ticket"

    def test_phase_1_3_do_not_require_ticket(self):
        """Happy: Phase 1-3 do not require ticket."""
        from governance_runtime.domain.phase_state_machine import phase_requires_ticket_input
        assert phase_requires_ticket_input("1") is False
        assert phase_requires_ticket_input("1.1") is False
        assert phase_requires_ticket_input("2") is False
        assert phase_requires_ticket_input("3A") is False
        assert phase_requires_ticket_input("3B-1") is False

    def test_unknown_does_not_require_ticket(self):
        """Edge: Unknown phase does not require ticket."""
        from governance_runtime.domain.phase_state_machine import phase_requires_ticket_input
        assert phase_requires_ticket_input("unknown") is False
        assert phase_requires_ticket_input("") is False
