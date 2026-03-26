#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Mapping

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).absolute().parents[2]))

from governance_runtime.application.use_cases.phase_router import route_phase
from governance_runtime.application.use_cases.rework_clarification import consume_rework_clarification_state
from governance_runtime.application.use_cases.session_state_helpers import with_kernel_result
from governance_runtime.application.services.state_accessor import get_phase
from governance_runtime.domain.phase_state_machine import normalize_phase_token
from governance_runtime.infrastructure.json_store import load_json as _load_json
from governance_runtime.infrastructure.session_pointer import (
    parse_session_pointer_document,
    resolve_active_session_state_path,
)
from governance_runtime.infrastructure.time_utils import now_iso as _now_iso
from governance_runtime.infrastructure.json_store import append_jsonl as _append_jsonl
from governance_runtime.infrastructure.json_store import write_json_atomic as _write_json_atomic
from governance_runtime.infrastructure.session_locator import resolve_active_session_paths


BLOCKED_P4_INTAKE_MISSING_EVIDENCE = "BLOCKED-P4-INTAKE-MISSING-EVIDENCE"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _canonicalize_text(raw: str) -> str:
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines).strip()


def _digest(payload: str, *, kind: str) -> str:
    material = f"{kind}:{payload}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _payload(status: str, **kwargs: object) -> dict[str, object]:
    out: dict[str, object] = {"status": status}
    out.update(kwargs)
    return out


def _ticket_record_path(session_path: Path) -> Path:
    return session_path.parent / "ticket-record.json"


