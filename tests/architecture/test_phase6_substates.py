"""Phase 6: Substate Prohibition Tests (v1)

Tests für das, was NICHT erlaubt ist zwischen Phase 6 Substates:
- Falsche Commands in bestimmten Substates
- Doppelte Entscheidungen
- Inkonsistente Flag-Kombinationen
- Terminal State Protection

Diese Tests validieren die NEGATIVE Logik der Substate-Maschine.
"""

from __future__ import annotations

import pytest
import yaml
from pathlib import Path


# ============================================================================
# Fixtures
# ============================================================================

def _find_command_policy_path() -> Path | None:
    """Find command_policy.yaml relative to test file location."""
    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / "governance_spec" / "command_policy.yaml"
        if candidate.exists():
            return candidate
    return None


def _find_topology_path() -> Path | None:
    """Find topology.yaml relative to test file location."""
    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / "governance_spec" / "topology.yaml"
        if candidate.exists():
            return candidate
    return None


@pytest.fixture
def command_policy():
    """Load command_policy.yaml."""
    cp_path = _find_command_policy_path()
    if cp_path is None:
        pytest.skip("command_policy.yaml not found")
    with open(cp_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture
def topology():
    """Load topology.yaml."""
    topo_path = _find_topology_path()
    if topo_path is None:
        pytest.skip("topology.yaml not found")
    with open(topo_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture
def commands_by_allowed_state(command_policy):
    """Map command to allowed states."""
    result = {}  # command -> set of allowed states
    for cmd in command_policy.get("commands", []):
        allowed_in = cmd.get("allowed_in", [])
        if allowed_in == "*":
            result[cmd["command"]] = {"*"}
        elif isinstance(allowed_in, list):
            result[cmd["command"]] = set(allowed_in)
    return result


@pytest.fixture
def command_restrictions(command_policy):
    """Extract all command restrictions."""
    return command_policy.get("command_restrictions", [])


# ============================================================================
# Command Restriction Tests
# ============================================================================

@pytest.mark.governance
class TestTerminalStateProtection:
    """6.complete terminal state must be hard protected."""

    def test_6_complete_is_terminal(self, topology):
        """Happy: 6.complete ist terminal."""
        state = next((s for s in topology["states"] if s["id"] == "6.complete"), None)
        assert state is not None, "6.complete must exist"
        assert state["terminal"] is True, "6.complete must have terminal=true"

    def test_6_complete_has_no_transitions(self, topology):
        """Happy: 6.complete hat keine Transitions."""
        state = next((s for s in topology["states"] if s["id"] == "6.complete"), None)
        assert state is not None
        assert len(state.get("transitions", [])) == 0, \
            "6.complete must have no transitions"

    def test_no_mutating_commands_allowed_in_6_complete(self, command_policy):
        """Runtime: Keine mutierenden Commands in 6.complete erlaubt."""
        restrictions = command_policy.get("command_restrictions", [])
        
        # Find restriction for 6.complete or terminal states
        complete_restriction = None
        for r in restrictions:
            if r.get("state_pattern") == "6.complete":
                complete_restriction = r
                break
        
        assert complete_restriction is not None, \
            "6.complete must have explicit command restriction"
        
        blocked_types = set(complete_restriction.get("blocked_command_types", []))
        blocked_cmds = set(complete_restriction.get("blocked_commands", []))
        
        # Must block all mutating command types
        assert "persist_evidence" in blocked_types, "/ticket, /plan blocked"
        assert "start_implementation" in blocked_types, "/implement blocked"
        assert "submit_review_decision" in blocked_types, "/review-decision blocked"
        assert "advance_routing" in blocked_types, "/continue blocked"
        
        # Must block specific commands
        assert "/continue" in blocked_cmds, "/continue blocked in terminal"
        assert "/implement" in blocked_cmds, "/implement blocked in terminal"

    def test_no_output_allowed_in_6_complete_except_readonly(self, command_policy):
        """Runtime: Nur read-only Output in 6.complete erlaubt."""
        output_policies = command_policy.get("output_policies", [])
        
        complete_policy = next(
            (p for p in output_policies if p.get("state_id") == "6.complete"),
            None
        )
        
        assert complete_policy is not None, "6.complete must have output policy"
        
        forbidden = set(complete_policy.get("forbidden_output_classes", []))
        assert "implementation" in forbidden, "No implementation in terminal"
        assert "plan" in forbidden, "No plan in terminal"
        assert "code_delivery" in forbidden, "No code delivery in terminal"


@pytest.mark.governance
class TestRejectedStateSemantics:
    """6.rejected transitional state semantics."""

    def test_6_rejected_is_not_terminal(self, topology):
        """Happy: 6.rejected ist NICHT terminal."""
        state = next((s for s in topology["states"] if s["id"] == "6.rejected"), None)
        assert state is not None
        assert state["terminal"] is False, "6.rejected must not be terminal"

    def test_6_rejected_has_return_transition(self, topology):
        """Happy: 6.rejected hat Transition zu Phase 4."""
        state = next((s for s in topology["states"] if s["id"] == "6.rejected"), None)
        assert state is not None
        
        targets = [t["target"] for t in state.get("transitions", [])]
        assert "4" in targets, "6.rejected must transition to Phase 4"

    def test_6_rejected_requires_continue(self, command_restrictions):
        """Runtime: 6.rejected erfordert /continue für Rückweg."""
        rejected_restriction = None
        for r in command_restrictions:
            if r.get("state_pattern") == "6.rejected":
                rejected_restriction = r
                break
        
        assert rejected_restriction is not None, "6.rejected must have restriction"
        
        blocked = set(rejected_restriction.get("blocked_commands", []))
        blocked_types = set(rejected_restriction.get("blocked_command_types", []))
        
        # No decision commands in rejected
        assert "/review-decision" in blocked, "No review-decision in rejected"
        assert "/implementation-decision" in blocked, "No implementation-decision in rejected"
        assert "submit_review_decision" in blocked_types

    def test_6_rejected_no_implementation_commands(self, command_restrictions):
        """Runtime: Keine Implementation-Commands in 6.rejected."""
        rejected_restriction = None
        for r in command_restrictions:
            if r.get("state_pattern") == "6.rejected":
                rejected_restriction = r
                break
        
        assert rejected_restriction is not None
        blocked_types = set(rejected_restriction.get("blocked_command_types", []))
        assert "start_implementation" in blocked_types, "No /implement in rejected"


@pytest.mark.governance
class TestSubstateCommandProhibitions:
    """Commands, die in bestimmten Substates verboten sind."""

    def test_no_implement_in_6_presentation(self, commands_by_allowed_state):
        """Runtime: /implement NICHT erlaubt in 6.presentation."""
        # /implement should NOT be allowed in presentation
        implement_allowed = commands_by_allowed_state.get("/implement", set())
        if "*" not in implement_allowed:
            assert "6.presentation" not in implement_allowed, \
                "/implement should not be allowed in 6.presentation"

    def test_no_review_decision_in_6_execution(self, commands_by_allowed_state):
        """Runtime: /review-decision NICHT erlaubt in 6.execution."""
        review_allowed = commands_by_allowed_state.get("/review-decision", set())
        if "*" not in review_allowed:
            assert "6.execution" not in review_allowed, \
                "/review-decision should not be allowed in 6.execution"

    def test_no_ticket_plan_in_phase6_except_6_rejected(self, commands_by_allowed_state, command_restrictions):
        """Runtime: /ticket, /plan in Phase 6 nur via restrictions."""
        # In Phase 6, /ticket and /plan should be restricted
        # except possibly in 6.rejected (via restrictions)
        
        restrictions = {r.get("state_pattern"): r for r in command_restrictions}
        
        # Check that terminal states block persist_evidence
        terminal_restriction = restrictions.get("*.terminal", {})
        blocked_types = set(terminal_restriction.get("blocked_command_types", []))
        assert "persist_evidence" in blocked_types, \
            "persist_evidence blocked in terminal states"


@pytest.mark.governance
class TestBlockedStateRestrictions:
    """6.blocked state restrictions."""

    def test_6_blocked_no_review_decision(self, command_restrictions):
        """Runtime: Keine Review-Entscheidung wenn blocked."""
        blocked_restriction = None
        for r in command_restrictions:
            if r.get("state_pattern") == "6.blocked":
                blocked_restriction = r
                break
        
        assert blocked_restriction is not None, "6.blocked must have restriction"
        
        blocked = set(blocked_restriction.get("blocked_commands", []))
        assert "/review-decision" in blocked, "No approval while blocked"
        assert "/implementation-decision" in blocked, "No approval while blocked"


@pytest.mark.governance
class TestApprovedStateRestrictions:
    """6.approved transitional state restrictions."""

    def test_6_approved_only_implement_allowed(self, commands_by_allowed_state):
        """Runtime: In 6.approved nur /implement erlaubt."""
        implement_allowed = commands_by_allowed_state.get("/implement", set())
        
        # /implement should be allowed in 6.approved
        if "*" not in implement_allowed:
            assert "6.approved" in implement_allowed, \
                "/implement must be allowed in 6.approved"

    def test_6_approved_no_review_decision(self, commands_by_allowed_state):
        """Runtime: Keine Review-Entscheidung in 6.approved."""
        review_allowed = commands_by_allowed_state.get("/review-decision", set())
        if "*" not in review_allowed:
            assert "6.approved" not in review_allowed, \
                "/review-decision should not be allowed in 6.approved"


@pytest.mark.governance
class TestExecutionStateRestrictions:
    """6.execution state restrictions."""

    def test_6_approved_implement_allowed(self, commands_by_allowed_state):
        """Runtime: /implement only in 6.approved (start implementation)."""
        implement_allowed = commands_by_allowed_state.get("/implement", set())
        
        if "*" not in implement_allowed:
            assert "6.approved" in implement_allowed, \
                "/implement must be allowed in 6.approved"
            assert "6.execution" not in implement_allowed, \
                "/implement should not be in 6.execution (use /retry_implementation)"

    def test_retry_implementation_in_blocked_and_rework(self, commands_by_allowed_state):
        """Runtime: /retry_implementation in 6.blocked and 6.rework."""
        retry_allowed = commands_by_allowed_state.get("/retry_implementation", set())
        
        assert "6.blocked" in retry_allowed, \
            "/retry_implementation must be allowed in 6.blocked"
        assert "6.rework" in retry_allowed, \
            "/retry_implementation must be allowed in 6.rework"

    def test_6_execution_no_review_decision(self, commands_by_allowed_state):
        """Runtime: Keine Review-Entscheidung in 6.execution."""
        review_allowed = commands_by_allowed_state.get("/review-decision", set())
        if "*" not in review_allowed:
            assert "6.execution" not in review_allowed, \
                "/review-decision should not be allowed in 6.execution"


@pytest.mark.governance
class TestSubstateConsistency:
    """Konsistenz-Checks für Substate-Architektur."""

    def test_no_command_allowed_in_terminal_states(self, command_policy):
        """Runtime: Kein mutierender Command in terminal States."""
        states = command_policy.get("commands", [])
        terminal_restriction = None
        
        for r in command_policy.get("command_restrictions", []):
            if r.get("state_pattern") == "*.terminal":
                terminal_restriction = r
                break
        
        assert terminal_restriction is not None, \
            "Must have terminal state restriction"

    def test_6_complete_explicitly_blocked(self, command_restrictions):
        """Runtime: 6.complete muss explizit blockiert sein."""
        complete_restriction = None
        for r in command_restrictions:
            if r.get("state_pattern") == "6.complete":
                complete_restriction = r
                break
        
        assert complete_restriction is not None, \
            "6.complete must have explicit restriction"

    def test_all_phase6_substates_have_parent(self, topology):
        """Happy: Alle Phase 6 Substates haben parent='6'."""
        substates = [
            "6.internal_review", "6.presentation", "6.execution",
            "6.approved", "6.blocked", "6.rework", "6.rejected", "6.complete"
        ]
        
        for substate_id in substates:
            state = next((s for s in topology["states"] if s["id"] == substate_id), None)
            if state:
                assert state.get("parent") == "6", \
                    f"Substate {substate_id} must have parent='6'"
