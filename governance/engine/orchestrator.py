"""Wave B engine orchestrator v1.

This module composes adapter normalization, context resolution, write-policy
validation, gate evaluation, and runtime activation into one deterministic flow.
"""

from __future__ import annotations

from dataclasses import dataclass

from governance.context.repo_context_resolver import RepoRootResolutionResult, resolve_repo_root
from governance.engine.adapters import HostAdapter
from governance.engine.reason_codes import (
    BLOCKED_WORKSPACE_PERSISTENCE,
    REASON_CODE_NONE,
)
from governance.engine.runtime import EngineRuntimeDecision, evaluate_runtime_activation, golden_parity_fields
from governance.persistence.write_policy import WriteTargetPolicyResult, evaluate_target_path


@dataclass(frozen=True)
class EngineOrchestratorOutput:
    """Deterministic output payload for one orchestrated engine run."""

    repo_context: RepoRootResolutionResult
    write_policy: WriteTargetPolicyResult
    runtime: EngineRuntimeDecision
    parity: dict[str, str]


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
    live_enable_policy: str = "ci_strict",
) -> EngineOrchestratorOutput:
    """Run one deterministic engine orchestration cycle.

    Behavior is fail-closed and side-effect free: this function computes outputs
    but does not write files or mutate session artifacts.
    """

    caps = adapter.capabilities()
    repo_context = resolve_repo_root(
        env=adapter.environment(),
        cwd=adapter.cwd(),
        search_parent_git_root=(caps.cwd_trust == "untrusted"),
    )
    write_policy = evaluate_target_path(target_path)

    gate_blocked = False
    gate_reason_code = REASON_CODE_NONE
    if not write_policy.valid:
        gate_blocked = True
        gate_reason_code = write_policy.reason_code
    elif not repo_context.is_git_root and not caps.git_available:
        gate_blocked = True
        gate_reason_code = BLOCKED_WORKSPACE_PERSISTENCE

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
    parity = golden_parity_fields(runtime)
    return EngineOrchestratorOutput(
        repo_context=repo_context,
        write_policy=write_policy,
        runtime=runtime,
        parity=parity,
    )
