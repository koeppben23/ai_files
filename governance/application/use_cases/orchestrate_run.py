"""Wave engine orchestrator with deterministic gates and parity outputs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
from pathlib import Path
import re
from types import SimpleNamespace
from typing import Any, Mapping

from governance.domain.evidence_policy import extract_verified_claim_evidence_ids
from governance.domain.integrity import build_activation_hash, build_ruleset_hash
from governance.domain.policy_precedence import resolve_widening_precedence
from governance.domain.reason_codes import (
    BLOCKED_ENGINE_SELFCHECK,
    BLOCKED_ACTIVATION_HASH_MISMATCH,
    BLOCKED_MISSING_BINDING_FILE,
    BLOCKED_EXEC_DISALLOWED,
    BLOCKED_OPERATING_MODE_REQUIRED,
    BLOCKED_PACK_LOCK_INVALID,
    BLOCKED_PACK_LOCK_MISMATCH,
    BLOCKED_PACK_LOCK_REQUIRED,
    BLOCKED_SURFACE_CONFLICT,
    BLOCKED_PERMISSION_DENIED,
    BLOCKED_REPO_IDENTITY_RESOLUTION,
    BLOCKED_RELEASE_HYGIENE,
    BLOCKED_STATE_OUTDATED,
    BLOCKED_WORKSPACE_PERSISTENCE,
    BLOCKED_RULESET_HASH_MISMATCH,
    BLOCKED_SYSTEM_MODE_REQUIRED,
    INTERACTIVE_REQUIRED_IN_PIPELINE,
    NOT_VERIFIED_EVIDENCE_STALE,
    NOT_VERIFIED_MISSING_EVIDENCE,
    PERSIST_CONFIRMATION_INVALID,
    PERSIST_CONFIRMATION_REQUIRED,
    PERSIST_DISALLOWED_IN_PIPELINE,
    PERSIST_GATE_NOT_APPROVED,
    PERSIST_PHASE_MISMATCH,
    POLICY_PRECEDENCE_APPLIED,
    PROMPT_BUDGET_EXCEEDED,
    REPO_CONSTRAINT_UNSUPPORTED,
    REPO_CONSTRAINT_WIDENING,
    REPO_DOC_UNSAFE_DIRECTIVE,
    REASON_CODE_NONE,
    WARN_MODE_DOWNGRADED,
    WARN_PERMISSION_LIMITED,
)
from governance.application.ports.gateways import (
    RepoDocEvidence,
    HostAdapter,
    OperatingMode,
    LiveEnablePolicy,
    canonicalize_reason_payload_failure,
    ensure_workspace_ready,
    capability_satisfies_requirement,
    classify_repo_doc,
    compute_repo_doc_hash,
    build_reason_payload,
    evaluate_interaction_gate,
    load_persist_confirmation_evidence,
    evaluate_runtime_activation,
    evaluate_target_path,
    golden_parity_fields,
    mode_satisfies_requirement,
    resolve_pack_lock,
    resolve_prompt_budget,
    resolve_repo_root,
    resolve_surface_policy,
    run_engine_selfcheck,
    summarize_classification,
)
from governance.application.policies.persistence_policy import (
    ARTIFACT_BUSINESS_RULES,
    ARTIFACT_DECISION_PACK,
    ARTIFACT_REPO_CACHE,
    ARTIFACT_REPO_DIGEST,
    ARTIFACT_WORKSPACE_MEMORY,
    PersistencePolicyInput,
    can_write as can_write_persistence,
)
from governance.application.use_cases.phase_router import route_phase

_VARIABLE_CAPTURE = re.compile(r"^\$\{([A-Z0-9_]+)\}")
_WORKSPACE_MEMORY_CONFIRMATION = "Persist to workspace memory: YES"


@dataclass(frozen=True)
class PersistencePhaseGateDecision:
    allowed: bool
    reason_code: str
    reason: str


def _session_state_root(session_state_document: Mapping[str, object] | None) -> Mapping[str, object]:
    if session_state_document is None:
        return {}
    session_state = session_state_document.get("SESSION_STATE")
    if isinstance(session_state, Mapping):
        return session_state
    return session_state_document


def _phase_rank(token: str) -> int:
    rank_map = {
        "1": 10,
        "1.1": 11,
        "1.2": 12,
        "1.3": 13,
        "1.5": 15,
        "2": 20,
        "2.1": 21,
        "3A": 30,
        "3B-1": 31,
        "3B-2": 32,
        "4": 40,
        "5": 50,
        "5.3": 53,
        "5.4": 54,
        "5.5": 55,
        "5.6": 56,
        "6": 60,
    }
    return rank_map.get(token, -1)


def _phase_token(value: str) -> str:
    from governance.domain.phase_state_machine import normalize_phase_token

    return normalize_phase_token(value)


def _phase5_approved(state: Mapping[str, object]) -> bool:
    for key in ("phase5_approved", "Phase5Approved", "phase_5_approved"):
        value = state.get(key)
        if isinstance(value, bool):
            return value
    return False


def _business_rules_executed(state: Mapping[str, object]) -> bool:
    for key in ("business_rules_executed", "BusinessRulesExecuted"):
        value = state.get(key)
        if isinstance(value, bool):
            return value
    return False


def _artifact_kind_from_target_variable(target_variable: str | None) -> str | None:
    if target_variable == "REPO_CACHE_FILE":
        return ARTIFACT_REPO_CACHE
    if target_variable == "REPO_DIGEST_FILE":
        return ARTIFACT_REPO_DIGEST
    if target_variable == "REPO_DECISION_PACK_FILE":
        return ARTIFACT_DECISION_PACK
    if target_variable == "REPO_BUSINESS_RULES_FILE":
        return ARTIFACT_BUSINESS_RULES
    if target_variable == "WORKSPACE_MEMORY_FILE":
        return ARTIFACT_WORKSPACE_MEMORY
    return None


def _confirmation_from_evidence(evidence: Mapping[str, object] | None, *, scope: str, gate: str) -> str:
    if evidence is None:
        return ""
    items = evidence.get("items") if isinstance(evidence, Mapping) else None
    if not isinstance(items, list):
        return ""
    for item in items:
        if not isinstance(item, Mapping):
            continue
        if str(item.get("scope") or "").strip() != scope:
            continue
        if str(item.get("gate") or "").strip() != gate:
            continue
        value = str(item.get("value") or "").strip()
        if value:
            return f"Persist to workspace memory: {value}"
    return ""


def _evaluate_phase_coupled_persistence(
    *,
    persistence_write_requested: bool,
    phase: str,
    target_variable: str | None,
    effective_mode: OperatingMode,
    session_state_document: Mapping[str, object] | None,
    persist_confirmation_evidence: Mapping[str, object] | None,
) -> PersistencePhaseGateDecision:
    if not persistence_write_requested:
        return PersistencePhaseGateDecision(True, REASON_CODE_NONE, "not-applicable")

    artifact_kind = _artifact_kind_from_target_variable(target_variable)
    if artifact_kind is None:
        return PersistencePhaseGateDecision(True, REASON_CODE_NONE, "not-applicable")

    state = _session_state_root(session_state_document)
    confirmation = _confirmation_from_evidence(
        persist_confirmation_evidence,
        scope="workspace-memory",
        gate="phase5",
    )
    decision = can_write_persistence(
        PersistencePolicyInput(
            artifact_kind=artifact_kind,
            phase=phase,
            mode=effective_mode,
            gate_approved=_phase5_approved(state),
            business_rules_executed=_business_rules_executed(state),
            explicit_confirmation=confirmation,
        )
    )

    if decision.allowed:
        return PersistencePhaseGateDecision(True, REASON_CODE_NONE, "approved")

    return PersistencePhaseGateDecision(False, decision.reason_code, decision.reason)


def _is_code_output_request(requested_action: str | None) -> bool:
    action = (requested_action or "").strip().lower()
    if not action:
        return False
    patterns = ("implement", "write code", "emit code", "generate code", "code output")
    return any(token in action for token in patterns)

@dataclass(frozen=True)
class EngineOrchestratorOutput:
    """Deterministic output payload for one orchestrated engine run."""

    repo_context: Any
    write_policy: Any
    runtime: Any
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
    repo_doc_evidence: RepoDocEvidence | None
    precedence_events: tuple[dict[str, object], ...]
    prompt_events: tuple[dict[str, object], ...]


def _resolve_effective_operating_mode(adapter: HostAdapter, requested: OperatingMode | None) -> OperatingMode:
    """Resolve operating mode with deterministic precedence."""

    if requested is not None:
        return requested
    env = adapter.environment()
    ci = str(env.get("CI", "")).strip().lower()
    if ci and ci not in {"0", "false", "no", "off"}:
        return "pipeline"
    return adapter.default_operating_mode()


def _has_required_mode_capabilities(mode: OperatingMode, caps: Any) -> bool:
    """Return True when minimal capabilities for the requested mode are satisfied."""

    if mode == "user":
        return caps.fs_read_commands_home and caps.fs_write_workspaces_home
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



def _extract_repo_identity(session_state_document: Mapping[str, object] | None) -> str:
    """Extract stable repo identity (repo_fingerprint) from SESSION_STATE."""
    if session_state_document is None:
        return ""
    session_state = session_state_document.get("SESSION_STATE")
    root = session_state if isinstance(session_state, Mapping) else session_state_document
    value = root.get("repo_fingerprint")
    return value.strip() if isinstance(value, str) else ""


def _with_workspace_ready_gate(
    session_state_document: Mapping[str, object] | None,
    *,
    repo_fingerprint: str,
    committed: bool,
) -> Mapping[str, object] | None:
    if session_state_document is None:
        state: dict[str, object] = {}
    else:
        state = dict(session_state_document)
    root = state.get("SESSION_STATE")
    if isinstance(root, Mapping):
        ss = dict(root)
        ss["repo_fingerprint"] = repo_fingerprint
        ss["workspace_ready_gate_committed"] = committed
        ss["workspace_ready"] = committed
        state["SESSION_STATE"] = ss
        return state
    state["repo_fingerprint"] = repo_fingerprint
    state["workspace_ready_gate_committed"] = committed
    state["workspace_ready"] = committed
    return state


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
    now_utc: datetime | None = None,
    release_hygiene_entries: tuple[str, ...] = (),
    repo_doc_path: str | None = None,
    repo_doc_text: str | None = None,
    prompt_used_total: int = 0,
    prompt_used_repo_docs: int = 0,
    repo_constraint_topic: str | None = None,
    repo_constraint_supported: bool = True,
    repo_constraint_widening: bool = False,
    widening_from: str | None = None,
    widening_to: str | None = None,
    widening_approved: bool = False,
    requested_action: str | None = None,
    persistence_write_requested: bool = False,
    persist_confirmation_evidence_path: str | None = None,
    interactive_required: bool = False,
    why_interactive_required: str | None = None,
    commit_workspace_ready_gate: bool = False,
    workspaces_home: str | None = None,
    session_state_file: str | None = None,
    session_pointer_file: str | None = None,
    session_id: str | None = None,
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
    mode_deviation: Any | None = None
    mode_reason = REASON_CODE_NONE

    if requested_mode != "user" and not _has_required_mode_capabilities(requested_mode, caps):
        effective_mode = "user"
        mode_downgraded = True
        mode_reason = WARN_MODE_DOWNGRADED
        mode_deviation = SimpleNamespace(
            type="mode_downgrade",
            scope="operating_mode",
            impact=f"requested {requested_mode} mode downgraded to user mode",
            recovery="restore required capabilities for requested mode or rerun in user mode",
        )

    repo_context = resolve_repo_root(
        adapter=adapter,
        cwd=adapter.cwd(),
    )

    if commit_workspace_ready_gate and repo_context.is_git_root and repo_context.repo_root is not None:
        repo_fingerprint = _extract_repo_identity(session_state_document)
        if repo_fingerprint and workspaces_home and session_state_file and session_pointer_file:
            gate = ensure_workspace_ready(
                workspaces_home=Path(workspaces_home),
                repo_fingerprint=repo_fingerprint,
                repo_root=repo_context.repo_root,
                session_state_file=Path(session_state_file),
                session_pointer_file=Path(session_pointer_file),
                session_id=(session_id or hashlib.sha256(str(repo_context.repo_root).encode("utf-8")).hexdigest()[:16]),
                discovery_method=repo_context.source,
            )
            session_state_document = _with_workspace_ready_gate(
                session_state_document,
                repo_fingerprint=repo_fingerprint,
                committed=bool(getattr(gate, "ok", False)),
            )

    routed_phase = route_phase(
        requested_phase=phase,
        requested_active_gate=active_gate,
        requested_next_gate_condition=next_gate_condition,
        session_state_document=session_state_document,
        repo_is_git_root=repo_context.is_git_root,
    )

    phase = routed_phase.phase
    active_gate = routed_phase.active_gate
    next_gate_condition = routed_phase.next_gate_condition

    write_policy = evaluate_target_path(target_path)
    pack_lock_checked = False
    expected_pack_lock_hash = ""
    observed_pack_lock_hash = ""
    evaluation_now = now_utc if now_utc is not None else adapter.now_utc()
    verified_claim_evidence, stale_claim_evidence = extract_verified_claim_evidence_ids(
        session_state_document,
        now_utc=evaluation_now,
    )
    required_evidence = set(required_evidence_ids or [])
    required_evidence.update(required_claim_evidence_ids or [])
    observed_evidence = set(observed_evidence_ids or [])
    observed_evidence.update(verified_claim_evidence)
    missing_evidence = tuple(sorted(required_evidence - observed_evidence))
    stale_required_evidence = tuple(sorted(required_evidence.intersection(stale_claim_evidence)))
    hash_diff: dict[str, str] = {}
    repo_doc_evidence: RepoDocEvidence | None = None
    precedence_events: list[dict[str, object]] = []
    prompt_events: list[dict[str, object]] = []
    unsafe_directive = None

    if repo_doc_text is not None:
        doc_hash = compute_repo_doc_hash(repo_doc_text)
        classifications = classify_repo_doc(repo_doc_text)
        repo_doc_evidence = RepoDocEvidence(
            doc_path=repo_doc_path or "AGENTS.md",
            doc_hash=doc_hash,
            classification_summary=summarize_classification(classifications),
        )
        unsafe_directive = next((c for c in classifications if c.directive_class == "unsafe_directive"), None)
        if unsafe_directive is not None:
            hash_diff["repo_doc_unsafe"] = unsafe_directive.rule_id

    budget = resolve_prompt_budget(effective_mode)

    gate_blocked = False
    gate_reason_code = REASON_CODE_NONE

    interaction_decision = evaluate_interaction_gate(
        effective_mode=effective_mode,
        interactive_required=interactive_required,
        prompt_used_total=prompt_used_total,
        prompt_used_repo_docs=prompt_used_repo_docs,
        requested_action=requested_action or "",
    )
    if interaction_decision.blocked:
        gate_blocked = True
        gate_reason_code = INTERACTIVE_REQUIRED_IN_PIPELINE
        if interaction_decision.event is not None:
            prompt_events.append(interaction_decision.event)
    elif prompt_used_total > budget.max_total_prompts or prompt_used_repo_docs > budget.max_repo_doc_prompts:
        gate_blocked = True
        gate_reason_code = PROMPT_BUDGET_EXCEEDED

    if not gate_blocked and repo_doc_evidence is not None and repo_doc_evidence.classification_summary.get("unsafe_directive", 0) > 0:
        gate_blocked = True
        gate_reason_code = REPO_DOC_UNSAFE_DIRECTIVE

    if not gate_blocked and repo_constraint_widening:
        precedence = resolve_widening_precedence(
            mode=effective_mode,
            widening_approved=widening_approved,
            reason_code=REPO_CONSTRAINT_WIDENING,
            applied_reason_code=POLICY_PRECEDENCE_APPLIED,
        )
        decision = precedence.decision
        if decision == "allow":
            precedence_events.append(
                {
                    "event": "POLICY_PRECEDENCE_APPLIED",
                    "winner_layer": precedence.winner_layer,
                    "loser_layer": precedence.loser_layer,
                    "requested_action": requested_action or "widen_constraint",
                    "decision": decision,
                    "reason_code": precedence.reason_code,
                    "refs": {
                        "policy_hash": hashlib.sha256("master_policy".encode("utf-8")).hexdigest(),
                        "pack_hash": expected_pack_lock_hash,
                        "mode_hash": hashlib.sha256(effective_mode.encode("utf-8")).hexdigest(),
                        "host_perm_hash": capabilities_hash,
                        "doc_hash": repo_doc_evidence.doc_hash if repo_doc_evidence is not None else "",
                    },
                }
            )
        else:
            gate_blocked = True
            gate_reason_code = precedence.reason_code
            if not widening_approved:
                interactive_required = True
                why_interactive_required = "widening_approval_required"
                prompt_events.append(
                    {
                        "event": "PROMPT_REQUESTED",
                        "source": "governance",
                        "topic": "WideningApproval",
                        "mode": effective_mode,
                    }
                )
        if decision == "deny":
            precedence_events.append(
                {
                    "event": "POLICY_PRECEDENCE_APPLIED",
                    "winner_layer": "mode_policy",
                    "loser_layer": "repo_doc_constraints",
                    "requested_action": requested_action or "widen_constraint",
                    "decision": "deny",
                    "reason_code": REPO_CONSTRAINT_WIDENING,
                    "refs": {
                        "policy_hash": hashlib.sha256("master_policy".encode("utf-8")).hexdigest(),
                        "pack_hash": expected_pack_lock_hash,
                        "mode_hash": hashlib.sha256(effective_mode.encode("utf-8")).hexdigest(),
                        "host_perm_hash": capabilities_hash,
                        "doc_hash": repo_doc_evidence.doc_hash if repo_doc_evidence is not None else "",
                    },
                }
            )

    if not gate_blocked and not repo_constraint_supported:
        mode_reason = REPO_CONSTRAINT_UNSUPPORTED
        if repo_constraint_topic:
            hash_diff["repo_constraint_topic"] = repo_constraint_topic
    target_variable = _extract_target_variable(target_path)
    persist_confirmation_evidence = load_persist_confirmation_evidence(
        evidence_path=(Path(persist_confirmation_evidence_path) if persist_confirmation_evidence_path else None)
    )

    persistence_phase_gate = _evaluate_phase_coupled_persistence(
        persistence_write_requested=persistence_write_requested,
        phase=phase,
        target_variable=target_variable,
        effective_mode=effective_mode,
        session_state_document=session_state_document,
        persist_confirmation_evidence=persist_confirmation_evidence,
    )

    if not gate_blocked and not persistence_phase_gate.allowed:
        gate_blocked = True
        gate_reason_code = persistence_phase_gate.reason_code
        if gate_reason_code == PERSIST_DISALLOWED_IN_PIPELINE:
            interactive_required = True
            why_interactive_required = persistence_phase_gate.reason

    if not gate_blocked and _phase_token(phase) == "4" and _is_code_output_request(requested_action):
        gate_blocked = True
        gate_reason_code = BLOCKED_STATE_OUTDATED

    if not caps.fs_read_commands_home:
        gate_blocked = True
        gate_reason_code = BLOCKED_MISSING_BINDING_FILE
    elif not caps.exec_allowed:
        gate_blocked = True
        gate_reason_code = BLOCKED_EXEC_DISALLOWED
    elif not write_policy.valid:
        gate_blocked = True
        gate_reason_code = write_policy.reason_code
    else:
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

    ruleset_hash = build_ruleset_hash(
        selected_pack_ids=selected_pack_ids,
        pack_engine_version=pack_engine_version,
        expected_pack_lock_hash=expected_pack_lock_hash,
    )
    repo_identity = _extract_repo_identity(session_state_document) or str(repo_context.repo_root)

    activation_hash = build_activation_hash(
        phase=phase,
        active_gate=active_gate,
        next_gate_condition=next_gate_condition,
        target_path=target_path,
        effective_operating_mode=effective_mode,
        capabilities_hash=capabilities_hash,
        repo_source=repo_context.source,
        repo_is_git_root=repo_context.is_git_root,
        repo_identity=repo_identity,
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
        if mode_reason == REPO_CONSTRAINT_UNSUPPORTED:
            parity["status"] = "not_verified"
    if convenience_limited and parity["status"] == "ok" and parity["reason_code"] == REASON_CODE_NONE:
        parity["reason_code"] = WARN_PERMISSION_LIMITED
    if stale_required_evidence and parity["status"] == "ok":
        parity["status"] = "not_verified"
        parity["reason_code"] = NOT_VERIFIED_EVIDENCE_STALE
    elif missing_evidence and parity["status"] == "ok":
        parity["status"] = "not_verified"
        parity["reason_code"] = NOT_VERIFIED_MISSING_EVIDENCE

    if runtime.deviation is None and mode_deviation is not None:
        runtime = runtime.__class__(
            runtime_mode=runtime.runtime_mode,
            state=runtime.state,
            gate=runtime.gate,
            reason_code=runtime.reason_code,
            selfcheck=runtime.selfcheck,
            deviation=mode_deviation,
        )

    reason_context: dict[str, object] = {}
    if parity["reason_code"] == REPO_DOC_UNSAFE_DIRECTIVE and repo_doc_evidence is not None and unsafe_directive is not None:
        reason_context = {
            "doc_path": repo_doc_evidence.doc_path,
            "doc_hash": repo_doc_evidence.doc_hash,
            "directive_excerpt": unsafe_directive.excerpt,
            "classification_rule_id": unsafe_directive.rule_id,
            "pointers": [repo_doc_evidence.doc_path],
        }
    elif parity["reason_code"] == REPO_CONSTRAINT_WIDENING:
        reason_context = {
            "requested_widening": {
                "type": "write_scope" if (requested_action or "").startswith("write") else "command_scope",
                "from": widening_from or "policy_envelope",
                "to": widening_to or "repo_doc_request",
            },
            "doc_path": repo_doc_evidence.doc_path if repo_doc_evidence is not None else (repo_doc_path or "AGENTS.md"),
            "doc_hash": repo_doc_evidence.doc_hash if repo_doc_evidence is not None else "",
            "winner_layer": "mode_policy",
            "loser_layer": "repo_doc_constraints",
        }
    elif parity["reason_code"] == INTERACTIVE_REQUIRED_IN_PIPELINE:
        reason_context = {
            "requested_action": requested_action or "interactive_required",
            "why_interactive_required": why_interactive_required or "approval_required",
            "pointers": [target_path],
        }
    elif parity["reason_code"] in {
        BLOCKED_WORKSPACE_PERSISTENCE,
        PERSIST_CONFIRMATION_REQUIRED,
        PERSIST_CONFIRMATION_INVALID,
        PERSIST_DISALLOWED_IN_PIPELINE,
        PERSIST_PHASE_MISMATCH,
        PERSIST_GATE_NOT_APPROVED,
    }:
        reason_context = {
            "requested_action": requested_action or "none",
            "required_confirmation": _WORKSPACE_MEMORY_CONFIRMATION,
            "phase": phase,
            "active_gate": active_gate,
            "pointers": [target_path],
        }
    elif parity["reason_code"] == BLOCKED_STATE_OUTDATED:
        reason_context = {
            "requested_action": requested_action or "none",
            "phase": phase,
            "active_gate": active_gate,
            "policy": "phase-4-planning-only-no-code-output",
            "pointers": [target_path],
        }
    elif parity["reason_code"] == PROMPT_BUDGET_EXCEEDED:
        reason_context = {
            "mode": effective_mode,
            "budget": {
                "max_total": budget.max_total_prompts,
                "max_repo_docs": budget.max_repo_doc_prompts,
                "used_total": prompt_used_total,
                "used_repo_docs": prompt_used_repo_docs,
            },
            "last_prompt": {
                "source": prompt_events[-1]["source"] if prompt_events else "none",
                "topic": prompt_events[-1]["topic"] if prompt_events else "none",
            },
        }
    elif parity["reason_code"] == REPO_CONSTRAINT_UNSUPPORTED:
        reason_context = {
            "constraint_topic": repo_constraint_topic or "unknown",
            "doc_path": repo_doc_evidence.doc_path if repo_doc_evidence is not None else (repo_doc_path or "AGENTS.md"),
            "doc_hash": repo_doc_evidence.doc_hash if repo_doc_evidence is not None else "",
        }
    elif precedence_events:
        latest = precedence_events[-1]
        if latest.get("reason_code") == POLICY_PRECEDENCE_APPLIED:
            reason_context = {
                "winner_layer": str(latest.get("winner_layer", "")),
                "loser_layer": str(latest.get("loser_layer", "")),
                "requested_action": str(latest.get("requested_action", "")),
                "decision": str(latest.get("decision", "")),
                "refs": latest.get("refs", {}),
            }

    try:
        if parity["status"] == "blocked":
            blocked_missing_evidence = missing_evidence
            if parity["reason_code"] == BLOCKED_MISSING_BINDING_FILE:
                blocked_missing_evidence = ("${USER_HOME}/.config/opencode/commands/governance.paths.json",)
            reason_payload = build_reason_payload(
                status="BLOCKED",
                reason_code=parity["reason_code"],
                surface=target_path,
                signals_used=("write_policy", "mode_policy", "capabilities", "hash_gate"),
                primary_action="Resolve the active blocker for this gate.",
                recovery_steps=("Collect required evidence and rerun deterministic checks.",),
                next_command=parity["next_action.command"],
                impact="Workflow is blocked until the issue is fixed.",
                missing_evidence=blocked_missing_evidence,
                deviation=hash_diff,
                context=reason_context,
            ).to_dict()
        elif parity["status"] == "not_verified":
            not_verified_missing = stale_required_evidence if stale_required_evidence else missing_evidence
            if not not_verified_missing and parity["reason_code"] == REPO_CONSTRAINT_UNSUPPORTED:
                not_verified_missing = (repo_constraint_topic or "repo_constraint_unsupported",)
            not_verified_signals = ("evidence_freshness",) if stale_required_evidence else ("evidence_requirements",)
            not_verified_primary_action = (
                "Refresh stale evidence and rerun."
                if stale_required_evidence
                else "Provide missing evidence and rerun."
            )
            reason_payload = build_reason_payload(
                status="NOT_VERIFIED",
                reason_code=parity["reason_code"],
                surface=target_path,
                signals_used=not_verified_signals,
                primary_action=not_verified_primary_action,
                recovery_steps=("Gather host evidence for all required claims.",),
                next_command="show diagnostics",
                impact="Claims are not evidence-backed yet.",
                missing_evidence=not_verified_missing,
                context=reason_context,
            ).to_dict()
        elif parity["reason_code"].startswith("WARN-") or parity["reason_code"] == REPO_CONSTRAINT_WIDENING:
            reason_payload = build_reason_payload(
                status="WARN",
                reason_code=parity["reason_code"],
                surface=target_path,
                signals_used=("degraded_execution",),
                impact="Execution continues with degraded capabilities.",
                recovery_steps=("Review warning impact and continue or remediate.",),
                next_command="none",
                deviation=runtime.deviation.__dict__ if runtime.deviation is not None else {},
                context=reason_context,
            ).to_dict()
        else:
            reason_payload = build_reason_payload(
                status="OK",
                reason_code=REASON_CODE_NONE,
                surface=target_path,
                impact="all checks passed",
                next_command="none",
                recovery_steps=(),
                context=reason_context,
            ).to_dict()
    except Exception as exc:
        failure_class, failure_detail = canonicalize_reason_payload_failure(exc)
        reason_payload = {
            "status": "BLOCKED",
            "reason_code": BLOCKED_ENGINE_SELFCHECK,
            "surface": target_path,
            "signals_used": ("reason_payload_builder",),
            "primary_action": "Fix reason-payload schema/registry and rerun.",
            "recovery_steps": ("Run diagnostics/schema_selfcheck.py and restore schema integrity.",),
            "next_command": "show diagnostics",
            "impact": "Engine blocked to preserve deterministic governance contracts.",
            "missing_evidence": (),
            "deviation": {
                "failure_class": failure_class,
                "failure_detail": failure_detail,
            },
            "expiry": "none",
            "context": {
                "failure_class": failure_class,
                "failure_detail": failure_detail,
                "previous_reason_code": parity["reason_code"],
            },
        }

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
        missing_evidence=stale_required_evidence if stale_required_evidence else missing_evidence,
        repo_doc_evidence=repo_doc_evidence,
        precedence_events=tuple(precedence_events),
        prompt_events=tuple(prompt_events),
    )
