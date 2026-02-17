"""Wave engine orchestrator with deterministic gates and parity outputs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import re
from typing import Mapping

from governance.context.repo_context_resolver import RepoRootResolutionResult, resolve_repo_root
from governance.engine.adapters import HostAdapter, HostCapabilities, OperatingMode
from governance.engine.canonical_json import canonical_json_hash
from governance.engine.error_reason_router import canonicalize_reason_payload_failure
from governance.engine.interaction_gate import evaluate_interaction_gate
from governance.engine.reason_codes import (
    BLOCKED_ENGINE_SELFCHECK,
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
    INTERACTIVE_REQUIRED_IN_PIPELINE,
    NOT_VERIFIED_EVIDENCE_STALE,
    NOT_VERIFIED_MISSING_EVIDENCE,
    POLICY_PRECEDENCE_APPLIED,
    PROMPT_BUDGET_EXCEEDED,
    REPO_CONSTRAINT_UNSUPPORTED,
    REPO_CONSTRAINT_WIDENING,
    REPO_DOC_UNSAFE_DIRECTIVE,
    REASON_CODE_NONE,
    WARN_MODE_DOWNGRADED,
    WARN_PERMISSION_LIMITED,
)
from governance.engine.mode_repo_rules import (
    RepoDocEvidence,
    classify_repo_doc,
    compute_repo_doc_hash,
    resolve_prompt_budget,
    summarize_classification,
)
from governance.engine.reason_payload import (
    ReasonPayload,
    build_reason_payload,
    validate_reason_payload,
)
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

_EVIDENCE_CLASS_DEFAULT_TTL_SECONDS: dict[str, int] = {
    "identity_signal": 0,
    "preflight_probe": 0,
    "gate_evidence": 24 * 60 * 60,
    "runtime_diagnostic": 24 * 60 * 60,
    "operator_provided": 24 * 60 * 60,
}


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

    return canonical_json_hash(payload)


def _canonical_claim_evidence_id(claim: str) -> str:
    """Convert a human claim label into canonical claim evidence ID."""

    normalized = re.sub(r"[^a-z0-9]+", "-", claim.strip().lower()).strip("-")
    if not normalized:
        return ""
    return f"claim/{normalized}"


def _parse_observed_at(raw: object) -> datetime | None:
    """Parse observed-at timestamps in UTC, returning None for invalid values."""

    if not isinstance(raw, str) or not raw.strip():
        return None
    value = raw.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _resolve_ttl_seconds(item: Mapping[str, object]) -> int:
    """Resolve evidence TTL seconds from item metadata with deterministic defaults."""

    ttl_raw = item.get("ttl_seconds")
    if isinstance(ttl_raw, int) and ttl_raw >= 0:
        return ttl_raw
    evidence_class = str(item.get("evidence_class", "gate_evidence")).strip().lower()
    return _EVIDENCE_CLASS_DEFAULT_TTL_SECONDS.get(evidence_class, 24 * 60 * 60)


def _is_stale(*, observed_at: datetime | None, ttl_seconds: int, now_utc: datetime) -> bool:
    """Return True when evidence is stale relative to the configured TTL."""

    if observed_at is None:
        return True
    if ttl_seconds == 0:
        # ttl=0 means fresh probe per run; accept only near-current evidence.
        return now_utc - observed_at > timedelta(seconds=1)
    return now_utc - observed_at > timedelta(seconds=ttl_seconds)


def _extract_verified_claim_evidence_ids(
    session_state_document: Mapping[str, object] | None,
    *,
    now_utc: datetime,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Extract verified claim evidence IDs and stale claim IDs from build evidence."""

    if session_state_document is None:
        return (), ()

    root: Mapping[str, object]
    session_state = session_state_document.get("SESSION_STATE")
    if isinstance(session_state, Mapping):
        root = session_state
    else:
        root = session_state_document

    build_evidence = root.get("BuildEvidence")
    if not isinstance(build_evidence, Mapping):
        return (), ()

    observed: set[str] = set()
    stale: set[str] = set()

    claims_stale = build_evidence.get("claims_stale")
    if isinstance(claims_stale, list):
        for entry in claims_stale:
            if isinstance(entry, str) and entry.strip():
                stale.add(entry.strip())

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
            candidate_id = ""
            if isinstance(evidence_id, str) and evidence_id.strip():
                candidate_id = evidence_id.strip()
            else:
                claim_id = item.get("claim_id")
                if isinstance(claim_id, str) and claim_id.strip():
                    candidate_id = claim_id.strip()
                else:
                    claim_label = item.get("claim")
                    if isinstance(claim_label, str) and claim_label.strip():
                        candidate_id = _canonical_claim_evidence_id(claim_label)

            if not candidate_id:
                continue

            observed_at = _parse_observed_at(item.get("observed_at"))
            ttl_seconds = _resolve_ttl_seconds(item)
            if _is_stale(observed_at=observed_at, ttl_seconds=ttl_seconds, now_utc=now_utc):
                stale.add(candidate_id)
            else:
                observed.add(candidate_id)

    stale -= observed
    return tuple(sorted(observed)), tuple(sorted(stale))


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
    repo_identity: str,
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
        "repo_identity": repo_identity,
        "repo_source": repo_context.source,
        "repo_is_git_root": repo_context.is_git_root,
        "ruleset_hash": ruleset_hash,
    }
    return _hash_payload(payload)


