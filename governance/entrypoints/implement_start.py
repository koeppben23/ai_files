#!/usr/bin/env python3
"""Implementation start rail -- ``/implement`` entrypoint.

Persists the authoritative governance-to-implementation handoff after an
approved Phase-6 review decision.

This rail is mutating, but intentionally does not trigger automatic code
execution, patch generation, CI, or PR workflows.
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

from governance.infrastructure.binding_evidence_resolver import BindingEvidenceResolver
from governance.infrastructure.adapters.logging.event_sink import write_jsonl_event
from governance.infrastructure.fs_atomic import atomic_write_text
from governance.infrastructure.plan_record_state import resolve_plan_record_signal

BLOCKED_IMPLEMENT_START_INVALID = "BLOCKED-UNSPECIFIED"


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


def _latest_plan_text(plan_record_file: Path) -> str:
    if not plan_record_file.exists():
        return ""
    payload = _load_json(plan_record_file)
    versions = payload.get("versions")
    if not isinstance(versions, list) or not versions:
        return ""
    latest = versions[-1] if isinstance(versions[-1], dict) else {}
    if not isinstance(latest, dict):
        return ""
    return str(latest.get("plan_record_text") or "").strip()


def _build_execution_work_queue(plan_text: str) -> list[str]:
    queue: list[str] = []
    for raw in plan_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(("- ", "* ")):
            queue.append(line[2:].strip())
        elif line[:3].isdigit() and "." in line[:4]:
            queue.append(line.split(".", 1)[1].strip())
    if not queue:
        queue = [
            "Identify files affected by the approved plan",
            "Apply the first implementation change set",
            "Run focused verification for touched areas",
        ]
    return queue[:20]


def _resolve_active_session_path() -> tuple[Path, Path]:
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


def _user_review_decision(state: Mapping[str, object]) -> str:
    decision = state.get("UserReviewDecision")
    if isinstance(decision, Mapping):
        value = decision.get("decision")
        if isinstance(value, str):
            token = value.strip().lower()
            if token in {"approve", "changes_requested", "reject"}:
                return token
    value = state.get("user_review_decision")
    if isinstance(value, str):
        token = value.strip().lower()
        if token in {"approve", "changes_requested", "reject"}:
            return token
    return ""


def start_implementation(
    *,
    session_path: Path,
    events_path: Path | None = None,
    actor: str = "",
    note: str = "",
) -> dict[str, object]:
    if not session_path.exists():
        return _payload("error", reason_code=BLOCKED_IMPLEMENT_START_INVALID, message="session state file not found")

    state_doc = _load_json(session_path)
    state_obj = state_doc.get("SESSION_STATE")
    state: dict[str, object] = state_obj if isinstance(state_obj, dict) else state_doc  # type: ignore[assignment]

    phase_text = str(state.get("Phase") or state.get("phase") or "").strip()
    if not phase_text.startswith("6"):
        return _payload(
            "error",
            reason_code=BLOCKED_IMPLEMENT_START_INVALID,
            message=f"/implement is only allowed in Phase 6. Current phase: {phase_text or 'unknown'}",
        )

    decision = _user_review_decision(state)
    workflow_complete = bool(state.get("workflow_complete") or state.get("WorkflowComplete"))
    if decision != "approve" and not workflow_complete:
        return _payload(
            "error",
            reason_code=BLOCKED_IMPLEMENT_START_INVALID,
            message="/implement requires an approved final review decision at Workflow Complete.",
        )

    active_gate = str(state.get("active_gate") or "").strip().lower()
    if active_gate == "rework clarification gate":
        return _payload(
            "error",
            reason_code=BLOCKED_IMPLEMENT_START_INVALID,
            message="/implement is blocked while rework clarification is pending.",
        )
    if active_gate == "ticket input gate":
        return _payload(
            "error",
            reason_code=BLOCKED_IMPLEMENT_START_INVALID,
            message="/implement is blocked after rejection/restart routing. Re-enter via /ticket.",
        )

    signal = resolve_plan_record_signal(state=state, plan_record_file=session_path.parent / "plan-record.json")
    if signal.versions < 1:
        return _payload(
            "error",
            reason_code=BLOCKED_IMPLEMENT_START_INVALID,
            message="/implement requires persisted plan-record evidence.",
        )

    event_id = uuid.uuid4().hex
    ts = _now_iso()
    plan_record_file = session_path.parent / "plan-record.json"
    plan_text = _latest_plan_text(plan_record_file)
    work_queue = _build_execution_work_queue(plan_text)

    state["implementation_authorized"] = True
    state["implementation_started"] = True
    state["implementation_status"] = "in_progress"
    state["implementation_started_at"] = ts
    state["implementation_started_by"] = actor.strip() or "operator"
    state["implementation_start_note"] = note.strip()
    state["implementation_handoff_plan_record_versions"] = signal.versions
    state["active_gate"] = "Implementation Started"
    state["next_gate_condition"] = (
        "Execution started on the approved implementation plan. "
        "Continue implementation work and produce repository artifacts."
    )
    state["Next"] = "6"
    state["next"] = "6"
    state["implementation_execution_started"] = True
    state["implementation_execution_status"] = "in_progress"
    state["implementation_execution_summary"] = (
        "Execution started from the approved plan record; work queue is materialized."
    )
    state["implementation_artifacts_expected"] = ["source changes", "tests", "review evidence"]
    state["implementation_blockers"] = []
    state["implementation_work_queue"] = work_queue
    state["implementation_current_step"] = work_queue[0] if work_queue else "none"

    _write_json_atomic(session_path, state_doc)

    audit_event: dict[str, object] = {
        "schema": "opencode.implementation-started.v1",
        "ts_utc": ts,
        "event_id": event_id,
        "event": "IMPLEMENTATION_STARTED",
        "phase": phase_text,
        "active_gate": "Implementation Started",
        "decision": decision or "approve",
        "plan_record_versions": signal.versions,
        "actor": state["implementation_started_by"],
        "note": state["implementation_start_note"],
        "execution_status": "in_progress",
        "work_queue_items": len(work_queue),
        "current_step": state["implementation_current_step"],
    }
    if events_path is not None:
        _append_event(events_path, audit_event)

    return _payload(
        "ok",
        event_id=event_id,
        phase="6-PostFlight",
        next="6",
        active_gate="Implementation Started",
        next_gate_condition=state["next_gate_condition"],
        implementation_authorized=True,
        implementation_started=True,
        implementation_started_at=ts,
        implementation_execution_started=True,
        implementation_execution_status="in_progress",
        implementation_execution_summary=state["implementation_execution_summary"],
        implementation_artifacts_expected=state["implementation_artifacts_expected"],
        implementation_blockers=[],
        implementation_work_queue=work_queue,
        implementation_current_step=state["implementation_current_step"],
        next_action="continue implementation work on the approved plan.",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Persist /implement governance-to-implementation handoff")
    parser.add_argument("--actor", default="", help="Optional operator identifier")
    parser.add_argument("--note", default="", help="Optional handoff note")
    parser.add_argument("--quiet", action="store_true", help="Emit JSON payload only")
    args = parser.parse_args(argv)

    try:
        session_path, events_path = _resolve_active_session_path()
        payload = start_implementation(
            session_path=session_path,
            events_path=events_path,
            actor=str(args.actor),
            note=str(args.note),
        )
    except Exception as exc:
        payload = _payload(
            "error",
            reason_code=BLOCKED_IMPLEMENT_START_INVALID,
            message=f"implement start failed: {exc}",
        )

    status = str(payload.get("status") or "error").strip().lower()
    print(json.dumps(payload, ensure_ascii=True))
    if status == "ok":
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
