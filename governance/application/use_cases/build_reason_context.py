"""Reason context and payload builders for orchestrator output."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping

from governance.application.ports.gateways import build_reason_payload, canonicalize_reason_payload_failure
from governance.application.use_cases.session_state_helpers import extract_repo_identity
from governance.domain.reason_codes import (
    BLOCKED_ENGINE_SELFCHECK,
    BLOCKED_FINGERPRINT_MISMATCH,
    BLOCKED_MISSING_BINDING_FILE,
    BLOCKED_STATE_OUTDATED,
    BLOCKED_WORKSPACE_PERSISTENCE,
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
    REASON_CODE_NONE,
    REPO_CONSTRAINT_UNSUPPORTED,
    REPO_CONSTRAINT_WIDENING,
    REPO_DOC_UNSAFE_DIRECTIVE,
)

if TYPE_CHECKING:
    from pathlib import Path
    from governance.application.ports.gateways import RepoDocEvidence


def build_hash_mismatch_diff(
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


def build_reason_context(
    *,
    parity_reason_code: str,
    repo_doc_evidence: "RepoDocEvidence | None",
    unsafe_directive: Any | None,
    requested_action: str | None,
    widening_from: str | None,
    widening_to: str | None,
    repo_doc_path: str | None,
    target_path: str,
    phase: str,
    active_gate: str,
    why_interactive_required: str | None,
    effective_mode: str,
    budget: Any,
    prompt_used_total: int,
    prompt_used_repo_docs: int,
    prompt_events: list[dict[str, object]],
    repo_constraint_topic: str | None,
    precedence_events: list[dict[str, object]],
    session_state_document: Mapping[str, object] | None,
    repo_context_repo_root: "Path | None",
    workspace_memory_confirmation: str,
) -> dict[str, object]:
    """Build reason context dict based on parity reason code."""
    reason_context: dict[str, object] = {}

    if parity_reason_code == REPO_DOC_UNSAFE_DIRECTIVE and repo_doc_evidence is not None and unsafe_directive is not None:
        reason_context = {
            "doc_path": repo_doc_evidence.doc_path,
            "doc_hash": repo_doc_evidence.doc_hash,
            "directive_excerpt": unsafe_directive.excerpt,
            "classification_rule_id": unsafe_directive.rule_id,
            "pointers": [repo_doc_evidence.doc_path],
        }
    elif parity_reason_code == REPO_CONSTRAINT_WIDENING:
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
    elif parity_reason_code == INTERACTIVE_REQUIRED_IN_PIPELINE:
        reason_context = {
            "requested_action": requested_action or "interactive_required",
            "why_interactive_required": why_interactive_required or "approval_required",
            "pointers": [target_path],
        }
    elif parity_reason_code in {
        BLOCKED_WORKSPACE_PERSISTENCE,
        PERSIST_CONFIRMATION_REQUIRED,
        PERSIST_CONFIRMATION_INVALID,
        PERSIST_DISALLOWED_IN_PIPELINE,
        PERSIST_PHASE_MISMATCH,
        PERSIST_GATE_NOT_APPROVED,
    }:
        reason_context = {
            "requested_action": requested_action or "none",
            "required_confirmation": workspace_memory_confirmation,
            "phase": phase,
            "active_gate": active_gate,
            "pointers": [target_path],
        }
    elif parity_reason_code == BLOCKED_STATE_OUTDATED:
        reason_context = {
            "requested_action": requested_action or "none",
            "phase": phase,
            "active_gate": active_gate,
            "policy": "phase-4-planning-only-no-code-output",
            "pointers": [target_path],
        }
    elif parity_reason_code == BLOCKED_FINGERPRINT_MISMATCH:
        reason_context = {
            "failure_class": "fingerprint_cross_wire",
            "session_fingerprint": extract_repo_identity(session_state_document),
            "live_repo_root": str(repo_context_repo_root) if repo_context_repo_root else "unknown",
            "pointers": [target_path],
        }
    elif parity_reason_code == PROMPT_BUDGET_EXCEEDED:
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
    elif parity_reason_code == REPO_CONSTRAINT_UNSUPPORTED:
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

    return reason_context


def build_orchestrator_reason_payload(
    *,
    parity_status: str,
    parity_reason_code: str,
    target_path: str,
    missing_evidence: tuple[str, ...],
    stale_required_evidence: tuple[str, ...],
    repo_constraint_topic: str | None,
    reason_context: dict[str, object],
    hash_diff: dict[str, str],
    runtime_deviation: Any | None,
) -> dict[str, object]:
    """Build reason payload from parity output."""
    try:
        if parity_status == "blocked":
            blocked_missing_evidence = missing_evidence
            if parity_reason_code == BLOCKED_MISSING_BINDING_FILE:
                blocked_missing_evidence = ("${USER_HOME}/.config/opencode/commands/governance.paths.json",)
            reason_payload = build_reason_payload(
                status="BLOCKED",
                reason_code=parity_reason_code,
                surface=target_path,
                signals_used=("write_policy", "mode_policy", "capabilities", "hash_gate"),
                primary_action="Resolve the active blocker for this gate.",
                recovery_steps=("Collect required evidence and rerun deterministic checks.",),
                next_command="show diagnostics",
                impact="Workflow is blocked until the issue is fixed.",
                missing_evidence=blocked_missing_evidence,
                deviation=hash_diff,
                context=reason_context,
            ).to_dict()
        elif parity_status == "not_verified":
            not_verified_missing = stale_required_evidence if stale_required_evidence else missing_evidence
            if not not_verified_missing and parity_reason_code == REPO_CONSTRAINT_UNSUPPORTED:
                not_verified_missing = (repo_constraint_topic or "repo_constraint_unsupported",)
            not_verified_signals = ("evidence_freshness",) if stale_required_evidence else ("evidence_requirements",)
            not_verified_primary_action = (
                "Refresh stale evidence and rerun."
                if stale_required_evidence
                else "Provide missing evidence and rerun."
            )
            reason_payload = build_reason_payload(
                status="NOT_VERIFIED",
                reason_code=parity_reason_code,
                surface=target_path,
                signals_used=not_verified_signals,
                primary_action=not_verified_primary_action,
                recovery_steps=("Gather host evidence for all required claims.",),
                next_command="show diagnostics",
                impact="Claims are not evidence-backed yet.",
                missing_evidence=not_verified_missing,
                context=reason_context,
            ).to_dict()
        elif parity_reason_code.startswith("WARN-") or parity_reason_code == REPO_CONSTRAINT_WIDENING:
            reason_payload = build_reason_payload(
                status="WARN",
                reason_code=parity_reason_code,
                surface=target_path,
                signals_used=("degraded_execution",),
                impact="Execution continues with degraded capabilities.",
                recovery_steps=("Review warning impact and continue or remediate.",),
                next_command="none",
                deviation=runtime_deviation.__dict__ if runtime_deviation is not None else {},
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
                "previous_reason_code": parity_reason_code,
            },
        }

    return reason_payload