def _extract_repo_identity(session_state_document: Mapping[str, object] | None) -> str:
    """Extract stable repo identity (repo_fingerprint) from SESSION_STATE."""
    if session_state_document is None:
        return ""
    session_state = session_state_document.get("SESSION_STATE")
    root = session_state if isinstance(session_state, Mapping) else session_state_document
    value = root.get("repo_fingerprint")
    return value.strip() if isinstance(value, str) else ""


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
    interactive_required: bool = False,
    why_interactive_required: str | None = None,
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
    evaluation_now = now_utc if now_utc is not None else datetime.now(timezone.utc)
    verified_claim_evidence, stale_claim_evidence = _extract_verified_claim_evidence_ids(
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
        decision = "deny"
        if effective_mode == "pipeline":
            gate_blocked = True
            gate_reason_code = REPO_CONSTRAINT_WIDENING
            decision = "deny"
        elif widening_approved:
            decision = "allow"
            precedence_events.append(
                {
                    "event": "POLICY_PRECEDENCE_APPLIED",
                    "winner_layer": "mode_policy",
                    "loser_layer": "repo_doc_constraints",
                    "requested_action": requested_action or "widen_constraint",
                    "decision": decision,
                    "reason_code": POLICY_PRECEDENCE_APPLIED,
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
            gate_reason_code = REPO_CONSTRAINT_WIDENING
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
    repo_identity = _extract_repo_identity(session_state_document) or str(repo_context.repo_root)

    activation_hash = _build_activation_hash(
        phase=phase,
        active_gate=active_gate,
        next_gate_condition=next_gate_condition,
        target_path=target_path,
        effective_operating_mode=effective_mode,
        capabilities_hash=capabilities_hash,
        repo_context=repo_context,
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
        runtime = EngineRuntimeDecision(
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
        fallback = ReasonPayload(
            status="BLOCKED",
            reason_code=BLOCKED_ENGINE_SELFCHECK,
            surface=target_path,
            signals_used=("reason_payload_builder",),
            primary_action="Fix reason-payload schema/registry and rerun.",
            recovery_steps=("Run diagnostics/schema_selfcheck.py and restore schema integrity.",),
            next_command="show diagnostics",
            impact="Engine blocked to preserve deterministic governance contracts.",
            missing_evidence=(),
            deviation={"failure_class": failure_class, "failure_detail": failure_detail},
            expiry="none",
            context={
                "failure_class": failure_class,
                "failure_detail": failure_detail,
                "previous_reason_code": parity["reason_code"],
            },
        )
        fallback_errors = validate_reason_payload(fallback)
        if fallback_errors:
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
                    "failure_class": "reason_payload_fallback_invalid",
                    "failure_detail": "contract_violation",
                },
                "expiry": "none",
                "context": {
                    "failure_class": "reason_payload_fallback_invalid",
                    "failure_detail": "contract_violation",
                    "previous_reason_code": parity["reason_code"],
                },
            }
        else:
            reason_payload = fallback.to_dict()

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
