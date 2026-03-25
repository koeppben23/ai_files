"""Runtime Integration Tests for Command Policy (WP1).

These tests prove that command_policy.yaml is the authoritative source
for command validation in the runtime. They test the actual runtime path
through validate_command_for_execution() in phase_kernel.py.
"""

from __future__ import annotations

import pytest

from governance_runtime.kernel.phase_kernel import validate_command_for_execution
from governance_runtime.kernel.command_policy_loader import (
    CommandNotFoundError,
    CommandNotAllowedError,
    enforce_command_policy,
    validate_command,
)


class TestPublicAPIConsistency:
    """Verify that phase_kernel helper uses public API, not internals."""

    def test_validate_command_for_execution_delegates_to_public_api(self):
        """The phase_kernel helper must use enforce_command_policy()."""
        # Both should return the same result
        result1 = validate_command_for_execution("6.approved", "/implement")
        result2 = enforce_command_policy("6.approved", "/implement")
        result3 = validate_command("6.approved", "/implement")
        
        assert result1.command == result2.command == result3.command
        assert result1.id == result2.id == result3.id

    def test_validate_command_for_execution_fail_closed(self):
        """Phase kernel helper raises same errors as public API."""
        # Unknown command
        with pytest.raises(CommandNotFoundError):
            validate_command_for_execution("6.approved", "/unknown")
        
        # Disallowed command
        with pytest.raises(CommandNotAllowedError):
            validate_command_for_execution("6.execution", "/implement")


class TestPhaseKernelCommandValidation:
    """Integration Tests: Command validation in phase_kernel.py runtime path.
    
    These tests prove that the runtime kernel validates commands against
    command_policy.yaml before execution.
    """

    def test_implement_allowed_in_6_approved(self):
        """Runtime: /implement passes validation in 6.approved."""
        result = validate_command_for_execution("6.approved", "/implement")
        
        assert result.command == "/implement"
        assert result.mutating is True
        assert "implementation_started" in result.produces_events

    def test_implement_blocked_in_6_execution(self):
        """Runtime: /implement fails validation in 6.execution."""
        with pytest.raises(CommandNotAllowedError) as exc_info:
            validate_command_for_execution("6.execution", "/implement")
        
        assert "/implement" in str(exc_info.value)
        assert "6.execution" in str(exc_info.value)

    def test_unknown_command_fails_in_any_state(self):
        """Runtime: Unknown command fails with CommandNotFoundError."""
        with pytest.raises(CommandNotFoundError) as exc_info:
            validate_command_for_execution("6.approved", "/nonexistent_command")
        
        assert "not found" in str(exc_info.value).lower()
        assert "command_policy.yaml" in str(exc_info.value)

    def test_continue_allowed_in_execution(self):
        """Runtime: /continue allowed in 6.execution (wildcard)."""
        result = validate_command_for_execution("6.execution", "/continue")
        
        assert result.command == "/continue"

    def test_continue_blocked_in_terminal(self):
        """Runtime: /continue blocked in 6.complete (terminal restriction)."""
        with pytest.raises(CommandNotAllowedError):
            validate_command_for_execution("6.complete", "/continue")

    def test_review_always_allowed(self):
        """Runtime: /review allowed in all states (read-only)."""
        for state in ["0", "4", "5", "6.approved", "6.execution", "6.complete"]:
            result = validate_command_for_execution(state, "/review")
            assert result.command == "/review"

    def test_review_decision_allowed_in_presentation(self):
        """Runtime: /review-decision allowed in 6.presentation."""
        result = validate_command_for_execution("6.presentation", "/review-decision")
        
        assert result.command == "/review-decision"
        assert "workflow_approved" in result.produces_events

    def test_review_decision_blocked_in_execution(self):
        """Runtime: /review-decision blocked in 6.execution."""
        with pytest.raises(CommandNotAllowedError):
            validate_command_for_execution("6.execution", "/review-decision")

    def test_retry_implementation_in_blocked(self):
        """Runtime: /retry_implementation allowed in 6.blocked."""
        result = validate_command_for_execution("6.blocked", "/retry_implementation")
        
        assert result.command == "/retry_implementation"

    def test_retry_implementation_in_rework(self):
        """Runtime: /retry_implementation allowed in 6.rework."""
        result = validate_command_for_execution("6.rework", "/retry_implementation")
        
        assert result.command == "/retry_implementation"

    def test_retry_implementation_blocked_in_approved(self):
        """Runtime: /retry_implementation blocked in 6.approved."""
        with pytest.raises(CommandNotAllowedError):
            validate_command_for_execution("6.approved", "/retry_implementation")


