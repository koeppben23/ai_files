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
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).absolute().parents[2]))

from governance.domain import reason_codes
from governance.receipts.match import ReceiptMatchContext, validate_receipt_match
from governance.infrastructure.binding_evidence_resolver import BindingEvidenceResolver
from governance.infrastructure.adapters.logging.event_sink import write_jsonl_event
from governance.infrastructure.fs_atomic import atomic_write_text

VALID_DECISIONS = frozenset({"approve", "changes_requested", "reject"})

BLOCKED_REVIEW_DECISION_INVALID = reason_codes.BLOCKED_REVIEW_DECISION_INVALID


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("json root must be object")
    return payload


def _write_json_atomic(path: Path, payload: Mapping[str, object]) -> None:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    atomic_write_text(path, text)


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

    candidates = (
        state.get("active_gate"),
        state.get("ActiveGate"),
        state.get("Gate"),
    )
    for value in candidates:
        text = str(value or "").strip().lower()
        if text == "evidence presentation gate":
            return True
    return False


def _review_package_ready(state: Mapping[str, object]) -> tuple[bool, str]:
    def _review_digest() -> str:
        source = "|".join(
            [
                str(state.get("review_package_review_object") or ""),
                str(state.get("review_package_ticket") or ""),
                str(state.get("review_package_approved_plan_summary") or ""),
                str(state.get("review_package_plan_body") or ""),
                str(state.get("review_package_implementation_scope") or ""),
                str(state.get("review_package_constraints") or ""),
                str(state.get("review_package_decision_semantics") or ""),
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

    review_complete = bool(state.get("implementation_review_complete"))
    if not review_complete:
        block = state.get("ImplementationReview")
        if isinstance(block, Mapping):
            review_complete = bool(block.get("implementation_review_complete"))
            if not review_complete:
                revision_delta = str(block.get("revision_delta") or "").strip().lower()
                iteration = _as_int(block.get("iteration"), 0)
                min_iterations = _as_int(block.get("min_self_review_iterations"), 1)
                review_complete = iteration >= min_iterations and revision_delta == "none"
    package_presented = bool(state.get("review_package_presented"))
    plan_body_present = bool(state.get("review_package_plan_body_present"))
    review_object = str(state.get("review_package_review_object") or "").strip()

    if not review_complete:
        return False, "implementation_review_complete=false"
    if not package_presented:
        return False, "review_package_presented=false"
    if not plan_body_present:
        return False, "review_package_plan_body_present=false"
    if not review_object:
        return False, "review_package_review_object=missing"
    receipt = state.get("review_package_presentation_receipt")
    if not isinstance(receipt, Mapping):
        return False, "review_package_presentation_receipt=missing"
    receipt_digest = str(receipt.get("digest") or "").strip()
    receipt_contract = str(receipt.get("contract") or "").strip()
    receipt_presented_at = str(receipt.get("presented_at") or "").strip()
    receipt_materialization_id = str(receipt.get("materialization_event_id") or "").strip()
    current_materialization_id = str(state.get("session_materialization_event_id") or "").strip()
    if not receipt_digest:
        return False, "review_package_presentation_receipt.digest=missing"
    if receipt_contract != "guided-ui.v1":
        return False, "review_package_presentation_receipt.contract!=guided-ui.v1"
    if not receipt_presented_at:
        return False, "review_package_presentation_receipt.presented_at=missing"
    if not receipt_materialization_id:
        return False, "review_package_presentation_receipt.materialization_event_id=missing"
    if not current_materialization_id:
        return False, "session_materialization_event_id=missing"
    if receipt_materialization_id != current_materialization_id:
        return False, "review_package_presentation_receipt.materialization_event_id_mismatch"

    receipt_session_id = str(receipt.get("session_id") or "").strip()
    current_session_id = str(state.get("session_run_id") or "").strip()
    if not current_session_id:
        return False, "session_run_id=missing"
    last_state_change_at = str(
        state.get("review_package_last_state_change_at")
        or state.get("session_materialized_at")
        or ""
    ).strip()
    matched, reason = validate_receipt_match(
        receipt=receipt,
        context=ReceiptMatchContext(
            expected_receipt_type="governance_review_presentation_receipt",
            expected_gate="Evidence Presentation Gate",
            expected_digest=_review_digest(),
            expected_session_id=current_session_id,
            expected_state_revision=current_materialization_id,
            expected_scope="R-REVIEW-DECISION-001",
            last_relevant_state_change_at=last_state_change_at,
        ),
    )
    if not matched:
        return False, f"review_package_presentation_receipt.match={reason}"
    if receipt_digest != _review_digest():
        return False, "review_package_presentation_receipt.digest_mismatch"
    if not receipt_session_id:
        return False, "review_package_presentation_receipt.session_id=missing"
    return True, "ready"


def _resolve_active_session_path() -> tuple[Path, Path]:
    """Resolve active workspace session + events path from global pointer."""
    resolver = BindingEvidenceResolver()
    evidence = getattr(resolver, "resolve")(mode="user")
    if evidence.config_root is None or evidence.workspaces_home is None:
        raise RuntimeError("binding unavailable")

    pointer_path = evidence.config_root / "SESSION_STATE.json"
    pointer = _load_json(pointer_path)
    fingerprint = str(pointer.get("activeRepoFingerprint") or "").strip()
    if not fingerprint:
        raise RuntimeError("activeRepoFingerprint missing")

    active_state = str(pointer.get("activeSessionStateFile") or "").strip()
    if active_state:
        session_path = Path(active_state)
    else:
        session_path = evidence.workspaces_home / fingerprint / "SESSION_STATE.json"
    if not session_path.is_absolute():
        raise RuntimeError("activeSessionStateFile must be absolute")
    if not session_path.exists():
        raise RuntimeError("active session missing")

    events_path = session_path.parent / "events.jsonl"
    return session_path, events_path


def apply_review_decision(
    *,
    decision: str,
    session_path: Path,
    events_path: Path | None = None,
    rationale: str = "",
) -> dict[str, object]:
    """Apply a user review decision to the active session state.

    Parameters
    ----------
    decision:
        One of ``"approve"``, ``"changes_requested"``, ``"reject"``.
    session_path:
        Absolute path to the ``SESSION_STATE.json`` file.
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

    # Validate we are in Phase 6
    phase_raw = state.get("Phase") or state.get("phase") or ""
    phase_text = str(phase_raw).strip()
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
        state["phase6_state"] = "phase6_completed"
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
        state["phase6_state"] = "phase6_changes_requested"
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
