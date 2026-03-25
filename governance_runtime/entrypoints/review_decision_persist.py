#!/usr/bin/env python3
"""Review decision rail — ``/review-decision`` entrypoint.

Accepts a final review decision (``approve | changes_requested | reject``)
at the Evidence Presentation Gate in Phase 6.

Behaviour by decision:
- **approve**: sets ``workflow_complete=True``, ``active_gate="Workflow Complete"``
  — terminal state within Phase 6, no new token.
- **changes_requested**: enters ``active_gate=Rework Clarification Gate`` and
  keeps implementation output blocked until chat clarification yields exactly
  one directed next rail (``/ticket`` | ``/plan`` | ``/continue``).
- **reject**: transitions back to Phase 4 with ``active_gate="Ticket Input Gate"``.

All decisions are written to ``SESSION_STATE["UserReviewDecision"]`` and an
audit event is appended to the workspace events JSONL.

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Mapping

from governance_runtime.application.services.state_accessor import (
    get_review_package,
    is_review_package_presented,
    is_review_package_plan_body_present,
    get_review_package_field,
    get_review_package_receipt,
)
from governance_runtime.application.services.state_normalizer import (
    normalize_with_conflicts,
)
from governance_runtime.kernel.phase_kernel import pipeline_auto_approve_eligible, _workflow_complete as _workflow_complete_state

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).absolute().parents[2]))

from governance_runtime.domain import reason_codes
from governance_runtime.application.services.state_accessor import get_active_gate, get_phase
from governance_runtime.contracts.enforcement import require_complete_contracts
from governance_runtime.receipts.match import ReceiptMatchContext, validate_receipt_match
from governance_runtime.infrastructure.adapters.logging.event_sink import write_jsonl_event
from governance_runtime.infrastructure.json_store import load_json as _load_json
from governance_runtime.infrastructure.json_store import write_json_atomic as _write_json_atomic
from governance_runtime.infrastructure.session_locator import resolve_active_session_paths
from governance_runtime.infrastructure.time_utils import now_iso as _now_iso


def _apply_pipeline_auto_approve(
    *,
    session_path: Path,
    events_path: Path | None = None,
) -> dict[str, object]:
    """Apply pipeline auto-approve at Evidence Presentation Gate.

    This is the canonical auto-approve path integrated into the review decision
    entrypoint. It uses the same persistence and audit mechanisms as human
    review decisions.

    Conditions (checked by pipeline_auto_approve_eligible before calling):
    - effective_operating_mode == "pipeline"
    - Internal review complete
    - At Evidence Presentation Gate
    - No existing review decision
    - Workflow not already complete
    """
    state_doc = _load_json(session_path)
    state_obj = state_doc.get("SESSION_STATE")
    state: dict[str, object] = state_obj if isinstance(state_obj, dict) else state_doc  # type: ignore[assignment]

    event_id = uuid.uuid4().hex
    ts = _now_iso()

    state["UserReviewDecision"] = {
        "decision": "approve",
        "rationale": "Auto-approved by pipeline mode",
        "timestamp": ts,
        "event_id": event_id,
        "source": "pipeline_auto_approve",
    }
    state["workflow_complete"] = True
    state["WorkflowComplete"] = True
    state["governance_status"] = "complete"
    state["implementation_status"] = "authorized"
    state["implementation_authorized"] = True
    state["next_action_command"] = "/implement"
    state["active_gate"] = "Workflow Complete"
    state["next_gate_condition"] = (
        "Workflow auto-approved by pipeline mode. Governance is complete. "
        "Run /implement to start the implementation phase."
    )
    state["phase6_state"] = "6.complete"
    state["implementation_review_complete"] = True

    review_block = state.get("ImplementationReview")
    if isinstance(review_block, dict):
        review_block["implementation_review_complete"] = True
        review_block["completion_status"] = "phase6-completed"
        state["ImplementationReview"] = review_block

    _write_json_atomic(session_path, {"SESSION_STATE": state})

    if events_path:
        event = {
            "event": "pipeline_auto_approve",
            "event_id": event_id,
            "timestamp": ts,
            "mode": "pipeline",
            "result": "approved",
            "decision_source": "pipeline_auto_approve",
        }
        _append_event(events_path, event)

    return _payload(status="ok", message="Workflow auto-approved in pipeline mode.")


def _resolve_active_session_path() -> tuple[Path, Path]:
    session_path, _, _, workspace_dir = resolve_active_session_paths()
    events_path = workspace_dir / "events.jsonl"
    return session_path, events_path


VALID_DECISIONS = frozenset({"approve", "changes_requested", "reject"})

BLOCKED_REVIEW_DECISION_INVALID = reason_codes.BLOCKED_REVIEW_DECISION_INVALID

_PIPELINE_AUTO_APPROVE_REASON = "AUTO-PIPELINE-APPROVE"




def _append_event(path: Path, event: dict[str, object]) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_jsonl_event(path, event, append=True)
        return True
    except Exception:
        return False


def _payload(status: str, **kwargs: object) -> dict[str, object]:
    out: dict[str, object] = {"status": status}
    out.update(kwargs)
    return out


def _is_evidence_presentation_gate(state: Mapping[str, object]) -> bool:
    """Return True when Phase-6 Evidence Presentation Gate is active."""
    return get_active_gate(state).strip().lower() == "evidence presentation gate"


def _review_package_ready(state: Mapping[str, object]) -> tuple[bool, str]:
    result = normalize_with_conflicts(dict(state))
    if result["conflicts"]:
        conflict_details = "; ".join(
            f"{c['field']}: flat={c['flat_value']} vs nested={c['nested_value']}"
            for c in result["conflicts"]
        )
        return False, f"review_package_conflict={conflict_details}"

    canonical = result["canonical"]

    def _review_digest() -> str:
        pkg = canonical.get("review_package", {})
        source = "|".join(
            [
                str(pkg.get("review_object") or ""),
                str(pkg.get("ticket") or ""),
                str(pkg.get("approved_plan_summary") or ""),
                str(pkg.get("plan_body") or ""),
                str(pkg.get("implementation_scope") or ""),
                str(pkg.get("constraints") or ""),
                str(pkg.get("decision_semantics") or ""),
            ]
        )
        return hashlib.sha256(source.encode("utf-8")).hexdigest()

    def _as_int(value: object, fallback: int) -> int:
        try:
            if isinstance(value, bool):
                return int(value)
            if isinstance(value, int):
                return value
            return int(str(value).strip())
        except Exception:
            return fallback

    pkg = canonical.get("review_package", {})
    impl_review = canonical.get("implementation_review", {})

    review_complete = bool(impl_review.get("implementation_review_complete"))
    if not review_complete:
        revision_delta = str(impl_review.get("revision_delta") or "").strip().lower()
        iteration = _as_int(impl_review.get("iteration"), 0)
        min_iterations = _as_int(impl_review.get("min_self_review_iterations"), 1)
        review_complete = iteration >= min_iterations and revision_delta == "none"

    package_presented = bool(pkg.get("presented"))
    plan_body_present = bool(pkg.get("plan_body_present"))
    review_object = str(pkg.get("review_object") or "").strip()

    if not review_complete:
        return False, "implementation_review_complete=false"
    if not package_presented:
        return False, "review_package.presented=false"
    if not plan_body_present:
        return False, "review_package.plan_body_present=false"
    if not review_object:
        return False, "review_package.review_object=missing"
    receipt = pkg.get("presentation_receipt")
    if not isinstance(receipt, Mapping):
        return False, "review_package.presentation_receipt=missing"
    receipt_digest = str(receipt.get("digest") or "").strip()
    receipt_contract = str(receipt.get("contract") or "").strip()
    receipt_presented_at = str(receipt.get("presented_at") or "").strip()
    current_materialization_id = str(canonical.get("session_materialization_event_id") or "").strip()
    current_state_revision = str(canonical.get("session_state_revision") or "").strip()
    if not receipt_digest:
        return False, "review_package.presentation_receipt.digest=missing"
    if receipt_contract != "guided-ui.v1":
        return False, "review_package.presentation_receipt.contract!=guided-ui.v1"
    if not receipt_presented_at:
        return False, "review_package.presentation_receipt.presented_at=missing"
    if not current_materialization_id:
        return False, "session_materialization_event_id=missing"
    if not current_state_revision:
        return False, "session_state_revision=missing"

    receipt_session_id = str(receipt.get("session_id") or "").strip()
    current_session_id = str(canonical.get("session_run_id") or "").strip()
    if not current_session_id:
        return False, "session_run_id=missing"
    last_state_change_at = str(
        pkg.get("last_state_change_at")
        or canonical.get("session_materialized_at")
        or ""
    ).strip()
    matched, reason = validate_receipt_match(
        receipt=receipt,
        context=ReceiptMatchContext(
            expected_receipt_type="governance_review_presentation_receipt",
            expected_gate="Evidence Presentation Gate",
            expected_digest=_review_digest(),
            expected_session_id=current_session_id,
            expected_state_revision=current_state_revision,
            expected_scope="R-REVIEW-DECISION-001",
            last_relevant_state_change_at=last_state_change_at,
        ),
    )
    if not matched:
        return False, f"review_package.presentation_receipt.match={reason}"
    if receipt_digest != _review_digest():
        return False, "review_package.presentation_receipt.digest_mismatch"
    if not receipt_session_id:
        return False, "review_package.presentation_receipt.session_id=missing"
    return True, "ready"


def apply_review_decision(
    *,
    decision: str,
    session_path: Path,
    events_path: Path | None = None,
    rationale: str = "",
    _pre_kernel_state: dict | None = None,
) -> dict[str, object]:
    """Apply a user review decision to the active session state.

    In pipeline mode, when no explicit decision is provided and eligibility
    conditions are met, pipeline auto-approve is applied automatically.

    Parameters
    ----------
    decision:
        One of ``"approve"``, ``"changes_requested"``, ``"reject"``.
        If empty in pipeline mode with eligible conditions, auto-approve is applied.
    session_path:
        Absolute path to the ``SESSION_STATE.json`` file.
    _pre_kernel_state:
        Internal: State snapshot BEFORE kernel evaluation. Used by session_reader
        to check eligibility against the pre-transition state.
    events_path:
        Optional path to the workspace ``events.jsonl`` for audit logging.
    rationale:
        Optional human-readable rationale for the decision.

    Returns
    -------
    dict
        Status payload with ``status`` key (``"ok"`` or ``"error"``).
    """
    normalized = decision.strip().lower()

    # Pipeline auto-approve: when no explicit decision and eligible, apply auto-approve
    if not normalized and session_path.exists():
        if _pre_kernel_state is not None:
            state = _pre_kernel_state
            if isinstance(state, dict) and "SESSION_STATE" in state:
                state = state["SESSION_STATE"]
        else:
            state_doc = _load_json(session_path)
            state_obj = state_doc.get("SESSION_STATE")
            state = state_obj if isinstance(state_obj, dict) else state_doc
        eligible = pipeline_auto_approve_eligible(state)
        if eligible:
            return _apply_pipeline_auto_approve(session_path=session_path, events_path=events_path)

        # Idempotent: empty decision on already-completed workflow returns ok
        if _workflow_complete_state(state):
            return _payload(
                status="ok",
                message="Workflow already approved. No action taken.",
                decision="already_approved",
            )

    if normalized not in VALID_DECISIONS:
        return _payload(
            "error",
            reason_code=BLOCKED_REVIEW_DECISION_INVALID,
            message=f"Invalid decision '{decision}'. Must be one of: {', '.join(sorted(VALID_DECISIONS))}",
        )

    if not session_path.exists():
        return _payload("error", message="session state file not found")

    state_doc = _load_json(session_path)
    state_obj = state_doc.get("SESSION_STATE")
    state: dict[str, object] = state_obj if isinstance(state_obj, dict) else state_doc  # type: ignore[assignment]

    enforcement = require_complete_contracts(
        repo_root=Path(__file__).absolute().parents[2],
        required_ids=("R-REVIEW-DECISION-001",),
    )
    if not enforcement.ok:
        return _payload(
            "error",
            reason_code=BLOCKED_REVIEW_DECISION_INVALID,
            message=f"{enforcement.reason}: {';'.join(enforcement.details)}",
        )

    # Validate we are in Phase 6
    phase_text = get_phase(state)
    if not phase_text.startswith("6"):
        return _payload(
            "error",
            reason_code=BLOCKED_REVIEW_DECISION_INVALID,
            message=f"Review decision only allowed in Phase 6. Current phase: {phase_text}",
        )

    if not _is_evidence_presentation_gate(state):
        return _payload(
            "error",
            reason_code=BLOCKED_REVIEW_DECISION_INVALID,
            message=(
                "Review decision requires Phase 6 Evidence Presentation Gate. "
                "Run /continue until active_gate is 'Evidence Presentation Gate', then run "
                "/review-decision <approve|changes_requested|reject>."
            ),
        )

    package_ready, package_reason = _review_package_ready(state)
    if not package_ready:
        return _payload(
            "error",
            reason_code=BLOCKED_REVIEW_DECISION_INVALID,
            message=(
                "Review decision is not yet allowed: review package is incomplete "
                f"({package_reason}). Run /continue until the full review package is presented."
            ),
        )

    event_id = uuid.uuid4().hex
    ts = _now_iso()

    # Write UserReviewDecision to state
    state["UserReviewDecision"] = {
        "decision": normalized,
        "rationale": rationale,
        "timestamp": ts,
        "event_id": event_id,
    }

    # Apply decision effects
    if normalized == "approve":
        state["workflow_complete"] = True
        state["WorkflowComplete"] = True
        state["governance_status"] = "complete"
        state["implementation_status"] = "authorized"
        state["implementation_authorized"] = True
        state["next_action_command"] = "/implement"
        # Write terminal surfacing fields so downstream consumers
        # (session_reader, phase_api) can derive completion without
        # re-running the kernel.
        state["active_gate"] = "Workflow Complete"
        state["next_gate_condition"] = (
            "Workflow approved. Governance is complete and implementation is authorized. "
            "Run /implement to start the implementation phase."
        )
        state["phase6_state"] = "6.complete"
        state["implementation_review_complete"] = True
        # Ensure ImplementationReview block is also consistent.
        review_block = state.get("ImplementationReview")
        if isinstance(review_block, dict):
            review_block["implementation_review_complete"] = True
            review_block["completion_status"] = "phase6-completed"
            state["ImplementationReview"] = review_block
        state.pop("rework_clarification_consumed", None)
        state.pop("rework_clarification_consumed_by", None)
        state.pop("rework_clarification_consumed_at", None)
    elif normalized == "changes_requested":
        # Enter explicit clarification gate before any further rail is chosen.
        state["Phase"] = "6-PostFlight"
        state["phase"] = "6-PostFlight"
        state["Next"] = "6"
        state["next"] = "6"
        state["active_gate"] = "Rework Clarification Gate"
        state["next_gate_condition"] = (
            "Clarify requested changes in chat, then run directed next rail."
        )
        state["rework_clarification_consumed"] = False
        state.pop("rework_clarification_consumed_by", None)
        state.pop("rework_clarification_consumed_at", None)

        # Loop-reset: clear review completion so the internal review restarts
        state["implementation_review_complete"] = False
        review_block = state.get("ImplementationReview")
        if isinstance(review_block, dict):
            review_block["implementation_review_complete"] = False
            review_block["completion_status"] = "phase6-changes-requested"
            review_block["iteration"] = 0
            review_block["revision_delta"] = "changed"
            state["ImplementationReview"] = review_block
        state["phase6_review_iterations"] = 0
        state["phase6_revision_delta"] = "changed"
        state["phase6_state"] = "6.rework"
        # Clear any previous workflow_complete flag
        state.pop("workflow_complete", None)
        state.pop("WorkflowComplete", None)
    elif normalized == "reject":
        # Return to Phase 4 with a consistent visible return path.
        state["Phase"] = "4"
        state["phase"] = "4"
        state["Next"] = "4"
        state["next"] = "4"
        state["active_gate"] = "Ticket Input Gate"
        state["next_gate_condition"] = (
            "Review rejected. Provide updated ticket/task details to restart."
        )
        state["phase_transition_evidence"] = False
        # Clear Phase 6 state
        state.pop("workflow_complete", None)
        state.pop("WorkflowComplete", None)
        state.pop("implementation_review_complete", None)
        state.pop("phase6_state", None)
        state.pop("rework_clarification_consumed", None)
        state.pop("rework_clarification_consumed_by", None)
        state.pop("rework_clarification_consumed_at", None)

    # Validate review payload before persist (fail-closed)
    from governance_runtime.application.services.state_document_validator import validate_review_payload
    review_payload = {
        "verdict": normalized,
        "rationale": rationale,
        "timestamp": ts,
    }
    payload_validation = validate_review_payload(review_payload)
    if not payload_validation.valid:
        error_messages = [e.message for e in payload_validation.errors]
        return _payload(
            "error",
            reason_code=BLOCKED_REVIEW_DECISION_INVALID,
            message=f"Review payload validation failed: {'; '.join(error_messages)}",
        )

    # Persist
    _write_json_atomic(session_path, state_doc)

    # Audit event
    audit_event: dict[str, object] = {
        "schema": "opencode.review-decision.v1",
        "ts_utc": ts,
        "event_id": event_id,
        "event": "REVIEW_DECISION",
        "decision": normalized,
        "rationale": rationale,
        "phase": phase_text,
    }

    if events_path is not None:
        _append_event(events_path, audit_event)

    return _payload(
        "ok",
        decision=normalized,
        event_id=event_id,
        next_phase=str(state.get("Phase") or state.get("phase") or ""),
        next_gate=str(state.get("active_gate") or ""),
        governance_status=str(state.get("governance_status") or ""),
        implementation_status=str(state.get("implementation_status") or ""),
        next_action=_next_action_hint(normalized),
    )


def _next_action_hint(decision: str) -> str:
    """Return a human-readable next action hint for the applied decision."""
    if decision == "approve":
        return "run /implement."
    if decision == "changes_requested":
        return "describe the requested changes in chat."
    if decision == "reject":
        return "run /ticket with revised task details."
    return ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Persist final /review-decision (approve | changes_requested | reject)"
    )
    parser.add_argument(
        "--decision",
        required=True,
        help="Final review decision: approve | changes_requested | reject",
    )
    parser.add_argument(
        "--note",
        default="",
        help="Optional decision note (non-mutating metadata)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Emit JSON payload only",
    )
    args = parser.parse_args(argv)

    try:
        session_path, events_path = _resolve_active_session_path()
        payload = apply_review_decision(
            decision=str(args.decision),
            session_path=session_path,
            events_path=events_path,
            rationale=str(args.note),
        )
    except Exception as exc:
        payload = _payload(
            "error",
            reason_code=BLOCKED_REVIEW_DECISION_INVALID,
            message=f"review-decision persist failed: {exc}",
        )

    status = str(payload.get("status") or "error").strip().lower()
    print(json.dumps(payload, ensure_ascii=True))
    if status == "ok":
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
