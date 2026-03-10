#!/usr/bin/env python3
"""Review decision rail — ``/review-decision`` entrypoint.

Accepts a final review decision (``approve | changes_requested | reject``)
at the Evidence Presentation Gate in Phase 6.

Behaviour by decision:
- **approve**: sets ``workflow_complete=True``, ``active_gate="Workflow Complete"``
  — terminal state within Phase 6, no new token.
- **changes_requested**: resets ``implementation_review_complete=False`` for a
  Phase 6 loop-reset. The internal review iterations restart.
- **reject**: transitions back to Phase 4 with ``active_gate="Ticket Input Gate"``.

All decisions are written to ``SESSION_STATE["UserReviewDecision"]`` and an
audit event is appended to the workspace events JSONL.

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).absolute().parents[2]))

from governance.domain import reason_codes
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
        # Write terminal surfacing fields so downstream consumers
        # (session_reader, phase_api) can derive completion without
        # re-running the kernel.
        state["active_gate"] = "Workflow Complete"
        state["next_gate_condition"] = "Workflow approved. No further action required."
        state["phase6_state"] = "phase6_completed"
        state["implementation_review_complete"] = True
        # Ensure ImplementationReview block is also consistent.
        review_block = state.get("ImplementationReview")
        if isinstance(review_block, dict):
            review_block["implementation_review_complete"] = True
            review_block["completion_status"] = "phase6-completed"
            state["ImplementationReview"] = review_block
    elif normalized == "changes_requested":
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
        state["phase6_state"] = "phase6_in_progress"
        # Clear any previous workflow_complete flag
        state.pop("workflow_complete", None)
        state.pop("WorkflowComplete", None)
    elif normalized == "reject":
        # Return to Phase 4 with a consistent visible return path.
        state["Phase"] = "4"
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
        next_action=_next_action_hint(normalized),
    )


def _next_action_hint(decision: str) -> str:
    """Return a human-readable next action hint for the applied decision."""
    if decision == "approve":
        return "Workflow complete. No further action required."
    if decision == "changes_requested":
        return "Changes requested. Address feedback, then run /continue to restart the implementation review loop."
    if decision == "reject":
        return "Review rejected. Workflow returned to Phase 4. Provide updated ticket/task details to restart."
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
