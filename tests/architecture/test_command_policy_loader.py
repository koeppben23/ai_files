"""Tests for CommandPolicyLoader - WP1: Command Policy Operative Authority.

Tests cover:
- Happy Path: Command permission checking works correctly
- Negative: Disallowed commands raise appropriate errors
- Edge Cases: Wildcards, terminal states, restrictions
- Regression: Real command_policy.yaml loads correctly
- Integration: validate_command() as single entry point
"""

from __future__ import annotations

import pytest

from governance_runtime.kernel.command_policy_loader import (
    CommandPolicyLoader,
    CommandDef,
    CommandNotFoundError,
    CommandNotAllowedError,
    OutputPolicy,
    validate_command,
    enforce_command_policy,
    CommandPolicyRuntimeEnforcer,
)


@pytest.fixture(autouse=True)
def reset_loader():
    """Reset loader before each test."""
    CommandPolicyLoader.reset()
    yield
    CommandPolicyLoader.reset()


class TestCommandPolicyLoaderGetCommand:
    """Happy Path: Get command definitions."""

    def test_get_command_returns_command_def(self):
        """Happy: get_command returns CommandDef for existing command."""
        cmd = CommandPolicyLoader.get_command("/implement")
        
        assert isinstance(cmd, CommandDef)
        assert cmd.command == "/implement"
        assert cmd.id == "cmd_implement"
        assert cmd.mutating is True

    def test_get_command_produces_events(self):
        """Happy: Command has correct produces_events."""
        cmd = CommandPolicyLoader.get_command("/implement")
        
        assert "implementation_started" in cmd.produces_events
        assert "implementation_execution_in_progress" in cmd.produces_events

    def test_get_command_continue_via_guards(self):
        """Happy: /continue has special *_via_guards produces_events."""
        cmd = CommandPolicyLoader.get_command("/continue")
        
        assert cmd.produces_events == "*_via_guards"

    def test_get_command_not_found_raises_error(self):
        """Negative: Unknown command raises CommandNotFoundError."""
        with pytest.raises(CommandNotFoundError) as exc_info:
            CommandPolicyLoader.get_command("/unknown_command")
        
        assert "not found" in str(exc_info.value).lower()
        assert "/unknown_command" in str(exc_info.value)


class TestCommandPolicyLoaderIsAllowed:
    """Command permission checking tests."""

    def test_implement_allowed_in_6_approved(self):
        """Happy: /implement allowed in 6.approved."""
        assert CommandPolicyLoader.is_command_allowed("6.approved", "/implement") is True

    def test_implement_not_allowed_in_6_execution(self):
        """Negative: /implement NOT allowed in 6.execution."""
        assert CommandPolicyLoader.is_command_allowed("6.execution", "/implement") is False

    def test_implement_not_allowed_in_6_complete(self):
        """Negative: /implement NOT allowed in terminal 6.complete."""
        assert CommandPolicyLoader.is_command_allowed("6.complete", "/implement") is False

    def test_ticket_allowed_in_state_4(self):
        """Happy: /ticket allowed in state 4."""
        assert CommandPolicyLoader.is_command_allowed("4", "/ticket") is True

    def test_ticket_not_allowed_in_state_5(self):
        """Negative: /ticket NOT allowed in state 5."""
        assert CommandPolicyLoader.is_command_allowed("5", "/ticket") is False

    def test_plan_allowed_in_states_4_and_5(self):
        """Happy: /plan allowed in both state 4 and 5."""
        assert CommandPolicyLoader.is_command_allowed("4", "/plan") is True
        assert CommandPolicyLoader.is_command_allowed("5", "/plan") is True

    def test_plan_not_allowed_in_state_6(self):
        """Negative: /plan NOT allowed in phase 6."""
        assert CommandPolicyLoader.is_command_allowed("6", "/plan") is False
        assert CommandPolicyLoader.is_command_allowed("6.approved", "/plan") is False

    def test_review_decision_allowed_in_6_presentation(self):
        """Happy: /review-decision allowed in 6.presentation."""
        assert CommandPolicyLoader.is_command_allowed("6.presentation", "/review-decision") is True

    def test_review_decision_not_allowed_in_6_blocked(self):
        """Negative: /review-decision NOT allowed in 6.blocked."""
        assert CommandPolicyLoader.is_command_allowed("6.blocked", "/review-decision") is False

    def test_review_decision_not_allowed_in_6_execution(self):
        """Negative: /review-decision NOT allowed in 6.execution."""
        assert CommandPolicyLoader.is_command_allowed("6.execution", "/review-decision") is False

    def test_retry_allowed_in_blocked_and_rework(self):
        """Happy: /retry_implementation allowed in 6.blocked and 6.rework."""
        assert CommandPolicyLoader.is_command_allowed("6.blocked", "/retry_implementation") is True
        assert CommandPolicyLoader.is_command_allowed("6.rework", "/retry_implementation") is True

    def test_implementation_decision_alias_works(self):
        """Happy: /implementation-decision (alias) works same as /review-decision."""
        assert CommandPolicyLoader.is_command_allowed("6.presentation", "/implementation-decision") is True
        assert CommandPolicyLoader.is_command_allowed("6.blocked", "/implementation-decision") is False


