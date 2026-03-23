"""Pipeline Auto-Approve Entrypoint.

Applies auto-approve for pipeline mode at the Evidence Presentation Gate.
This is a SEPARATE path from human review decision (review_decision_persist.py).

Pipeline auto-approve sets:
- workflow_complete = True
- implementation_authorized = True
- Records that the decision was auto-approved (not human)
- Writes audit event for traceability
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
import sys

from governance_runtime.kernel.phase_kernel import pipeline_auto_approve_eligible
from governance_runtime.infrastructure.fs_atomic import atomic_write_json


_BLOCKED_AUTO_APPROVE = "BLOCKED-PIPELINE-AUTO-APPROVE"
_BLOCKED_NOT_ELIGIBLE = "BLOCKED-NOT-ELIGIBLE"


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _payload(status: str, message: str, reason_code: str = "") -> dict:
    result = {"status": status, "message": message}
    if reason_code:
        result["reason_code"] = reason_code
    return result


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _persist(session_path: Path, state: dict) -> None:
    payload = {"SESSION_STATE": state}
    atomic_write_json(session_path, payload, indent=2)


def apply_pipeline_auto_approve(
    *,
    session_path: Path,
    events_path: Path | None = None,
) -> dict:
    """Apply auto-approve for pipeline mode.

    This function is the state mutation layer for pipeline auto-approve.
    It is called after the kernel has determined eligibility via
    pipeline_auto_approve_eligible().

    Args:
        session_path: Path to SESSION_STATE.json
        events_path: Optional path to events.jsonl for audit logging

    Returns:
        dict with status, message, and reason_code
    """
    if not session_path.exists():
        return _payload("error", "session state file not found")

    state_doc = _load_json(session_path)
    state_obj = state_doc.get("SESSION_STATE")
    state: dict = state_obj if isinstance(state_obj, dict) else state_doc

    if not pipeline_auto_approve_eligible(state):
        return _payload(
            "blocked",
            "Pipeline auto-approve is not eligible. Check operating mode, review completion, and gate state.",
            reason_code=_BLOCKED_NOT_ELIGIBLE,
        )

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
    state["phase6_state"] = "phase6_completed"
    state["implementation_review_complete"] = True

    review_block = state.get("ImplementationReview")
    if isinstance(review_block, dict):
        review_block["implementation_review_complete"] = True
        review_block["completion_status"] = "phase6-completed"
        state["ImplementationReview"] = review_block

    _persist(session_path, state)

    if events_path and events_path.parent.exists():
        event = {
            "event": "pipeline_auto_approve",
            "event_id": event_id,
            "timestamp": ts,
            "mode": "pipeline",
            "session_path": str(session_path),
            "result": "approved",
        }
        with events_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=True) + "\n")

    return _payload("ok", "Workflow auto-approved in pipeline mode. Implementation authorized.")


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="pipeline-auto-approve",
        description="Apply pipeline auto-approve at Evidence Presentation Gate",
    )
    parser.add_argument(
        "--session-path",
        required=True,
        help="Path to SESSION_STATE.json",
    )
    parser.add_argument(
        "--events-path",
        help="Path to events.jsonl for audit logging",
    )
    args = parser.parse_args()

    session_path = Path(args.session_path)
    events_path = Path(args.events_path) if args.events_path else None

    result = apply_pipeline_auto_approve(
        session_path=session_path,
        events_path=events_path,
    )

    print(json.dumps(result, ensure_ascii=True))

    if result["status"] == "error":
        return 1
    if result["status"] == "blocked":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
