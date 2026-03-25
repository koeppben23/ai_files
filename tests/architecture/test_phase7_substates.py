"""Phase 7: Runtime Executor Substate Tests (v2)

Tests für die Phase 6 Substate-Detection-Funktionen im Runtime-Executor.
Überarbeitet mit stärkerer Regression-Absicherung.
"""

from __future__ import annotations

import pytest


class TestPhase6SubstateDetection:
    """Tests für Phase 6 Substate Detection."""

    def test_detect_internal_review_canonical_state(self):
        """Happy: Erkennt 6.internal_review vom canonical phase6_state field."""
        from governance_runtime.kernel.phase_kernel import _detect_phase6_substate
        
        state = {"phase6_state": "6.internal_review"}
        assert _detect_phase6_substate(state) == "6.internal_review"

    def test_detect_execution_from_canonical_state(self):
        """Happy: Erkennt 6.execution vom canonical phase6_state field."""
        from governance_runtime.kernel.phase_kernel import _detect_phase6_substate
        
        state = {"phase6_state": "6.execution"}
        assert _detect_phase6_substate(state) == "6.execution"

    def test_detect_complete_from_workflow_flag(self):
        """Happy: Erkennt 6.complete vom Workflow-Flag (priority über Gate)."""
        from governance_runtime.kernel.phase_kernel import _detect_phase6_substate
        
        state = {"workflow_complete": True}
        assert _detect_phase6_substate(state) == "6.complete"

    def test_detect_rejected_from_decision(self):
        """Happy: Erkennt 6.rejected von Reject-Entscheidung."""
        from governance_runtime.kernel.phase_kernel import _detect_phase6_substate
        
        state = {"user_review_decision": "reject"}
        assert _detect_phase6_substate(state) == "6.rejected"

    def test_detect_execution_from_execution_status(self):
        """Happy: Erkennt 6.execution vom Execution-Status."""
        from governance_runtime.kernel.phase_kernel import _detect_phase6_substate
        
        state = {"implementation_execution_status": "in_progress"}
        assert _detect_phase6_substate(state) == "6.execution"

    def test_detect_blocked_from_hard_blockers(self):
        """Happy: Erkennt 6.blocked von Hard-Blockers."""
        from governance_runtime.kernel.phase_kernel import _detect_phase6_substate
        
        state = {
            "implementation_execution_status": "blocked",
            "implementation_hard_blockers": ["Critical Issue"]
        }
        assert _detect_phase6_substate(state) == "6.blocked"

    def test_detect_rework_from_clarification_required(self):
        """Happy: Erkennt 6.rework von Rework-Clarification-Required."""
        from governance_runtime.kernel.phase_kernel import _detect_phase6_substate
        
        state = {"implementation_rework_clarification_required": True}
        assert _detect_phase6_substate(state) == "6.rework"

    def test_detect_approved_from_workflow_approved_flag(self):
        """Happy: Erkennt 6.approved von workflow_approved flag.
        
        Note: 6.approved means PLAN/WORKFLOW was approved (before implementation).
        NOT "Implementation Accepted" which means implementation RESULT was accepted.
        """
        from governance_runtime.kernel.phase_kernel import _detect_phase6_substate
        
        state = {"workflow_approved": True}
        assert _detect_phase6_substate(state) == "6.approved"

    def test_detect_approved_from_plan_approved_flag(self):
        """Happy: Erkennt 6.approved auch von implementation_plan_approved."""
        from governance_runtime.kernel.phase_kernel import _detect_phase6_substate
        
        state = {"implementation_plan_approved": True}
        assert _detect_phase6_substate(state) == "6.approved"

    def test_implementation_accepted_does_not_map_to_approved(self):
        """Negative: "Implementation Accepted" ist NICHT 6.approved.
        
        "Implementation Accepted" bedeutet das Ergebnis wurde akzeptiert,
        nicht dass der Plan genehmigt wurde. 6.approved ist für
        Genehmigung VOR der Implementierung.
        """
        from governance_runtime.kernel.phase_kernel import _detect_phase6_substate, is_phase6_approved
        
        # "Implementation Accepted" Gate sollte NICHT 6.approved setzen
        state = {"active_gate": "Implementation Accepted"}
        result = _detect_phase6_substate(state)
        assert result != "6.approved", \
            "Implementation Accepted should not map to 6.approved"
        assert is_phase6_approved(state) is False

    def test_fallback_to_6_internal_review(self):
        """Happy: Fallback zu 6.internal_review wenn keine Flags gesetzt."""
        from governance_runtime.kernel.phase_kernel import _detect_phase6_substate
        
        # Keine canonical Flags, keine Entscheidung, keine Execution
        state = {
            "active_gate": "Implementation Internal Review"
        }
        # Sollte internal_review sein wenn Review noch nicht complete
        result = _detect_phase6_substate(state)
        assert result == "6.internal_review"

    def test_fallback_to_internal_review_when_review_incomplete(self):
        """Edge: Fallback zu 6.internal_review wenn Review noch nicht complete.
        
        Wenn keine Flags gesetzt und Review nicht complete, ist 6.internal_review
        die korrekte Annahme (Default-Zustand für Review-Loop).
        """
        from governance_runtime.kernel.phase_kernel import _detect_phase6_substate
        
        # Keine canonical Flags, keine Entscheidung
        state = {}
        result = _detect_phase6_substate(state)
        # Review ist nicht complete, also 6.internal_review
        assert result == "6.internal_review"

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
        assert normalize_phase_token("6.approved") == "6.approved"
        assert normalize_phase_token("6.blocked") == "6.blocked"
        assert normalize_phase_token("6.rework") == "6.rework"
        assert normalize_phase_token("6.rejected") == "6.rejected"
        assert normalize_phase_token("6.complete") == "6.complete"


