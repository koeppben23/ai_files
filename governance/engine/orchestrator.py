"""Wave B engine orchestrator v1.

This module composes adapter normalization, context resolution, write-policy
validation, gate evaluation, and runtime activation into one deterministic flow.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping

from governance.context.repo_context_resolver import RepoRootResolutionResult, resolve_repo_root
from governance.engine.adapters import HostAdapter, HostCapabilities, OperatingMode
from governance.engine.reason_codes import (
    BLOCKED_EXEC_DISALLOWED,
    BLOCKED_OPERATING_MODE_REQUIRED,
    BLOCKED_PACK_LOCK_INVALID,
    BLOCKED_PACK_LOCK_MISMATCH,
    BLOCKED_PACK_LOCK_REQUIRED,
    BLOCKED_PERMISSION_DENIED,
    BLOCKED_REPO_IDENTITY_RESOLUTION,
    BLOCKED_SYSTEM_MODE_REQUIRED,
    REASON_CODE_NONE,
    WARN_MODE_DOWNGRADED,
    WARN_PERMISSION_LIMITED,
)
from governance.engine.surface_policy import (
    capability_satisfies_requirement,
    mode_satisfies_requirement,
    resolve_surface_policy,
)
from governance.packs.pack_lock import resolve_pack_lock
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
    pack_lock_checked: bool
    expected_pack_lock_hash: str
    observed_pack_lock_hash: str


def _resolve_effective_operating_mode(adapter: HostAdapter, requested: OperatingMode | None) -> OperatingMode:
    """Resolve operating mode with deterministic precedence."""

    env = adapter.environment()
    if requested is not None:
        return requested
    if str(env.get("CI", "")).strip().lower() == "true":
        return "pipeline"
    return adapter.default_operating_mode()


def _has_required_mode_capabilities(mode: OperatingMode, caps: HostCapabilities) -> bool:
    """Return True when minimal capabilities for the requested mode are satisfied."""

    if mode == "user":
        return True
    if mode == "system":
        return caps.exec_allowed and caps.fs_read_commands_home and caps.fs_write_workspaces_home
    return (
        caps.exec_allowed
        and caps.fs_read_commands_home
        and caps.fs_write_workspaces_home
        and caps.fs_write_commands_home
        and caps.git_available
    )


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
    pack_manifests_by_id: Mapping[str, Mapping[str, object]] | None = None,
    selected_pack_ids: list[str] | None = None,
    pack_engine_version: str | None = None,
    observed_pack_lock: Mapping[str, object] | None = None,
    require_pack_lock: bool = False,
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

    if requested_mode != "user" and not _has_required_mode_capabilities(requested_mode, caps):
        effective_mode = "user"
        mode_downgraded = True
        mode_reason = WARN_MODE_DOWNGRADED
        mode_deviation = EngineDeviation(
            type="mode_downgrade",
            scope="operating_mode",
            impact=f"requested {requested_mode} mode downgraded to user mode",
            recovery=(
                "restore required capabilities for the requested mode "
                "or rerun with explicit user mode"
            ),
        )

    repo_context = resolve_repo_root(
        env=adapter.environment(),
        cwd=adapter.cwd(),
        search_parent_git_root=(caps.cwd_trust == "untrusted"),
    )
    write_policy = evaluate_target_path(target_path)
    pack_lock_checked = False
    expected_pack_lock_hash = ""
    observed_pack_lock_hash = ""

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
        if target_variable is not None:
            surface_policy = resolve_surface_policy(target_variable)
            if surface_policy is None:
                gate_blocked = True
                gate_reason_code = BLOCKED_PERMISSION_DENIED
            elif not mode_satisfies_requirement(
                effective_mode=effective_mode,
                minimum_mode=surface_policy.minimum_mode,
            ):
                gate_blocked = True
                if surface_policy.minimum_mode == "system":
                    gate_reason_code = BLOCKED_SYSTEM_MODE_REQUIRED
                else:
                    gate_reason_code = BLOCKED_OPERATING_MODE_REQUIRED
            elif not capability_satisfies_requirement(
                caps=caps,
                capability_key=surface_policy.capability_key,
            ):
                gate_blocked = True
                gate_reason_code = BLOCKED_PERMISSION_DENIED
            elif not repo_context.is_git_root and not caps.git_available:
                gate_blocked = True
                gate_reason_code = BLOCKED_REPO_IDENTITY_RESOLUTION
        elif not repo_context.is_git_root and not caps.git_available:
            gate_blocked = True
            gate_reason_code = BLOCKED_REPO_IDENTITY_RESOLUTION

    if not gate_blocked and pack_manifests_by_id is not None and selected_pack_ids is not None and pack_engine_version is not None:
        manifests = {key: dict(value) for key, value in pack_manifests_by_id.items()}
        expected_lock = resolve_pack_lock(
            manifests_by_id=manifests,
            selected_pack_ids=selected_pack_ids,
            engine_version=pack_engine_version,
        )
        expected_pack_lock_hash = str(expected_lock.get("lock_hash", ""))
        pack_lock_checked = True

        if observed_pack_lock is None:
            if require_pack_lock:
                gate_blocked = True
                gate_reason_code = BLOCKED_PACK_LOCK_REQUIRED
        else:
            if not isinstance(observed_pack_lock, dict):
                gate_blocked = True
                gate_reason_code = BLOCKED_PACK_LOCK_INVALID
            else:
                observed_schema = observed_pack_lock.get("schema")
                observed_hash = observed_pack_lock.get("lock_hash")
                observed_pack_lock_hash = str(observed_hash) if observed_hash is not None else ""
                if observed_schema != expected_lock.get("schema") or not isinstance(observed_hash, str) or not observed_hash:
                    gate_blocked = True
                    gate_reason_code = BLOCKED_PACK_LOCK_INVALID
                elif observed_hash != expected_pack_lock_hash:
                    gate_blocked = True
                    gate_reason_code = BLOCKED_PACK_LOCK_MISMATCH

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
        pack_lock_checked=pack_lock_checked,
        expected_pack_lock_hash=expected_pack_lock_hash,
        observed_pack_lock_hash=observed_pack_lock_hash,
    )
