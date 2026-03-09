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

import json
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).absolute().parents[2]))

from governance.domain import reason_codes
from governance.infrastructure.adapters.logging.event_sink import write_jsonl_event

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
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


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
        # Return to Phase 4
        state["Phase"] = "4"
        state["phase_transition_evidence"] = False
        # Clear Phase 6 state
        state.pop("workflow_complete", None)
        state.pop("WorkflowComplete", None)
        state.pop("implementation_review_complete", None)

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