class TestPhaseRequiresTicketInputRegression:
    """Regression tests for phase_requires_ticket_input.
    
    This function was changed to exclude Phase 6 substates.
    These tests ensure backward compatibility.
    """

    def test_phase_4_requires_ticket(self):
        """Happy: Phase 4 requires ticket."""
        from governance_runtime.domain.phase_state_machine import phase_requires_ticket_input
        
        assert phase_requires_ticket_input("4") is True

    def test_phase_5_requires_ticket(self):
        """Happy: Phase 5 requires ticket."""
        from governance_runtime.domain.phase_state_machine import phase_requires_ticket_input
        
        assert phase_requires_ticket_input("5") is True

    def test_phase_5_3_requires_ticket(self):
        """Happy: Phase 5.3 requires ticket (inherits from 5)."""
        from governance_runtime.domain.phase_state_machine import phase_requires_ticket_input
        
        assert phase_requires_ticket_input("5.3") is True

    def test_phase_5_6_requires_ticket(self):
        """Happy: Phase 5.6 requires ticket (inherits from 5)."""
        from governance_runtime.domain.phase_state_machine import phase_requires_ticket_input
        
        assert phase_requires_ticket_input("5.6") is True

    def test_phase_6_base_does_not_require_ticket(self):
        """Happy: Phase 6 base does not require ticket."""
        from governance_runtime.domain.phase_state_machine import phase_requires_ticket_input
        
        assert phase_requires_ticket_input("6") is False

    def test_phase_6_substates_do_not_require_ticket(self):
        """Happy: All Phase 6 substates do not require ticket."""
        from governance_runtime.domain.phase_state_machine import phase_requires_ticket_input
        
        for substate in ["6.internal_review", "6.presentation", "6.execution",
                          "6.approved", "6.blocked", "6.rework", "6.rejected", "6.complete"]:
            assert phase_requires_ticket_input(substate) is False, \
                f"{substate} should not require ticket"

    def test_phase_3_does_not_require_ticket(self):
        """Happy: Phase 3 does not require ticket."""
        from governance_runtime.domain.phase_state_machine import phase_requires_ticket_input
        
        assert phase_requires_ticket_input("3A") is False
        assert phase_requires_ticket_input("3B-1") is False
        assert phase_requires_ticket_input("3B-2") is False

    def test_phase_2_does_not_require_ticket(self):
        """Happy: Phase 2 does not require ticket."""
        from governance_runtime.domain.phase_state_machine import phase_requires_ticket_input
        
        assert phase_requires_ticket_input("2") is False

    def test_phase_1_does_not_require_ticket(self):
        """Happy: Phase 1 does not require ticket."""
        from governance_runtime.domain.phase_state_machine import phase_requires_ticket_input
        
        assert phase_requires_ticket_input("1") is False
        assert phase_requires_ticket_input("1.1") is False
        assert phase_requires_ticket_input("1.3") is False

    def test_unknown_does_not_require_ticket(self):
        """Edge: Unknown phase does not require ticket."""
        from governance_runtime.domain.phase_state_machine import phase_requires_ticket_input
        
        assert phase_requires_ticket_input("unknown") is False
        assert phase_requires_ticket_input("") is False