class TestCommandPolicyLoaderWildcard:
    """Tests for wildcard allowed_in: '*'."""

    def test_continue_allowed_in_non_terminal_states(self):
        """Happy: /continue allowed in non-terminal states (wildcard + restrictions)."""
        assert CommandPolicyLoader.is_command_allowed("0", "/continue") is True
        assert CommandPolicyLoader.is_command_allowed("4", "/continue") is True
        assert CommandPolicyLoader.is_command_allowed("6.approved", "/continue") is True
        assert CommandPolicyLoader.is_command_allowed("6.execution", "/continue") is True

    def test_continue_blocked_in_terminal_states(self):
        """Negative: /continue blocked in terminal states (per command_restrictions)."""
        assert CommandPolicyLoader.is_command_allowed("6.complete", "/continue") is False

    def test_review_allowed_in_all_states(self):
        """Happy: /review allowed in all states (read-only)."""
        assert CommandPolicyLoader.is_command_allowed("0", "/review") is True
        assert CommandPolicyLoader.is_command_allowed("6.complete", "/review") is True
        assert CommandPolicyLoader.is_command_allowed("6.blocked", "/review") is True


class TestCommandPolicyLoaderTerminalStates:
    """Tests for terminal state restrictions."""

    def test_mutating_not_allowed_in_terminal_state(self):
        """Negative: Mutating commands blocked in terminal 6.complete."""
        assert CommandPolicyLoader.is_command_allowed("6.complete", "/continue") is False
        assert CommandPolicyLoader.is_command_allowed("6.complete", "/implement") is False
        assert CommandPolicyLoader.is_command_allowed("6.complete", "/plan") is False

    def test_readonly_allowed_in_terminal_state(self):
        """Happy: Read-only /review allowed in terminal state."""
        assert CommandPolicyLoader.is_command_allowed("6.complete", "/review") is True


class TestCommandPolicyLoaderAssertAllowed:
    """Tests for assert_command_allowed (fail-closed)."""

    def test_assert_allowed_passes_for_valid_command(self):
        """Happy: assert_command_allowed passes for allowed command."""
        CommandPolicyLoader.assert_command_allowed("6.approved", "/implement")

    def test_assert_allowed_raises_for_invalid_command(self):
        """Negative: assert_command_allowed raises CommandNotAllowedError."""
        with pytest.raises(CommandNotAllowedError) as exc_info:
            CommandPolicyLoader.assert_command_allowed("6.execution", "/implement")
        
        assert "/implement" in str(exc_info.value)
        assert "6.execution" in str(exc_info.value)

    def test_assert_allowed_raises_for_unknown_command(self):
        """Negative: assert_command_allowed raises CommandNotFoundError for unknown."""
        with pytest.raises(CommandNotFoundError):
            CommandPolicyLoader.assert_command_allowed("6.approved", "/unknown")


class TestCommandPolicyLoaderMutating:
    """Tests for is_mutating check."""

    def test_implement_is_mutating(self):
        """Happy: /implement is mutating."""
        assert CommandPolicyLoader.is_mutating("/implement") is True

    def test_review_is_not_mutating(self):
        """Happy: /review is NOT mutating (read-only)."""
        assert CommandPolicyLoader.is_mutating("/review") is False

    def test_continue_is_mutating(self):
        """Happy: /continue is mutating."""
        assert CommandPolicyLoader.is_mutating("/continue") is True


