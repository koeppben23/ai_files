"""Phase 7: Runtime Executor Substate Tests (v4)

Tests für die Phase 6 Substate-Detection-Funktionen im Runtime-Executor.
Kanonische Resolver ohne Legacy-Bridge - alle Sessions müssen phase6_state setzen.
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
    
    def test_resolve_returns_6_when_no_phase6_state(self):
        """Happy: resolve_phase6_substate gibt "6" wenn kein phase6_state gesetzt.
        
        Ohne phase6_state Feld soll "6" (unknown) zurückgegeben werden.
        Die Legacy-Bridge ist entfernt - Sessions müssen phase6_state setzen.
        """
        from governance_runtime.kernel.phase_kernel import resolve_phase6_substate
        
        state = {"phase_transition_evidence": True}
        assert resolve_phase6_substate(state) == "6"

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




class TestPhase6SubstateHelpers:
    """Tests für die is_phase6_* Helper-Funktionen."""

    def test_is_terminal_returns_true_for_complete(self):
        """Happy: is_phase6_terminal True für 6.complete."""
        from governance_runtime.kernel.phase_kernel import is_phase6_terminal
        
        state = {"phase6_state": "6.complete"}
        assert is_phase6_terminal(state) is True

    def test_is_terminal_returns_false_for_execution(self):
        """Happy: is_phase6_terminal False für 6.execution."""
        from governance_runtime.kernel.phase_kernel import is_phase6_terminal
        
        state = {"implementation_execution_status": "in_progress"}
        assert is_phase6_terminal(state) is False

    def test_is_approved_returns_true_for_6_approved(self):
        """Happy: is_phase6_approved True für 6.approved."""
        from governance_runtime.kernel.phase_kernel import is_phase6_approved
        
        state = {"phase6_state": "6.approved"}
        assert is_phase6_approved(state) is True

    def test_is_approved_returns_false_for_implementation_accepted(self):
        """NEGATIVE: is_phase6_approved False für "Implementation Accepted".
        
        "Implementation Accepted" bedeutet Ergebnis akzeptiert (post-execution).
        6.approved bedeutet Plan genehmigt (pre-execution).
        """
        from governance_runtime.kernel.phase_kernel import is_phase6_approved
        
        state = {"active_gate": "Implementation Accepted"}
        assert is_phase6_approved(state) is False

    def test_is_execution_returns_true_for_6_execution(self):
        """Happy: is_phase6_execution True für 6.execution."""
        from governance_runtime.kernel.phase_kernel import is_phase6_execution
        
        state = {"phase6_state": "6.execution"}
        assert is_phase6_execution(state) is True

    def test_is_blocked_returns_true_for_6_blocked(self):
        """Happy: is_phase6_blocked True für 6.blocked."""
        from governance_runtime.kernel.phase_kernel import is_phase6_blocked
        
        state = {"phase6_state": "6.blocked"}
        assert is_phase6_blocked(state) is True

    def test_is_rejected_returns_true_for_6_rejected(self):
        """Happy: is_phase6_rejected True für 6.rejected."""
        from governance_runtime.kernel.phase_kernel import is_phase6_rejected
        
        state = {"phase6_state": "6.rejected"}
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
