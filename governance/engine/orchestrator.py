"""Wave B engine orchestrator v1.

This module composes adapter normalization, context resolution, write-policy
validation, gate evaluation, and runtime activation into one deterministic flow.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from governance.context.repo_context_resolver import RepoRootResolutionResult, resolve_repo_root
from governance.engine.adapters import HostAdapter, HostCapabilities, OperatingMode
from governance.engine.reason_codes import (
    BLOCKED_EXEC_DISALLOWED,
    BLOCKED_PERMISSION_DENIED,
    BLOCKED_REPO_IDENTITY_RESOLUTION,
    REASON_CODE_NONE,
    WARN_MODE_DOWNGRADED,
    WARN_PERMISSION_LIMITED,
)
from governance.engine.runtime import (
    EngineDeviation,
    EngineRuntimeDecision,
    LiveEnablePolicy,
    evaluate_runtime_activation,
    golden_parity_fields,
)
from governance.persistence.write_policy import WriteTargetPolicyResult, evaluate_target_path

_VARIABLE_CAPTURE = re.compile(r"^\$\{([A-Z0-9_]+)\}")


@dataclass(frozen=True)
class EngineOrchestratorOutput:
    """Deterministic output payload for one orchestrated engine run."""

    repo_context: RepoRootResolutionResult
    write_policy: WriteTargetPolicyResult
    runtime: EngineRuntimeDecision
    parity: dict[str, str]
    effective_operating_mode: OperatingMode
    capabilities_hash: str
    mode_downgraded: bool


def _resolve_effective_operating_mode(adapter: HostAdapter, requested: OperatingMode | None) -> OperatingMode:
    """Resolve operating mode with deterministic precedence."""

    env = adapter.environment()
    if requested is not None:
        return requested
    if str(env.get("CI", "")).strip().lower() == "true":
        return "system"
    return adapter.default_operating_mode()


def _has_required_system_capabilities(caps: HostCapabilities) -> bool:
    """Return True when minimal system-mode requirements are satisfied."""

    return caps.exec_allowed and caps.fs_read_commands_home and caps.fs_write_workspaces_home


def _target_write_allowed(capability_key: str, caps: HostCapabilities) -> bool:
    """Map target surface to capability flag check."""

    if capability_key in {"WORKSPACE_MEMORY_FILE", "SESSION_STATE_FILE", "REPO_CACHE_FILE", "REPO_DECISION_PACK_FILE", "REPO_DIGEST_FILE"}:
        return caps.fs_write_workspaces_home
    if capability_key in {"COMMANDS_HOME", "PROFILES_HOME", "SESSION_STATE_POINTER_FILE"}:
        return caps.fs_write_commands_home
    if capability_key in {"CONFIG_ROOT", "OPENCODE_HOME", "WORKSPACES_HOME"}:
        return caps.fs_write_config_root
    if capability_key in {"REPO_HOME", "REPO_BUSINESS_RULES_FILE"}:
        return caps.fs_write_repo_root
    return False


def _extract_target_variable(target_path: str) -> str | None:
    """Extract canonical variable token from target path string."""

    match = _VARIABLE_CAPTURE.match(target_path.strip())
    if match is None:
        return None
    return match.group(1)


def run_engine_orchestrator(
    *,
    adapter: HostAdapter,
    phase: str,
    active_gate: str,
    mode: str,
    next_gate_condition: str,
    gate_key: str = "P4-Entry",
    target_path: str = "${WORKSPACE_MEMORY_FILE}",
    enable_live_engine: bool = False,
    enforce_registered_reason_code: bool = False,
    live_enable_policy: LiveEnablePolicy = "ci_strict",
    requested_operating_mode: OperatingMode | None = None,
) -> EngineOrchestratorOutput:
    """Run one deterministic engine orchestration cycle.

    Behavior is fail-closed and side-effect free: this function computes outputs
    but does not write files or mutate session artifacts.
    """

    caps = adapter.capabilities()
    requested_mode = _resolve_effective_operating_mode(adapter, requested_operating_mode)
    effective_mode = requested_mode
    mode_downgraded = False
    mode_deviation: EngineDeviation | None = None
    mode_reason = REASON_CODE_NONE

    if requested_mode == "system" and not _has_required_system_capabilities(caps):
        effective_mode = "user"
        mode_downgraded = True
        mode_reason = WARN_MODE_DOWNGRADED
        mode_deviation = EngineDeviation(
            type="mode_downgrade",
            scope="operating_mode",
            impact="requested system mode downgraded to user mode",
            recovery="restore required capabilities or rerun with explicit user mode",
        )

    repo_context = resolve_repo_root(
        env=adapter.environment(),
        cwd=adapter.cwd(),
        search_parent_git_root=(caps.cwd_trust == "untrusted"),
    )
    write_policy = evaluate_target_path(target_path)

    gate_blocked = False
    gate_reason_code = REASON_CODE_NONE
    if not caps.exec_allowed:
        gate_blocked = True
        gate_reason_code = BLOCKED_EXEC_DISALLOWED
    elif not write_policy.valid:
        gate_blocked = True
        gate_reason_code = write_policy.reason_code
    else:
        target_variable = _extract_target_variable(target_path)
        if target_variable is not None and not _target_write_allowed(target_variable, caps):
            gate_blocked = True
            gate_reason_code = BLOCKED_PERMISSION_DENIED
        elif not repo_context.is_git_root and not caps.git_available:
            gate_blocked = True
            gate_reason_code = BLOCKED_REPO_IDENTITY_RESOLUTION

    runtime = evaluate_runtime_activation(
        phase=phase,
        active_gate=active_gate,
        mode=mode,
        next_gate_condition=next_gate_condition,
        gate_key=gate_key,
        gate_blocked=gate_blocked,
        gate_reason_code=gate_reason_code,
        enforce_registered_reason_code=enforce_registered_reason_code,
        enable_live_engine=enable_live_engine,
        live_enable_policy=live_enable_policy,
    )

    convenience_limited = not caps.git_available and repo_context.is_git_root and not gate_blocked
    parity = golden_parity_fields(runtime)
    if mode_reason != REASON_CODE_NONE and parity["status"] == "ok":
        parity["reason_code"] = mode_reason
    if convenience_limited and parity["status"] == "ok" and parity["reason_code"] == REASON_CODE_NONE:
        parity["reason_code"] = WARN_PERMISSION_LIMITED

    if runtime.deviation is None and mode_deviation is not None:
        runtime = EngineRuntimeDecision(
            runtime_mode=runtime.runtime_mode,
            state=runtime.state,
            gate=runtime.gate,
            reason_code=runtime.reason_code,
            selfcheck=runtime.selfcheck,
            deviation=mode_deviation,
        )

    return EngineOrchestratorOutput(
        repo_context=repo_context,
        write_policy=write_policy,
        runtime=runtime,
        parity=parity,
        effective_operating_mode=effective_mode,
        capabilities_hash=caps.stable_hash(),
        mode_downgraded=mode_downgraded,
    )