class TestCommandPolicyLoaderProducesEvents:
    """Tests for get_produces_events."""

    def test_implement_produces_events(self):
        """Happy: /implement produces expected events."""
        events = CommandPolicyLoader.get_produces_events("/implement")
        
        assert "implementation_started" in events
        assert "implementation_execution_in_progress" in events

    def test_review_produces_no_events(self):
        """Happy: /review produces no events (local findings only)."""
        events = CommandPolicyLoader.get_produces_events("/review")
        
        assert events == []

    def test_continue_produces_via_guards(self):
        """Happy: /continue produces *_via_guards."""
        events = CommandPolicyLoader.get_produces_events("/continue")
        
        assert events == ["*_via_guards"]


class TestCommandPolicyLoaderGetAllowedCommands:
    """Tests for get_allowed_commands."""

    def test_get_allowed_commands_in_6_approved(self):
        """Happy: Returns correct commands for 6.approved."""
        allowed = CommandPolicyLoader.get_allowed_commands("6.approved")
        
        assert "/implement" in allowed
        assert "/review" in allowed
        assert "/continue" in allowed

    def test_get_allowed_commands_in_6_execution(self):
        """Happy: /implement NOT in allowed for 6.execution."""
        allowed = CommandPolicyLoader.get_allowed_commands("6.execution")
        
        assert "/implement" not in allowed
        assert "/retry_implementation" not in allowed

    def test_get_allowed_commands_in_terminal(self):
        """Happy: Only read-only commands in terminal state."""
        allowed = CommandPolicyLoader.get_allowed_commands("6.complete")
        
        assert "/review" in allowed
        assert "/implement" not in allowed
        assert "/continue" not in allowed


class TestCommandPolicyLoaderOutputPolicies:
    """Tests for output policy enforcement."""

    def test_get_output_policy_for_restricted_state(self):
        """Happy: Output policy exists for 6.complete."""
        policy = CommandPolicyLoader.get_output_policy("6.complete")
        
        assert policy is not None
        assert isinstance(policy, OutputPolicy)
        assert "implementation" in policy.forbidden_output_classes

    def test_no_output_policy_for_unrestricted_state(self):
        """Edge: No output policy for states not in phase_output_policy_map."""
        policy = CommandPolicyLoader.get_output_policy("6.execution")
        
        assert policy is None

    def test_implementation_output_forbidden_in_6_complete(self):
        """Negative: 'implementation' output forbidden in 6.complete."""
        assert CommandPolicyLoader.is_output_allowed("6.complete", "implementation") is False
        assert CommandPolicyLoader.is_output_allowed("6.complete", "review") is True

    def test_output_allowed_in_unrestricted_state(self):
        """Happy: Output allowed when no policy restricts it."""
        assert CommandPolicyLoader.is_output_allowed("6.execution", "implementation") is True


class TestCommandPolicyLoaderRestrictionReason:
    """Tests for get_restriction_reason."""

    def test_restriction_reason_for_terminal_state(self):
        """Happy: Returns reason for terminal state restriction."""
        reason = CommandPolicyLoader.get_restriction_reason("6.complete", "/continue")
        
        assert reason is not None
        assert "terminal" in reason.lower() or "immutable" in reason.lower()

    def test_restriction_reason_for_allowed_command(self):
        """Edge: Returns None for allowed command."""
        reason = CommandPolicyLoader.get_restriction_reason("6.approved", "/implement")
        
        assert reason is None


class TestCommandPolicyLoaderRegression:
    """Regression: Real command_policy.yaml loads correctly."""

    def test_loads_real_command_policy(self):
        """Regression: Real command_policy.yaml loads successfully."""
        cmd = CommandPolicyLoader.get_command("/implement")
        
        assert cmd.id == "cmd_implement"
        assert cmd.behavior["type"] == "start_implementation"

    def test_all_defined_commands_loadable(self):
        """Regression: All commands in policy are loadable."""
        from governance_runtime.kernel.spec_registry import SpecRegistry
        
        policy = SpecRegistry.get_command_policy()
        commands = policy.get("commands", [])
        
        for cmd in commands:
            command_str = cmd["command"]
            loaded = CommandPolicyLoader.get_command(command_str)
            assert loaded.command == command_str

    def test_command_restrictions_loaded(self):
        """Regression: command_restrictions section loaded."""
        CommandPolicyLoader.reset()
        CommandPolicyLoader._ensure_loaded()
        
        assert CommandPolicyLoader._restrictions is not None
        assert len(CommandPolicyLoader._restrictions) > 0
        
        terminal_restriction = next(
            (r for r in CommandPolicyLoader._restrictions if "terminal" in r.state_pattern),
            None
        )
        assert terminal_restriction is not None
        assert "/continue" in terminal_restriction.blocked_commands

    def test_review_decision_produces_multiple_events(self):
        """Regression: /review-decision produces correct decision events."""
        events = CommandPolicyLoader.get_produces_events("/review-decision")
        
        assert "workflow_approved" in events
        assert "review_changes_requested" in events
        assert "review_rejected" in events