def _persist_ticket_record(*, session_path: Path, repo_fingerprint: str, state: Mapping[str, Any]) -> Path:
    payload = {
        "schema": "governance.ticket-record.v1",
        "repo_fingerprint": repo_fingerprint,
        "source": "phase4-intake-bridge",
        "updated_at": _now_iso(),
        "ticket": str(state.get("Ticket") or ""),
        "task": str(state.get("Task") or ""),
        "ticket_digest": str(state.get("TicketRecordDigest") or ""),
        "task_digest": str(state.get("TaskRecordDigest") or ""),
    }
    ticket_path = _ticket_record_path(session_path)
    _write_json_atomic(ticket_path, payload)
    return ticket_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Persist Phase-4 intake evidence and reroute kernel state")
    parser.add_argument("--ticket-text", default="", help="Ticket text input")
    parser.add_argument("--task-text", default="", help="Task text input")
    parser.add_argument("--ticket-file", default="", help="Path to ticket markdown/text file")
    parser.add_argument("--task-file", default="", help="Path to task markdown/text file")
    parser.add_argument("--feature-class", default="", help="Optional FeatureComplexity.Class")
    parser.add_argument("--feature-reason", default="", help="Optional FeatureComplexity.Reason")
    parser.add_argument("--feature-planning-depth", default="", help="Optional FeatureComplexity.PlanningDepth")
    parser.add_argument("--quiet", action="store_true", help="Emit JSON payload only")
    args = parser.parse_args(argv)

    try:
        ticket_source = args.ticket_text
        if args.ticket_file:
            ticket_source = _read_text(Path(args.ticket_file))
        task_source = args.task_text
        if args.task_file:
            task_source = _read_text(Path(args.task_file))
    except Exception as exc:
        payload = _payload(
            "blocked",
            reason_code=BLOCKED_P4_INTAKE_MISSING_EVIDENCE,
            reason="intake-source-unreadable",
            observed=str(exc),
            recovery_action="provide readable --ticket-text/--task-text or valid --ticket-file/--task-file",
        )
        print(json.dumps(payload, ensure_ascii=True))
        return 2

    ticket = _canonicalize_text(ticket_source)
    task = _canonicalize_text(task_source)
    if not ticket and not task:
        payload = _payload(
            "blocked",
            reason_code=BLOCKED_P4_INTAKE_MISSING_EVIDENCE,
            reason="missing-intake-evidence",
            recovery_action="provide non-empty ticket or task input via text or file",
        )
        print(json.dumps(payload, ensure_ascii=True))
        return 2

    has_fc_inputs = any(
        bool(str(token or "").strip())
        for token in (args.feature_class, args.feature_reason, args.feature_planning_depth)
    )
    has_fc_complete = all(
        bool(str(token or "").strip())
        for token in (args.feature_class, args.feature_reason, args.feature_planning_depth)
    )
    if has_fc_inputs and not has_fc_complete:
        payload = _payload(
            "blocked",
            reason_code=BLOCKED_P4_INTAKE_MISSING_EVIDENCE,
            reason="feature-complexity-incomplete",
            recovery_action="provide all FeatureComplexity fields or omit them",
        )
        print(json.dumps(payload, ensure_ascii=True))
        return 2

    try:
        session_path, repo_fingerprint, _, _ = resolve_active_session_paths()
        document = _load_json(session_path)
        state = document.get("SESSION_STATE")
        if not isinstance(state, dict):
            raise RuntimeError("SESSION_STATE root missing")

        phase_before = get_phase(state)

        # When /ticket is executed from Phase-6 rework clarification,
        # consume clarification state and force deterministic Phase-4 re-entry
        # before routing into the development path.
        if consume_rework_clarification_state(state, consumed_by="ticket", consumed_at=_now_iso()):
            state["phase"] = "4"
            state["next"] = "4"
            state["active_gate"] = "Ticket Input Gate"
            state["next_gate_condition"] = "Collect ticket and planning constraints"

        if ticket:
            state["Ticket"] = ticket
            state["TicketRecordDigest"] = _digest(ticket, kind="ticket")
        if task:
            state["Task"] = task
            state["TaskRecordDigest"] = _digest(task, kind="task")
        state["phase4_intake_evidence"] = True
        state["phase4_intake_source"] = "phase4-intake-bridge"
        state["phase4_intake_updated_at"] = _now_iso()
        if has_fc_complete:
            state["FeatureComplexity"] = {
                "Class": args.feature_class.strip(),
                "Reason": args.feature_reason.strip(),
                "PlanningDepth": args.feature_planning_depth.strip(),
            }

        routed = route_phase(
            requested_phase=normalize_phase_token(get_phase(state) or "4") or "4",
            requested_active_gate=str(state.get("active_gate") or "Ticket Input Gate"),
            requested_next_gate_condition=str(state.get("next_gate_condition") or "Persist ticket intake evidence"),
            session_state_document=document,
            repo_is_git_root=True,
            live_repo_fingerprint=repo_fingerprint,
        )
        document = dict(
            with_kernel_result(
                document,
                phase=routed.phase,
                next_token=routed.next_token,
                active_gate=routed.active_gate,
                next_gate_condition=routed.next_gate_condition,
                status=routed.status,
                spec_hash=routed.spec_hash,
                spec_path=routed.spec_path,
                spec_loaded_at=routed.spec_loaded_at,
                log_paths=routed.log_paths,
                event_id=routed.event_id,
                plan_record_status=routed.plan_record_status,
                plan_record_versions=routed.plan_record_versions,
            )
        )
        _write_json_atomic(session_path, document)
        state_after = document.get("SESSION_STATE")
        state_after_map = state_after if isinstance(state_after, dict) else {}
        ticket_record_path = _persist_ticket_record(
            session_path=session_path,
            repo_fingerprint=repo_fingerprint,
            state=state_after_map,
        )
        _append_jsonl(
            session_path.parent / "logs" / "events.jsonl",
            {
                "event": "phase4-intake-persisted",
                "observed_at": _now_iso(),
                "repo_fingerprint": repo_fingerprint,
                "phase_before": phase_before,
                "phase_after": routed.phase,
                "ticket_digest_present": bool(ticket),
                "task_digest_present": bool(task),
                "source": "phase4-intake-bridge",
                "ticket_record_path": str(ticket_record_path),
            },
        )
    except Exception as exc:
        payload = _payload(
            "blocked",
            reason_code=BLOCKED_P4_INTAKE_MISSING_EVIDENCE,
            reason="intake-persist-failed",
            observed=str(exc),
            recovery_action="verify active workspace pointer/session and rerun intake command",
        )
        print(json.dumps(payload, ensure_ascii=True))
        return 2

    payload = _payload(
        "ok",
        reason="phase4-intake-persisted",
        repo_fingerprint=repo_fingerprint,
        session_state_path=str(session_path),
        phase_before=phase_before,
        phase_after=routed.phase,
        next_phase=str(routed.phase or ""),
        next_gate=routed.active_gate,
        next_action="run /continue.",
        active_gate=routed.active_gate,
        ticket_record_path=str(ticket_record_path),
    )
    if args.quiet:
        print(json.dumps(payload, ensure_ascii=True))
    else:
        print(json.dumps(payload, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
