"""Session state document helpers."""

from __future__ import annotations

from typing import Any, Mapping


def _coerce_non_negative_int(value: object) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value if value >= 0 else 0
    if isinstance(value, str):
        raw = value.strip()
        if raw.isdigit():
            return int(raw)
    return None


def _read_first_int(mapping: Mapping[str, object], keys: tuple[str, ...]) -> int | None:
    for key in keys:
        if key in mapping:
            parsed = _coerce_non_negative_int(mapping.get(key))
            if parsed is not None:
                return parsed
    return None


def _clamp_review_iteration_fields(
    *,
    state: dict[str, object],
    block_key: str,
    block_iteration_keys: tuple[str, ...],
    block_max_keys: tuple[str, ...],
    top_iteration_keys: tuple[str, ...],
    top_max_keys: tuple[str, ...],
) -> None:
    block_obj = state.get(block_key)
    block = dict(block_obj) if isinstance(block_obj, Mapping) else None

    block_iteration = _read_first_int(block, block_iteration_keys) if block is not None else None
    top_iteration = _read_first_int(state, top_iteration_keys)
    iteration = block_iteration if block_iteration is not None else (top_iteration if top_iteration is not None else None)
    if iteration is None:
        return

    block_max = _read_first_int(block, block_max_keys) if block is not None else None
    top_max = _read_first_int(state, top_max_keys)
    max_iterations = block_max if block_max is not None else (top_max if top_max is not None else 3)
    max_iterations = min(max(1, max_iterations), 3)
    clamped_iteration = min(max(0, iteration), max_iterations)

    if block is None:
        block = {}
    block["iteration"] = clamped_iteration
    block["max_iterations"] = max_iterations
    for key in block_iteration_keys:
        if key in block:
            block[key] = clamped_iteration
    for key in block_max_keys:
        if key in block:
            block[key] = max_iterations
    state[block_key] = block

    for key in top_iteration_keys:
        if key in state:
            state[key] = clamped_iteration
    for key in top_max_keys:
        if key in state:
            state[key] = max_iterations


def _normalize_review_iteration_invariants(state: dict[str, object]) -> None:
    _clamp_review_iteration_fields(
        state=state,
        block_key="Phase5Review",
        block_iteration_keys=("iteration", "Iteration", "rounds_completed", "RoundsCompleted"),
        block_max_keys=("max_iterations", "MaxIterations"),
        top_iteration_keys=("phase5_self_review_iterations", "phase5SelfReviewIterations", "self_review_iterations"),
        top_max_keys=("phase5_max_review_iterations", "phase5MaxReviewIterations"),
    )
    _clamp_review_iteration_fields(
        state=state,
        block_key="ImplementationReview",
        block_iteration_keys=("iteration", "Iteration"),
        block_max_keys=("max_iterations", "MaxIterations"),
        top_iteration_keys=("phase6_review_iterations", "phase6ReviewIterations"),
        top_max_keys=("phase6_max_review_iterations", "phase6MaxReviewIterations"),
    )


def session_state_root(session_state_document: Mapping[str, object] | None) -> Mapping[str, object]:
    if session_state_document is None:
        return {}
    session_state = session_state_document.get("SESSION_STATE")
    if isinstance(session_state, Mapping):
        return session_state
    return session_state_document


def phase_token(value: str) -> str:
    from governance.domain.phase_state_machine import normalize_phase_token

    return normalize_phase_token(value)


def extract_repo_identity(session_state_document: Mapping[str, object] | None) -> str:
    """Extract stable repo identity (repo_fingerprint) from SESSION_STATE.
    
    Reads multiple key variants for compatibility:
    - SESSION_STATE.RepoFingerprint (canonical)
    - SESSION_STATE.repo_fingerprint (legacy)
    - root-level RepoFingerprint
    - root-level repo_fingerprint
    """
    if session_state_document is None:
        return ""
    session_state = session_state_document.get("SESSION_STATE")
    root = session_state if isinstance(session_state, Mapping) else session_state_document
    
    for key in ("RepoFingerprint", "repo_fingerprint"):
        value = root.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    
    for key in ("RepoFingerprint", "repo_fingerprint"):
        value = session_state_document.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    
    return ""


def with_workspace_ready_gate(
    session_state_document: Mapping[str, object] | None,
    *,
    repo_fingerprint: str,
    committed: bool,
) -> Mapping[str, object] | None:
    """Write workspace ready gate state with canonical keys.
    
    Writes canonical keys (PascalCase under SESSION_STATE):
    - SESSION_STATE.RepoFingerprint
    - SESSION_STATE.WorkspaceReadyGateCommitted
    
    Also writes legacy lowercase keys for transition compatibility.
    """
    if session_state_document is None:
        state: dict[str, object] = {}
    else:
        state = dict(session_state_document)
    root = state.get("SESSION_STATE")
    if isinstance(root, Mapping):
        ss = dict(root)
        ss["RepoFingerprint"] = repo_fingerprint
        ss["WorkspaceReadyGateCommitted"] = committed
        ss["repo_fingerprint"] = repo_fingerprint
        ss["workspace_ready_gate_committed"] = committed
        ss["workspace_ready"] = committed
        state["SESSION_STATE"] = ss
        return state
    state["SESSION_STATE"] = {
        "RepoFingerprint": repo_fingerprint,
        "WorkspaceReadyGateCommitted": committed,
        "repo_fingerprint": repo_fingerprint,
        "workspace_ready_gate_committed": committed,
        "workspace_ready": committed,
    }
    state["repo_fingerprint"] = repo_fingerprint
    state["workspace_ready_gate_committed"] = committed
    state["workspace_ready"] = committed
    return state