class TestPhaseKernelCommandValidationMutations:
    """Integration Tests: State changes affect command validity in runtime.
    
    These tests prove that the same command has different validity
    depending on the current state - proving policy is consulted.
    """

    def test_implement_across_states(self):
        """Runtime: /implement validity changes with state."""
        # Allowed in 6.approved
        result = validate_command_for_execution("6.approved", "/implement")
        assert result.mutating is True
        
        # Blocked in 6.execution
        with pytest.raises(CommandNotAllowedError):
            validate_command_for_execution("6.execution", "/implement")
        
        # Blocked in 6.presentation
        with pytest.raises(CommandNotAllowedError):
            validate_command_for_execution("6.presentation", "/implement")
        
        # Blocked in early phases
        with pytest.raises(CommandNotAllowedError):
            validate_command_for_execution("4", "/implement")

    def test_ticket_across_states(self):
        """Runtime: /ticket validity changes with state."""
        # Allowed in 4
        result = validate_command_for_execution("4", "/ticket")
        assert result.mutating is True
        
        # Blocked in 5
        with pytest.raises(CommandNotAllowedError):
            validate_command_for_execution("5", "/ticket")
        
        # Blocked in 6 states
        with pytest.raises(CommandNotAllowedError):
            validate_command_for_execution("6.approved", "/ticket")

    def test_continue_in_terminal_states(self):
        """Runtime: /continue blocked by terminal restrictions."""
        # Allowed in non-terminal states
        for state in ["0", "4", "5", "6.approved", "6.execution"]:
            result = validate_command_for_execution(state, "/continue")
            assert result.command == "/continue"
        
        # Blocked in terminal 6.complete
        with pytest.raises(CommandNotAllowedError):
            validate_command_for_execution("6.complete", "/continue")


class TestPhaseKernelCommandValidationMetadata:
    """Integration Tests: Command metadata from policy is available in runtime.
    
    These tests prove that runtime can access command metadata
    (mutating flag, produces_events) from command_policy.yaml.
    """

    def test_mutating_flag_from_policy(self):
        """Runtime: mutating flag comes from command_policy.yaml."""
        impl = validate_command_for_execution("6.approved", "/implement")
        review = validate_command_for_execution("6.approved", "/review")
        ticket = validate_command_for_execution("4", "/ticket")
        
        assert impl.mutating is True
        assert review.mutating is False
        assert ticket.mutating is True

    def test_produces_events_from_policy(self):
        """Runtime: produces_events comes from command_policy.yaml."""
        impl = validate_command_for_execution("6.approved", "/implement")
        review_decision = validate_command_for_execution("6.presentation", "/review-decision")
        
        assert "implementation_started" in impl.produces_events
        assert "implementation_execution_in_progress" in impl.produces_events
        
        assert "workflow_approved" in review_decision.produces_events
        assert "review_changes_requested" in review_decision.produces_events
        assert "review_rejected" in review_decision.produces_events

    def test_behavior_type_from_policy(self):
        """Runtime: behavior type comes from command_policy.yaml."""
        impl = validate_command_for_execution("6.approved", "/implement")
        plan = validate_command_for_execution("4", "/plan")
        
        assert impl.behavior["type"] == "start_implementation"
        assert plan.behavior["type"] == "persist_evidence"
        assert plan.behavior["evidence_class"] == "plan"

    def test_command_id_from_policy(self):
        """Runtime: command id comes from command_policy.yaml."""
        impl = validate_command_for_execution("6.approved", "/implement")
        continue_cmd = validate_command_for_execution("0", "/continue")
        
        assert impl.id == "cmd_implement"
        assert continue_cmd.id == "cmd_continue"