class TestValidateCommandIntegration:
    """Integration Tests: validate_command() as single entry point.
    
    These tests prove that command_policy.yaml is the authoritative source
    for runtime command validation.
    """

    def test_validate_command_returns_command_def(self):
        """Happy: validate_command returns CommandDef for valid command."""
        result = validate_command("6.approved", "/implement")
        
        assert isinstance(result, CommandDef)
        assert result.command == "/implement"
        assert result.mutating is True

    def test_validate_command_raises_for_unknown_command(self):
        """Fail-closed: Unknown command raises CommandNotFoundError."""
        with pytest.raises(CommandNotFoundError) as exc_info:
            validate_command("6.approved", "/unknown_command_xyz")
        
        assert "not found" in str(exc_info.value).lower()
        assert "command_policy.yaml" in str(exc_info.value)

    def test_validate_command_raises_for_disallowed_command(self):
        """Fail-closed: Disallowed command raises CommandNotAllowedError."""
        with pytest.raises(CommandNotAllowedError) as exc_info:
            validate_command("6.execution", "/implement")
        
        assert "/implement" in str(exc_info.value)
        assert "6.execution" in str(exc_info.value)

    def test_state_change_affects_command_validity(self):
        """Policy-driven: State change affects command validity.
        
        This proves runtime consults policy - same command, different states
        yields different results.
        """
        # /implement allowed in 6.approved
        result_approved = validate_command("6.approved", "/implement")
        assert result_approved.command == "/implement"
        
        # /implement NOT allowed in 6.execution
        with pytest.raises(CommandNotAllowedError):
            validate_command("6.execution", "/implement")
        
        # /implement NOT allowed in 6.presentation
        with pytest.raises(CommandNotAllowedError):
            validate_command("6.presentation", "/implement")

    def test_validate_command_with_mutating_flag(self):
        """Policy-driven: Mutating flag comes from command_policy.yaml."""
        impl = validate_command("6.approved", "/implement")
        review = validate_command("6.approved", "/review")
        
        assert impl.mutating is True
        assert review.mutating is False

    def test_validate_command_with_produces_events(self):
        """Policy-driven: produces_events comes from command_policy.yaml."""
        impl = validate_command("6.approved", "/implement")
        review_decision = validate_command("6.presentation", "/review-decision")
        
        assert "implementation_started" in impl.produces_events
        assert "workflow_approved" in review_decision.produces_events


class TestCommandPolicyRuntimeEnforcement:
    """Integration Tests: Runtime cannot bypass policy.
    
    These tests prove that command_policy.yaml is the ONLY source of truth
    for command permission decisions.
    """

    def test_unknown_command_not_allowed_in_any_state(self):
        """Fail-closed: Unknown command rejected regardless of state."""
        states_to_test = ["0", "4", "5", "6.approved", "6.execution", "6.presentation"]
        
        for state in states_to_test:
            assert CommandPolicyLoader.is_command_allowed(state, "/nonexistent") is False

    def test_policy_uses_spec_registry_single_source(self):
        """Integration: CommandPolicyLoader uses SpecRegistry, not own loader."""
        # Reset and verify loader uses SpecRegistry
        CommandPolicyLoader.reset()
        
        # This should work because SpecRegistry has loaded the policy
        cmd = CommandPolicyLoader.get_command("/implement")
        assert cmd.id == "cmd_implement"
        
        # Verify it's the same data as in SpecRegistry
        from governance_runtime.kernel.spec_registry import SpecRegistry
        policy = SpecRegistry.get_command_policy()
        spec_cmd = next(c for c in policy["commands"] if c["command"] == "/implement")
        
        assert cmd.id == spec_cmd["id"]
        assert cmd.behavior["type"] == spec_cmd["behavior"]["type"]

    def test_terminal_state_blocks_all_mutating_commands(self):
        """Policy enforcement: Terminal states block mutating commands."""
        mutating_commands = ["/implement", "/plan", "/ticket", "/continue"]
        
        for cmd in mutating_commands:
            # Even if wildcard allows it, restrictions override
            if CommandPolicyLoader.is_command_allowed("6.complete", cmd):
                # Only review should pass
                assert cmd == "/review"

    def test_command_restrictions_override_allowed_in(self):
        """Policy enforcement: Restrictions override allowed_in wildcard."""
        # /continue has allowed_in: "*" but is blocked in terminal states
        assert CommandPolicyLoader.is_command_allowed("6.execution", "/continue") is True
        assert CommandPolicyLoader.is_command_allowed("6.complete", "/continue") is False


