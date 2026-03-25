"""Command Policy Loader - Operative Authority for Command Permissions.

This module provides command policy enforcement as the operative authority
for the runtime. It reads from command_policy.yaml via SpecRegistry and
provides runtime methods for command permission checking.

Architecture:
    - command_policy_loader.py: Command permission binding (WP1)
    - Uses SpecRegistry as single source of truth for spec loading
    - Provides fail-closed command validation
    - Single entry point for all command permission checks

Usage:
    from governance_runtime.kernel.command_policy_loader import (
        validate_command,        # Main API - raises on invalid command
        CommandNotAllowedError,  # Raised when command not allowed
        CommandNotFoundError,    # Raised when command not in policy
    )
    
    # Fail-closed validation
    validate_command("6.approved", "/implement")  # OK
    
    try:
        validate_command("6.execution", "/implement")  # Raises
    except CommandNotAllowedError:
        pass

Error Classification:
    - CommandNotFoundError: Command not defined in command_policy.yaml (fail-closed)
    - CommandNotAllowedError: Command not allowed in current state (fail-closed)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from governance_runtime.kernel.spec_registry import SpecRegistry


class CommandPolicyError(RuntimeError):
    """Base error for command policy failures."""
    pass


class CommandNotFoundError(CommandPolicyError):
    """Raised when a command is not found in policy."""
    pass


class CommandNotAllowedError(CommandPolicyError):
    """Raised when a command is not allowed in current state."""
    pass


@dataclass(frozen=True)
class CommandDef:
    """Definition of a command from command_policy.yaml."""
    id: str
    command: str
    allowed_in: list[str] | str
    mutating: bool
    behavior: dict[str, Any]
    produces_events: list[str] | str


@dataclass(frozen=True)
class CommandRestriction:
    """Restriction rules for a state."""
    state_pattern: str
    blocked_command_types: list[str]
    blocked_commands: list[str]
    reason: str


@dataclass(frozen=True)
class OutputPolicy:
    """Output policy for a state."""
    id: str
    state_id: str
    allowed_output_classes: list[str]
    forbidden_output_classes: list[str]
    reason: str | None


class CommandPolicyLoader:
    """Loader for command policy with runtime enforcement.
    
    Provides command permission checking based on command_policy.yaml.
    Uses SpecRegistry to access specs, ensuring consistency and fail-closed behavior.
    
    Error Classification:
    - CommandNotFoundError: Command not defined in policy
    - CommandNotAllowedError: Command not allowed in state (checked first)
    """

    _command_map: dict[str, CommandDef] | None = None
    _restrictions: list[CommandRestriction] | None = None
    _output_policies: dict[str, OutputPolicy] | None = None
    _policy_map: dict[str, OutputPolicy] | None = None

    @classmethod
    def _ensure_loaded(cls) -> None:
        """Ensure command policy is loaded from SpecRegistry."""
        if cls._command_map is not None:
            return
        
        policy = SpecRegistry.get_command_policy()
        
        cls._command_map = {}
        for cmd in policy.get("commands", []):
            cmd_def = CommandDef(
                id=cmd.get("id", ""),
                command=cmd.get("command", ""),
                allowed_in=cmd.get("allowed_in", []),
                mutating=cmd.get("mutating", False),
                behavior=cmd.get("behavior", {}),
                produces_events=cmd.get("produces_events", []),
            )
            cls._command_map[cmd["command"]] = cmd_def
        
        cls._restrictions = []
        for restriction in policy.get("command_restrictions", []):
            cls._restrictions.append(CommandRestriction(
                state_pattern=restriction.get("state_pattern", ""),
                blocked_command_types=restriction.get("blocked_command_types", []),
                blocked_commands=restriction.get("blocked_commands", []),
                reason=restriction.get("reason", ""),
            ))
        
        cls._output_policies = {}
        for op in policy.get("output_policies", []):
            policy_def = OutputPolicy(
                id=op.get("id", ""),
                state_id=op.get("state_id", ""),
                allowed_output_classes=op.get("allowed_output_classes", []),
                forbidden_output_classes=op.get("forbidden_output_classes", []),
                reason=op.get("reason"),
            )
            cls._output_policies[op["id"]] = policy_def
        
        cls._policy_map = {}
        for mapping in policy.get("phase_output_policy_map", []):
            state_id = mapping.get("state_id", "")
            policy_ref = mapping.get("output_policy_ref", "")
            if policy_ref in cls._output_policies:
                cls._policy_map[state_id] = cls._output_policies[policy_ref]

    @classmethod
    def reset(cls) -> None:
        """Reset the loader. For testing only."""
        cls._command_map = None
        cls._restrictions = None
        cls._output_policies = None
        cls._policy_map = None

    @classmethod
    def get_command(cls, command: str) -> CommandDef:
        """Get command definition by command string.
        
        Args:
            command: Command string (e.g., "/implement")
            
        Returns:
            CommandDef with command metadata.
            
        Raises:
            CommandNotFoundError: If command not in policy.
        """
        cls._ensure_loaded()
        
        if command not in cls._command_map:
            raise CommandNotFoundError(
                f"Command '{command}' not found in command_policy.yaml. "
                "All commands must be defined in policy."
            )
        
        return cls._command_map[command]

    @classmethod
    def is_command_allowed(cls, state_id: str, command: str) -> bool:
        """Check if command is allowed in given state.
        
        Args:
            state_id: Current state ID (e.g., "6.approved")
            command: Command string (e.g., "/implement")
            
        Returns:
            True if command is allowed in state, False otherwise.
            
        Note:
            This method does NOT raise on disallowed commands.
            Use assert_command_allowed() if you want fail-closed behavior.
        """
        cls._ensure_loaded()
        
        if command not in cls._command_map:
            return False
        
        cmd_def = cls._command_map[command]
        allowed_in = cmd_def.allowed_in
        
        if allowed_in == "*":
            pass
        elif isinstance(allowed_in, list):
            if state_id not in allowed_in:
                return False
        else:
            return False
        
        if cls._is_restricted(state_id, command, cmd_def):
            return False
        
        return True

    @classmethod
    def assert_command_allowed(cls, state_id: str, command: str) -> None:
        """Assert command is allowed in state, raise if not.
        
        Args:
            state_id: Current state ID
            command: Command string
            
        Raises:
            CommandNotFoundError: If command not in policy.
            CommandNotAllowedError: If command not allowed in state.
        """
        cls._ensure_loaded()
        
        if command not in cls._command_map:
            raise CommandNotFoundError(
                f"Command '{command}' not found in command_policy.yaml. "
                "All commands must be defined in policy."
            )
        
        if not cls.is_command_allowed(state_id, command):
            raise CommandNotAllowedError(
                f"Command '{command}' not allowed in state '{state_id}'. "
                "Check command_policy.yaml for allowed_in states."
            )

    @classmethod
    def _is_restricted(cls, state_id: str, command: str, cmd_def: CommandDef) -> bool:
        """Check if command is restricted in state by command_restrictions."""
        if cls._restrictions is None:
            return False
        
        for restriction in cls._restrictions:
            if cls._matches_state_pattern(state_id, restriction.state_pattern):
                if command in restriction.blocked_commands:
                    return True
                
                behavior_type = cmd_def.behavior.get("type", "")
                if behavior_type in restriction.blocked_command_types:
                    return True
        
        return False

    @classmethod
    def _matches_state_pattern(cls, state_id: str, pattern: str) -> bool:
        """Match state_id against state_pattern.
        
        Patterns:
            - Exact match: "6.complete"
            - Wildcard suffix: "6.*"
            - Terminal pattern: "*.terminal"
        """
        if pattern == state_id:
            return True
        
        if pattern.endswith(".*"):
            prefix = pattern[:-2]
            if state_id.startswith(prefix + ".") or state_id == prefix:
                return True
        
        if pattern == "*.terminal":
            topology = SpecRegistry.get_topology()
            for state in topology.get("states", []):
                if state.get("id") == state_id and state.get("terminal", False):
                    return True
        
        return False

    @classmethod
    def is_mutating(cls, command: str) -> bool:
        """Check if command is mutating (changes state).
        
        Args:
            command: Command string
            
        Returns:
            True if command is mutating.
        """
        cmd_def = cls.get_command(command)
        return cmd_def.mutating

    @classmethod
    def get_produces_events(cls, command: str) -> list[str]:
        """Get events that command produces.
        
        Args:
            command: Command string
            
        Returns:
            List of event names command produces.
            Empty list means state change via evidence, not direct event.
            "*_via_guards" means event determined by guards (special case).
        """
        cmd_def = cls.get_command(command)
        produces = cmd_def.produces_events
        
        if isinstance(produces, list):
            return produces
        elif produces == "*_via_guards":
            return ["*_via_guards"]
        else:
            return []

    @classmethod
    def get_allowed_commands(cls, state_id: str) -> set[str]:
        """Get all commands allowed in state.
        
        Args:
            state_id: State ID to check
            
        Returns:
            Set of allowed command strings.
        """
        cls._ensure_loaded()
        
        allowed = set()
        for command, cmd_def in cls._command_map.items():
            if cls.is_command_allowed(state_id, command):
                allowed.add(command)
        
        return allowed

    @classmethod
    def get_output_policy(cls, state_id: str) -> OutputPolicy | None:
        """Get output policy for state.
        
        Args:
            state_id: State ID
            
        Returns:
            OutputPolicy if defined for state, None otherwise.
        """
        cls._ensure_loaded()
        
        return cls._policy_map.get(state_id)

    @classmethod
    def is_output_allowed(cls, state_id: str, output_class: str) -> bool:
        """Check if output class is allowed in state.
        
        Args:
            state_id: State ID
            output_class: Output class name (e.g., "implementation", "review")
            
        Returns:
            True if output is allowed or no policy restricts it.
        """
        policy = cls.get_output_policy(state_id)
        
        if policy is None:
            return True
        
        if output_class in policy.forbidden_output_classes:
            return False
        
        if policy.allowed_output_classes and output_class not in policy.allowed_output_classes:
            return False
        
        return True

    @classmethod
    def get_restriction_reason(cls, state_id: str, command: str) -> str | None:
        """Get reason why command is restricted in state.
        
        Args:
            state_id: State ID
            command: Command string
            
        Returns:
            Reason string if restricted, None if allowed.
        """
        cls._ensure_loaded()
        
        if command not in cls._command_map:
            return None
        
        if cls.is_command_allowed(state_id, command):
            return None
        
        cmd_def = cls._command_map[command]
        
        if cls._restrictions:
            for restriction in cls._restrictions:
                if cls._matches_state_pattern(state_id, restriction.state_pattern):
                    if command in restriction.blocked_commands:
                        return restriction.reason
                    
                    behavior_type = cmd_def.behavior.get("type", "")
                    if behavior_type in restriction.blocked_command_types:
                        return restriction.reason
        
        return f"Command not in allowed_in list for state '{state_id}'"


# ============================================================================
# Public API - Single Entry Point for Command Validation
# ============================================================================

def validate_command(state_id: str, command: str) -> CommandDef:
    """Validate command is allowed in state - fail-closed.
    
    This is the SINGLE entry point for all command permission checks.
    All command handlers MUST use this function before processing commands.
    
    Args:
        state_id: Current state ID (e.g., "6.approved")
        command: Command string (e.g., "/implement")
        
    Returns:
        CommandDef if command is valid and allowed.
        
    Raises:
        CommandNotFoundError: If command not defined in policy (fail-closed).
        CommandNotAllowedError: If command not allowed in state (fail-closed).
        
    Example:
        # In a command handler:
        try:
            cmd_def = validate_command(current_state, user_command)
            # Proceed with command using cmd_def.metadata
        except (CommandNotFoundError, CommandNotAllowedError) as e:
            return error_response(e)
    """
    loader = CommandPolicyLoader
    loader._ensure_loaded()
    
    if command not in loader._command_map:
        raise CommandNotFoundError(
            f"Command '{command}' not found in command_policy.yaml. "
            "All commands must be defined in policy. "
            f"Known commands: {sorted(loader._command_map.keys())}"
        )
    
    cmd_def = loader._command_map[command]
    
    if not loader.is_command_allowed(state_id, command):
        reason = loader.get_restriction_reason(state_id, command)
        raise CommandNotAllowedError(
            f"Command '{command}' not allowed in state '{state_id}'. "
            f"{reason or ''}"
        )
    
    return cmd_def


class CommandPolicyRuntimeEnforcer:
    """Runtime enforcement layer for command policy.
    
    This class provides enforcement hooks that MUST be called by the runtime
    before any command is processed. It ensures that command_policy.yaml
    is the authoritative source for command permission decisions.
    
    Usage in runtime:
        1. Call CommandPolicyRuntimeEnforcer.register_enforcement_hook()
           to register the enforcement callback
        2. Before processing any command, call enforce_command_policy()
        3. The hook will be called and must return True or raise an error
    """
    
    _enforcement_hooks: list[callable] = []
    _enabled: bool = True
    
    @classmethod
    def register_enforcement_hook(cls, hook: callable) -> None:
        """Register a hook that will be called for every command.
        
        The hook receives (state_id, command) and should raise
        CommandPolicyError if the command should be rejected.
        """
        cls._enforcement_hooks.append(hook)
    
    @classmethod
    def disable(cls) -> None:
        """Disable enforcement. FOR TESTING ONLY."""
        cls._enabled = False
    
    @classmethod
    def enable(cls) -> None:
        """Enable enforcement."""
        cls._enabled = True
    
    @classmethod
    def reset(cls) -> None:
        """Reset hooks. FOR TESTING ONLY."""
        cls._enforcement_hooks = []
        cls._enabled = True
    
    @classmethod
    def enforce(cls, state_id: str, command: str) -> CommandDef:
        """Enforce command policy - fail-closed.
        
        This is the MAIN enforcement point that must be called before
        any command is processed by the runtime.
        
        Args:
            state_id: Current state ID
            command: Command string
            
        Returns:
            CommandDef if command is valid and allowed.
            
        Raises:
            CommandNotFoundError: If command not in policy (fail-closed).
            CommandNotAllowedError: If command not allowed (fail-closed).
        """
        if not cls._enabled:
            return validate_command(state_id, command)
        
        # Run registered hooks first
        for hook in cls._enforcement_hooks:
            hook(state_id, command)
        
        # Then run standard validation
        return validate_command(state_id, command)


def enforce_command_policy(state_id: str, command: str) -> CommandDef:
    """Enforce command policy at runtime - fail-closed.
    
    This function MUST be called before any command is processed.
    It ensures command_policy.yaml is the authoritative source.
    
    Args:
        state_id: Current state ID
        command: Command string
        
    Returns:
        CommandDef if command is valid and allowed.
        
    Raises:
        CommandNotFoundError: If command not in policy (fail-closed).
        CommandNotAllowedError: If command not allowed (fail-closed).
        
    Example - in execute() function:
        def execute_command(state, command):
            cmd_def = enforce_command_policy(state, command)
            # Process command using cmd_def
    """
    return CommandPolicyRuntimeEnforcer.enforce(state_id, command)
