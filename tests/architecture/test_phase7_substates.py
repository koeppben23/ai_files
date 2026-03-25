"""Phase 7: Runtime Executor Substate Tests (v1)

Tests für die Phase 6 Substate-Detection-Funktionen im Runtime-Executor.
"""

from __future__ import annotations

import pytest


class TestPhase6SubstateDetection:
    """Tests für Phase 6 Substate Detection."""

    def test_detect_internal_review_from_gate(self):
        """Happy: Erkennt 6.internal_review vom Gate."""
        from governance_runtime.kernel.phase_kernel import _detect_phase6_substate
        
        state = {"active_gate": "Implementation Internal Review"}
        assert _detect_phase6_substate(state) == "6.internal_review"

    def test_detect_presentation_from_gate(self):
        """Happy: Erkennt 6.presentation vom Gate."""
        from governance_runtime.kernel.phase_kernel import _detect_phase6_substate
        
        state = {"active_gate": "Evidence Presentation Gate"}
        assert _detect_phase6_substate(state) == "6.presentation"

    def test_detect_execution_from_status(self):
        """Happy: Erkennt 6.execution vom Execution-Status."""
        from governance_runtime.kernel.phase_kernel import _detect_phase6_substate
        
        state = {"implementation_execution_status": "in_progress"}
        assert _detect_phase6_substate(state) == "6.execution"

    def test_detect_complete_from_workflow_flag(self):
        """Happy: Erkennt 6.complete vom Workflow-Flag."""
        from governance_runtime.kernel.phase_kernel import _detect_phase6_substate
        
        state = {"workflow_complete": True}
        assert _detect_phase6_substate(state) == "6.complete"

    def test_detect_blocked_from_gate(self):
        """Happy: Erkennt 6.blocked vom Gate."""
        from governance_runtime.kernel.phase_kernel import _detect_phase6_substate
        
        state = {"active_gate": "Implementation Blocked"}
        assert _detect_phase6_substate(state) == "6.blocked"

    def test_detect_rejected_from_decision(self):
        """Happy: Erkennt 6.rejected von Reject-Entscheidung."""
        from governance_runtime.kernel.phase_kernel import _detect_phase6_substate
        
        state = {"user_review_decision": "reject"}
        assert _detect_phase6_substate(state) == "6.rejected"

    def test_detect_from_phase6_state_field(self):
        """Happy: Erkennt direkt vom phase6_state Field."""
        from governance_runtime.kernel.phase_kernel import _detect_phase6_substate
        
        state = {"phase6_state": "6.execution"}
        assert _detect_phase6_substate(state) == "6.execution"

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

    def test_is_approved_returns_true_for_accepted(self):
        """Happy: is_phase6_approved True für "Implementation Accepted" Gate."""
        from governance_runtime.kernel.phase_kernel import is_phase6_approved
        
        state = {"active_gate": "Implementation Accepted"}
        assert is_phase6_approved(state) is True

    def test_is_execution_returns_true_for_execution(self):
        """Happy: is_phase6_execution True für Execution Status."""
        from governance_runtime.kernel.phase_kernel import is_phase6_execution
        
        state = {"implementation_execution_status": "in_progress"}
        assert is_phase6_execution(state) is True

    def test_is_blocked_returns_true_for_blocked(self):
        """Happy: is_phase6_blocked True für Blocked Gate."""
        from governance_runtime.kernel.phase_kernel import is_phase6_blocked
        
        state = {"active_gate": "Implementation Blocked"}
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
        """Happy: 6.complete hat höchste Rank."""
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
            token: PhaseToken = substate  # Type check
            assert token == substate

    def test_normalize_phase_token_recognizes_substates(self):
        """Happy: normalize_phase_token erkennt Substates."""
        from governance_runtime.domain.phase_state_machine import normalize_phase_token
        
        assert normalize_phase_token("6.execution") == "6.execution"
        assert normalize_phase_token("6.presentation") == "6.presentation"
        assert normalize_phase_token("6.internal_review") == "6.internal_review"

    def test_phase_requires_ticket_input_still_works(self):
        """Happy: phase_requires_ticket_input funktioniert noch."""
        from governance_runtime.domain.phase_state_machine import phase_requires_ticket_input
        
        assert phase_requires_ticket_input("6") is False
        assert phase_requires_ticket_input("6.execution") is False
        assert phase_requires_ticket_input("4") is True
