"""Wave engine orchestrator with deterministic gates and parity outputs."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Mapping

from governance.context.repo_context_resolver import RepoRootResolutionResult, resolve_repo_root
from governance.engine.adapters import HostAdapter, HostCapabilities, OperatingMode
from governance.engine.reason_codes import (
    BLOCKED_ACTIVATION_HASH_MISMATCH,
    BLOCKED_EXEC_DISALLOWED,
    BLOCKED_OPERATING_MODE_REQUIRED,
    BLOCKED_PACK_LOCK_INVALID,
    BLOCKED_PACK_LOCK_MISMATCH,
    BLOCKED_PACK_LOCK_REQUIRED,
    BLOCKED_SURFACE_CONFLICT,
    BLOCKED_PERMISSION_DENIED,
    BLOCKED_REPO_IDENTITY_RESOLUTION,
    BLOCKED_RELEASE_HYGIENE,
    BLOCKED_RULESET_HASH_MISMATCH,
    BLOCKED_SYSTEM_MODE_REQUIRED,
    NOT_VERIFIED_MISSING_EVIDENCE,
    REASON_CODE_NONE,
    WARN_MODE_DOWNGRADED,
    WARN_PERMISSION_LIMITED,
)
from governance.engine.reason_payload import build_reason_payload
from governance.engine.runtime import (
    EngineDeviation,
    EngineRuntimeDecision,
    LiveEnablePolicy,
    evaluate_runtime_activation,
    golden_parity_fields,
)
from governance.engine.selfcheck import run_engine_selfcheck
from governance.engine.surface_policy import (
    capability_satisfies_requirement,
    mode_satisfies_requirement,
    resolve_surface_policy,
)
from governance.packs.pack_lock import resolve_pack_lock
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
    ruleset_hash: str
    activation_hash: str
    reason_payload: dict[str, object]
    missing_evidence: tuple[str, ...]


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


def _hash_payload(payload: dict[str, object]) -> str:
    """Return deterministic sha256 over canonical JSON payload."""

    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _canonical_claim_evidence_id(claim: str) -> str:
    """Convert a human claim label into canonical claim evidence ID."""

    normalized = re.sub(r"[^a-z0-9]+", "-", claim.strip().lower()).strip("-")
    if not normalized:
        return ""
    return f"claim/{normalized}"


def _extract_verified_claim_evidence_ids(session_state_document: Mapping[str, object] | None) -> tuple[str, ...]:
    """Extract verified claim evidence IDs from SESSION_STATE build evidence."""

    if session_state_document is None:
        return ()

    root: Mapping[str, object]
    session_state = session_state_document.get("SESSION_STATE")
    if isinstance(session_state, Mapping):
        root = session_state
    else:
        root = session_state_document

    build_evidence = root.get("BuildEvidence")
    if not isinstance(build_evidence, Mapping):
        return ()

    observed: set[str] = set()

    claims_verified = build_evidence.get("claims_verified")
    if isinstance(claims_verified, list):
        for entry in claims_verified:
            if isinstance(entry, str) and entry.strip():
                observed.add(entry.strip())

    items = build_evidence.get("items")
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, Mapping):
                continue
            result = str(item.get("result", "")).strip().lower()
            verified = item.get("verified") is True
            if result not in {"pass", "passed", "ok", "success"} and not verified:
                continue

            evidence_id = item.get("evidence_id")
            if isinstance(evidence_id, str) and evidence_id.strip():
                observed.add(evidence_id.strip())
                continue

            claim_id = item.get("claim_id")
            if isinstance(claim_id, str) and claim_id.strip():
                observed.add(claim_id.strip())
                continue

            claim_label = item.get("claim")
            if isinstance(claim_label, str) and claim_label.strip():
                canonical = _canonical_claim_evidence_id(claim_label)
                if canonical:
                    observed.add(canonical)

    return tuple(sorted(observed))


def _build_ruleset_hash(
    *,
    selected_pack_ids: list[str] | None,
    pack_engine_version: str | None,
    expected_pack_lock_hash: str,
) -> str:
    """Build deterministic ruleset hash from selected packs and lock evidence."""

    payload = {
        "selected_pack_ids": sorted(selected_pack_ids or []),
        "pack_engine_version": pack_engine_version or "",
        "expected_pack_lock_hash": expected_pack_lock_hash,
    }
    return _hash_payload(payload)


def _build_activation_hash(
    *,
    phase: str,
    active_gate: str,
    next_gate_condition: str,
    target_path: str,
    effective_operating_mode: OperatingMode,
    capabilities_hash: str,
    repo_context: RepoRootResolutionResult,
    ruleset_hash: str,
) -> str:
    """Build deterministic activation hash from runtime context facts."""

    payload = {
        "phase": phase,
        "active_gate": active_gate,
        "next_gate_condition": next_gate_condition,
        "target_path": target_path,
        "effective_operating_mode": effective_operating_mode,
        "capabilities_hash": capabilities_hash,
        "repo_root": str(repo_context.repo_root),
        "repo_source": repo_context.source,
        "repo_is_git_root": repo_context.is_git_root,
        "ruleset_hash": ruleset_hash,
    }
    return _hash_payload(payload)


def _build_hash_mismatch_diff(
    *,
    observed_ruleset_hash: str | None,
    observed_activation_hash: str | None,
    expected_ruleset_hash: str,
    expected_activation_hash: str,
) -> dict[str, str]:
    """Build minimal deterministic mismatch diff payload."""

    diff: dict[str, str] = {}
    if observed_ruleset_hash and observed_ruleset_hash.strip() != expected_ruleset_hash:
        diff["ruleset_hash"] = f"{observed_ruleset_hash.strip()}->{expected_ruleset_hash}"
    if observed_activation_hash and observed_activation_hash.strip() != expected_activation_hash:
        diff["activation_hash"] = f"{observed_activation_hash.strip()}->{expected_activation_hash}"
    return diff


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
    observed_ruleset_hash: str | None = None,
    observed_activation_hash: str | None = None,
    require_hash_match: bool = False,
    required_evidence_ids: list[str] | None = None,
    observed_evidence_ids: list[str] | None = None,
    required_claim_evidence_ids: list[str] | None = None,
    session_state_document: Mapping[str, object] | None = None,
    release_hygiene_entries: tuple[str, ...] = (),
) -> EngineOrchestratorOutput:
    """Run one deterministic engine orchestration cycle.

    Behavior is fail-closed and side-effect free: this function computes outputs
    but does not write files or mutate session artifacts.
    """

    caps = adapter.capabilities()
    capabilities_hash = caps.stable_hash()
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
            recovery="restore required capabilities for requested mode or rerun in user mode",
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
    required_evidence = set(required_evidence_ids or [])
    required_evidence.update(required_claim_evidence_ids or [])
    observed_evidence = set(observed_evidence_ids or [])
    observed_evidence.update(_extract_verified_claim_evidence_ids(session_state_document))
    missing_evidence = tuple(sorted(required_evidence - observed_evidence))
    hash_diff: dict[str, str] = {}

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
            elif not capability_satisfies_requirement(caps=caps, capability_key=surface_policy.capability_key):
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
        try:
            expected_lock = resolve_pack_lock(
                manifests_by_id=manifests,
                selected_pack_ids=selected_pack_ids,
                engine_version=pack_engine_version,
            )
        except ValueError as exc:
            gate_blocked = True
            if "surface conflict detected" in str(exc):
                gate_reason_code = BLOCKED_SURFACE_CONFLICT
            else:
                gate_reason_code = BLOCKED_PACK_LOCK_INVALID
            expected_lock = {"lock_hash": "", "schema": "governance-lock.v1"}
        expected_pack_lock_hash = str(expected_lock.get("lock_hash", ""))
        pack_lock_checked = True

        if not gate_blocked:
            if observed_pack_lock is None:
                if require_pack_lock:
                    gate_blocked = True
                    gate_reason_code = BLOCKED_PACK_LOCK_REQUIRED
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

    ruleset_hash = _build_ruleset_hash(
        selected_pack_ids=selected_pack_ids,
        pack_engine_version=pack_engine_version,
        expected_pack_lock_hash=expected_pack_lock_hash,
    )
    activation_hash = _build_activation_hash(
        phase=phase,
        active_gate=active_gate,
        next_gate_condition=next_gate_condition,
        target_path=target_path,
        effective_operating_mode=effective_mode,
        capabilities_hash=capabilities_hash,
        repo_context=repo_context,
        ruleset_hash=ruleset_hash,
    )

    if not gate_blocked and require_hash_match:
        if observed_ruleset_hash and observed_ruleset_hash.strip() != ruleset_hash:
            gate_blocked = True
            gate_reason_code = BLOCKED_RULESET_HASH_MISMATCH
        elif observed_activation_hash and observed_activation_hash.strip() != activation_hash:
            gate_blocked = True
            gate_reason_code = BLOCKED_ACTIVATION_HASH_MISMATCH
        hash_diff = _build_hash_mismatch_diff(
            observed_ruleset_hash=observed_ruleset_hash,
            observed_activation_hash=observed_activation_hash,
            expected_ruleset_hash=ruleset_hash,
            expected_activation_hash=activation_hash,
        )

    if not gate_blocked and effective_mode in {"system", "pipeline"} and release_hygiene_entries:
        hygiene = run_engine_selfcheck(release_hygiene_entries=release_hygiene_entries)
        if not hygiene.ok and "release_metadata_hygiene_violation" in hygiene.failed_checks:
            gate_blocked = True
            gate_reason_code = BLOCKED_RELEASE_HYGIENE

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
    if missing_evidence and parity["status"] == "ok":
        parity["status"] = "not_verified"
        parity["reason_code"] = NOT_VERIFIED_MISSING_EVIDENCE

    if runtime.deviation is None and mode_deviation is not None:
        runtime = EngineRuntimeDecision(
            runtime_mode=runtime.runtime_mode,
            state=runtime.state,
            gate=runtime.gate,
            reason_code=runtime.reason_code,
            selfcheck=runtime.selfcheck,
            deviation=mode_deviation,
        )

    if parity["status"] == "blocked":
        reason_payload = build_reason_payload(
            status="BLOCKED",
            reason_code=parity["reason_code"],
            surface=target_path,
            signals_used=("write_policy", "mode_policy", "capabilities", "hash_gate"),
            primary_action="Resolve the active blocker for this gate.",
            recovery_steps=("Collect required evidence and rerun deterministic checks.",),
            next_command=parity["next_action.command"],
            impact="Workflow is blocked until the issue is fixed.",
            deviation=hash_diff,
        ).to_dict()
    elif parity["status"] == "not_verified":
        reason_payload = build_reason_payload(
            status="NOT_VERIFIED",
            reason_code=parity["reason_code"],
            surface=target_path,
            signals_used=("evidence_requirements",),
            primary_action="Provide missing evidence and rerun.",
            recovery_steps=("Gather host evidence for all required claims.",),
            next_command="show diagnostics",
            impact="Claims are not evidence-backed yet.",
            missing_evidence=missing_evidence,
        ).to_dict()
    elif parity["reason_code"].startswith("WARN-"):
        reason_payload = build_reason_payload(
            status="WARN",
            reason_code=parity["reason_code"],
            surface=target_path,
            signals_used=("degraded_execution",),
            impact="Execution continues with degraded capabilities.",
            recovery_steps=("Review warning impact and continue or remediate.",),
            next_command="none",
            deviation=runtime.deviation.__dict__ if runtime.deviation is not None else {},
        ).to_dict()
    else:
        reason_payload = build_reason_payload(
            status="OK",
            reason_code=REASON_CODE_NONE,
            surface=target_path,
            impact="all checks passed",
            next_command="none",
            recovery_steps=(),
        ).to_dict()

    return EngineOrchestratorOutput(
        repo_context=repo_context,
        write_policy=write_policy,
        runtime=runtime,
        parity=parity,
        effective_operating_mode=effective_mode,
        capabilities_hash=capabilities_hash,
        mode_downgraded=mode_downgraded,
        pack_lock_checked=pack_lock_checked,
        expected_pack_lock_hash=expected_pack_lock_hash,
        observed_pack_lock_hash=observed_pack_lock_hash,
        ruleset_hash=ruleset_hash,
        activation_hash=activation_hash,
        reason_payload=reason_payload,
        missing_evidence=missing_evidence,
    )