class TestRealRuntimeIntegration:
    """Integration Tests: Simulate real command handler using policy.
    
    These tests simulate how the runtime would use command validation
    in a real command execution path.
    """

    def test_command_handler_simulation_6_approved(self):
        """Simulate: /implement command handler in 6.approved state."""
        current_state = "6.approved"
        user_command = "/implement"
        
        # Command handler must validate before processing
        cmd_def = validate_command_for_execution(current_state, user_command)
        
        # Handler proceeds with command
        assert cmd_def.mutating is True
        assert "implementation_started" in cmd_def.produces_events

    def test_command_handler_simulation_disallowed(self):
        """Simulate: /implement command handler in wrong state - must fail."""
        current_state = "6.execution"
        user_command = "/implement"
        
        # Command handler validates and fails
        with pytest.raises(CommandNotAllowedError) as exc_info:
            validate_command_for_execution(current_state, user_command)
        
        # Error response would be sent to user
        assert "/implement" in str(exc_info.value)
        assert "6.execution" in str(exc_info.value)

    def test_command_handler_simulation_unknown(self):
        """Simulate: Unknown command - must fail before any processing."""
        current_state = "6.approved"
        user_command = "/magic_command"
        
        # Command handler fails immediately
        with pytest.raises(CommandNotFoundError) as exc_info:
            validate_command_for_execution(current_state, user_command)
        
        # Error includes known commands for helpful message
        assert "command_policy.yaml" in str(exc_info.value)

    def test_command_handler_simulation_terminal_state(self):
        """Simulate: /continue blocked in terminal state by restrictions."""
        current_state = "6.complete"
        user_command = "/continue"
        
        # Even though /continue has allowed_in: "*",
        # command_restrictions override for terminal states
        with pytest.raises(CommandNotAllowedError) as exc_info:
            validate_command_for_execution(current_state, user_command)
        
        assert "terminal" in str(exc_info.value).lower() or "immutable" in str(exc_info.value).lower()

    def test_multiple_commands_in_sequence(self):
        """Simulate: Multiple commands validated in sequence.
        
        This proves each command is validated independently against policy.
        """
        # Sequence: /ticket, /plan, /implement in different states
        results = []
        
        # /ticket in state 4
        cmd1 = validate_command_for_execution("4", "/ticket")
        results.append(("4", "/ticket", True, cmd1.mutating))
        
        # /plan in state 4
        cmd2 = validate_command_for_execution("4", "/plan")
        results.append(("4", "/plan", True, cmd2.mutating))
        
        # /plan in state 5
        cmd3 = validate_command_for_execution("5", "/plan")
        results.append(("5", "/plan", True, cmd3.mutating))
        
        # /implement in 6.approved
        cmd4 = validate_command_for_execution("6.approved", "/implement")
        results.append(("6.approved", "/implement", True, cmd4.mutating))
        
        # All passed
        assert len(results) == 4
        assert all(r[2] for r in results)  # all succeeded

    def test_state_transition_changes_allowed_commands(self):
        """Simulate: State change affects which commands are allowed.
        
        This proves policy is consulted per-state, not cached globally.
        """
        # Same command, different states
        states_and_results = [
            ("4", "/ticket", True),      # allowed
            ("5", "/ticket", False),     # not allowed
            ("6.approved", "/ticket", False),  # not allowed
        ]
        
        for state, command, should_pass in states_and_results:
            if should_pass:
                result = validate_command_for_execution(state, command)
                assert result.command == command
            else:
                with pytest.raises(CommandNotAllowedError):
                    validate_command_for_execution(state, command)