def _auto_propagate_gates(
    ss: dict[str, object],
    *,
    status: str,
    next_token: str | None,
) -> None:
    """Conservatively upgrade Gates dict entries based on authoritative kernel evidence.

    Policy (Fix 2.1):
    - Only runs when kernel status is OK (authoritative outcome).
    - Only upgrades from "pending" — never overwrites a gate that has already
      been evaluated to a non-pending terminal status.
    - Uses ``next_token`` rank to infer which upstream gates must have been
      cleared by the kernel's phase transition logic.

    Gate-to-phase mapping (derived from ``phase_api.yaml`` topology):
    - P5-Architecture  → cleared when session reaches token 5.3 or later.
    - P5.3-TestQuality → cleared when session reaches token 5.4, 5.5, 5.6, or 6.
    - P5.4-BusinessRules → NOT auto-propagated (conditional on Phase 1.5;
      handled by ``bootstrap_preflight``).
    - P5.5-TechnicalDebt → NOT auto-propagated (informational only).
    - P5.6-RollbackSafety → NOT auto-propagated (conditional on schema/contract
      touch surface; handled by ``bootstrap_preflight`` + ``gate_evaluator``).
    - P6-ImplementationQA → NOT auto-propagated (requires explicit completion).
    """
    from governance.domain.phase_state_machine import phase_rank

    if status != "OK" or not next_token:
        return

    gates_obj = ss.get("Gates")
    if not isinstance(gates_obj, dict):
        return
    gates: dict[str, object] = gates_obj

    token_rank = phase_rank(next_token)
    if token_rank < 0:
        return

    # P5-Architecture: session at 5.3+ implies architecture review passed.
    if token_rank >= phase_rank("5.3"):
        if str(gates.get("P5-Architecture", "")).strip().lower() == "pending":
            gates["P5-Architecture"] = "approved"

    # P5.3-TestQuality: session at 5.4+ or 6 implies test quality gate passed.
    if token_rank >= phase_rank("5.4"):
        if str(gates.get("P5.3-TestQuality", "")).strip().lower() == "pending":
            gates["P5.3-TestQuality"] = "pass"


def with_kernel_result(
    session_state_document: Mapping[str, object] | None,
    *,
    phase: str,
    next_token: str | None,
    active_gate: str,
    next_gate_condition: str,
    status: str,
    spec_hash: str,
    spec_path: str,
    spec_loaded_at: str,
    log_paths: Mapping[str, str] | None,
    event_id: str,
    plan_record_status: str | None = None,
    plan_record_versions: int | None = None,
    effective_operating_mode: str | None = None,
    resolved_operating_mode: str | None = None,
    verify_policy_version: str | None = None,
    operating_mode_resolution: Mapping[str, object] | None = None,
    break_glass: Mapping[str, object] | None = None,
) -> Mapping[str, object]:
    state: dict[str, object] = dict(session_state_document or {})
    root = state.get("SESSION_STATE")
    ss = dict(root) if isinstance(root, Mapping) else {}

    ss["Phase"] = phase
    ss["phase"] = phase
    ss["Next"] = next_token or ""
    ss["active_gate"] = active_gate
    ss["next_gate_condition"] = next_gate_condition
    ss["status"] = status
    ss["log_paths"] = dict(log_paths or {})
    kernel = ss.get("Kernel")
    kernel_block = dict(kernel) if isinstance(kernel, Mapping) else {}
    kernel_block["PhaseApiPath"] = spec_path
    kernel_block["PhaseApiSha256"] = spec_hash
    kernel_block["PhaseApiLoadedAt"] = spec_loaded_at
    kernel_block["LastPhaseEventId"] = event_id
    ss["Kernel"] = kernel_block
    if isinstance(plan_record_status, str):
        status_text = plan_record_status.strip() or "unknown"
        ss["plan_record_status"] = status_text
        ss["PlanRecordStatus"] = status_text
    if plan_record_versions is not None:
        parsed_versions = _coerce_non_negative_int(plan_record_versions)
        versions = parsed_versions if parsed_versions is not None else 0
        ss["plan_record_versions"] = versions
        ss["PlanRecordVersions"] = versions

    if isinstance(effective_operating_mode, str) and effective_operating_mode.strip():
        effective_mode = effective_operating_mode.strip().lower()
        ss["effective_operating_mode"] = effective_mode

    if isinstance(resolved_operating_mode, str) and resolved_operating_mode.strip():
        resolved_mode = resolved_operating_mode.strip().lower()
        ss["resolved_operating_mode"] = resolved_mode
        ss["resolvedOperatingMode"] = resolved_mode

    if isinstance(verify_policy_version, str) and verify_policy_version.strip():
        policy_version = verify_policy_version.strip()
        ss["verify_policy_version"] = policy_version
        ss["verifyPolicyVersion"] = policy_version

    if isinstance(operating_mode_resolution, Mapping):
        ss["operating_mode_resolution"] = dict(operating_mode_resolution)
        ss["operatingModeResolution"] = dict(operating_mode_resolution)

    if isinstance(break_glass, Mapping):
        ss["break_glass"] = dict(break_glass)
        ss["breakGlass"] = dict(break_glass)

    _normalize_review_iteration_invariants(ss)
    _auto_propagate_gates(ss, status=status, next_token=next_token)

    state["SESSION_STATE"] = ss
    return state