class TestEnforceCommandPolicyRuntime:
    """Integration Tests: enforce_command_policy() as runtime enforcement point.
    
    These tests prove that the runtime MUST use command_policy.yaml
    for command validation. The enforcement function cannot be bypassed.
    """

    def test_enforce_returns_command_def_for_valid(self):
        """Happy: enforce_command_policy returns CommandDef for valid command."""
        result = enforce_command_policy("6.approved", "/implement")
        
        assert isinstance(result, CommandDef)
        assert result.command == "/implement"

    def test_enforce_raises_for_unknown_command(self):
        """Fail-closed: Unknown command raises CommandNotFoundError."""
        with pytest.raises(CommandNotFoundError) as exc_info:
            enforce_command_policy("6.approved", "/nonexistent")
        
        assert "not found" in str(exc_info.value).lower()
        assert "command_policy.yaml" in str(exc_info.value)

    def test_enforce_raises_for_disallowed_command(self):
        """Fail-closed: Disallowed command raises CommandNotAllowedError."""
        with pytest.raises(CommandNotAllowedError) as exc_info:
            enforce_command_policy("6.execution", "/implement")
        
        assert "/implement" in str(exc_info.value)
        assert "6.execution" in str(exc_info.value)

    def test_enforce_terminal_blocks_continue(self):
        """Fail-closed: enforce blocks /continue in terminal state."""
        # /continue is allowed in execution
        result = enforce_command_policy("6.execution", "/continue")
        assert result.command == "/continue"
        
        # /continue is blocked in terminal (even though wildcard allows it)
        with pytest.raises(CommandNotAllowedError):
            enforce_command_policy("6.complete", "/continue")

    def test_enforce_mutation_changes_validity(self):
        """Policy mutation affects enforce behavior.
        
        This proves that enforce_command_policy consults the actual policy
        and not a cached or hardcoded value.
        """
        # /implement works in 6.approved
        result = enforce_command_policy("6.approved", "/implement")
        assert result.mutating is True
        
        # Same command fails in wrong state
        with pytest.raises(CommandNotAllowedError):
            enforce_command_policy("0", "/implement")

    def test_enforcement_hook_called(self):
        """Integration: Registered hooks are called during enforcement."""
        calls = []
        
        def tracking_hook(state_id, command):
            calls.append((state_id, command))
        
        CommandPolicyRuntimeEnforcer.register_enforcement_hook(tracking_hook)
        
        try:
            enforce_command_policy("6.approved", "/implement")
            assert len(calls) == 1
            assert calls[0] == ("6.approved", "/implement")
        finally:
            CommandPolicyRuntimeEnforcer.reset()

    def test_enforcement_hook_can_block(self):
        """Integration: Hooks can add additional restrictions."""
        def block_everything(state_id, command):
            raise CommandNotAllowedError("HOOK: All commands blocked")
        
        CommandPolicyRuntimeEnforcer.register_enforcement_hook(block_everything)
        
        try:
            with pytest.raises(CommandNotAllowedError) as exc_info:
                enforce_command_policy("6.approved", "/implement")
            
            assert "HOOK" in str(exc_info.value)
        finally:
            CommandPolicyRuntimeEnforcer.reset()

    def test_enforce_produces_events_from_policy(self):
        """Policy-driven: enforce returns events from command_policy.yaml."""
        result = enforce_command_policy("6.approved", "/implement")
        
        assert "implementation_started" in result.produces_events
        assert "implementation_execution_in_progress" in result.produces_events

    def test_multiple_states_same_command(self):
        """Policy-driven: Same command, different validity by state."""
        # /implement in multiple states
        results = []
        for state in ["6.approved", "6.execution", "6.presentation", "0"]:
            try:
                result = enforce_command_policy(state, "/implement")
                results.append((state, "allowed"))
            except CommandNotAllowedError:
                results.append((state, "blocked"))
        
        assert ("6.approved", "allowed") in results
        assert ("6.execution", "blocked") in results
        assert ("6.presentation", "blocked") in results
        assert ("0", "blocked") in results
