#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Mapping

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).absolute().parents[2]))

from governance_runtime.domain import reason_codes
from governance_runtime.domain.access_control import Action, AccessDecision, Role, evaluate_access
from governance_runtime.infrastructure.adapters.logging.event_sink import write_jsonl_event
from governance_runtime.infrastructure.binding_evidence_resolver import BindingEvidenceResolver
from governance_runtime.infrastructure.json_store import load_json as _load_json
from governance_runtime.infrastructure.json_store import write_json_atomic as _write_json_atomic
from governance_runtime.infrastructure.session_pointer import (
    parse_session_pointer_document,
    resolve_active_session_state_path,
)
from governance_runtime.infrastructure.time_utils import now_iso as _now_iso

VALID_DECISIONS = frozenset({"approve", "reject", "reset"})




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


def _resolve_active_session_path() -> tuple[Path, Path]:
    resolver = BindingEvidenceResolver()
    evidence = getattr(resolver, "resolve")(mode="user")
    if evidence.config_root is None or evidence.workspaces_home is None:
        raise RuntimeError("binding unavailable")

    pointer_path = evidence.config_root / "SESSION_STATE.json"
    pointer = parse_session_pointer_document(_load_json(pointer_path))
    session_path = resolve_active_session_state_path(pointer, config_root=evidence.config_root)
    fingerprint = str(pointer.get("activeRepoFingerprint") or "").strip()
    if not fingerprint:
        raise RuntimeError("activeRepoFingerprint missing")
    if not session_path.exists():
        raise RuntimeError("active session missing")

    events_path = session_path.parent / "events.jsonl"
    return session_path, events_path


def apply_human_approval(
    *,
    decision: str,
    session_path: Path,
    initiator_role: str,
    approver_role: str,
    events_path: Path | None = None,
    rationale: str = "",
) -> dict[str, object]:
    normalized = decision.strip().lower()
    if normalized not in VALID_DECISIONS:
        return _payload(
            "error",
            reason_code=reason_codes.BLOCKED_REVIEW_DECISION_INVALID,
            message=f"Invalid decision '{decision}'. Must be one of: {', '.join(sorted(VALID_DECISIONS))}",
        )

    if not session_path.exists():
        return _payload("error", message="session state file not found")

    try:
        initiator = Role(initiator_role.strip().lower())
        approver = Role(approver_role.strip().lower())
    except ValueError as exc:
        return _payload(
            "error",
            reason_code=reason_codes.BLOCKED_PERMISSION_DENIED,
            message=f"invalid role: {exc}",
        )

    if normalized == "approve":
        decision_eval = evaluate_access(
            role=approver,
            action=Action.APPROVE_HUMAN_GATE,
            regulated_mode_active=True,
        )
        if decision_eval.decision != AccessDecision.ALLOW:
            return _payload(
                "error",
                reason_code=reason_codes.BLOCKED_PERMISSION_DENIED,
                message=f"approver role not allowed: {decision_eval.reason}",
            )
        if approver == initiator:
            return _payload(
                "error",
                reason_code=reason_codes.BLOCKED_PERMISSION_DENIED,
                message="four-eyes violation: approver must differ from initiator",
            )

    state_doc = _load_json(session_path)
    state_obj = state_doc.get("SESSION_STATE")
    state: dict[str, object] = state_obj if isinstance(state_obj, dict) else state_doc  # type: ignore[assignment]

    event_id = uuid.uuid4().hex
    ts = _now_iso()
    approval_status = "pending"
    if normalized == "approve":
        approval_status = "approved"
    elif normalized == "reject":
        approval_status = "rejected"

    state["requires_human_approval"] = True
    state["approval_status"] = approval_status
    state["role"] = initiator.value
    state["approver_role"] = approver.value
    state["approval_context"] = {
        "decision": normalized,
        "status": approval_status,
        "initiator_role": initiator.value,
        "approver_role": approver.value,
        "rationale": rationale,
        "timestamp": ts,
        "event_id": event_id,
    }

    _write_json_atomic(session_path, state_doc)

    audit_event: dict[str, object] = {
        "schema": "opencode.human-approval.v1",
        "ts_utc": ts,
        "event_id": event_id,
        "event": "HUMAN_APPROVAL_DECISION",
        "decision": normalized,
        "approval_status": approval_status,
        "initiator_role": initiator.value,
        "approver_role": approver.value,
        "rationale": rationale,
    }

    if events_path is not None:
        _append_event(events_path, audit_event)

    return _payload(
        "ok",
        decision=normalized,
        approval_status=approval_status,
        event_id=event_id,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Persist human approval decision for regulated finalization")
    parser.add_argument("--decision", required=True, help="approve | reject | reset")
    parser.add_argument("--initiator-role", default="operator", help="Role that initiated the action")
    parser.add_argument("--approver-role", default="approver", help="Independent human approver role")
    parser.add_argument("--note", default="", help="Optional approval note")
    parser.add_argument("--quiet", action="store_true", help="Emit JSON payload only")
    args = parser.parse_args(argv)

    try:
        session_path, events_path = _resolve_active_session_path()
        payload = apply_human_approval(
            decision=str(args.decision),
            session_path=session_path,
            initiator_role=str(args.initiator_role),
            approver_role=str(args.approver_role),
            events_path=events_path,
            rationale=str(args.note),
        )
    except Exception as exc:
        payload = _payload(
            "error",
            reason_code=reason_codes.BLOCKED_PERMISSION_DENIED,
            message=f"human approval persist failed: {exc}",
        )

    status = str(payload.get("status") or "error").strip().lower()
    print(json.dumps(payload, ensure_ascii=True))
    if status == "ok":
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
