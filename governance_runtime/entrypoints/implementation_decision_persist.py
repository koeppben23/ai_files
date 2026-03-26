#!/usr/bin/env python3
"""Implementation decision rail -- ``/implementation-decision`` entrypoint."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from pathlib import Path
from typing import Mapping

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).absolute().parents[2]))

from governance_runtime.domain import reason_codes
from governance_runtime.contracts.enforcement import require_complete_contracts
from governance_runtime.receipts.match import ReceiptMatchContext, validate_receipt_match
from governance_runtime.infrastructure.adapters.logging.event_sink import write_jsonl_event
from governance_runtime.infrastructure.json_store import load_json as _load_json
from governance_runtime.infrastructure.json_store import write_json_atomic as _write_json_atomic
from governance_runtime.infrastructure.session_pointer import (
    parse_session_pointer_document,
    resolve_active_session_state_path,
)
from governance_runtime.infrastructure.time_utils import now_iso as _now_iso
from governance_runtime.infrastructure.session_locator import resolve_active_session_paths


def _resolve_active_session_path() -> tuple[Path, Path]:
    session_path, _, _, workspace_dir = resolve_active_session_paths()
    events_path = workspace_dir / "logs" / "events.jsonl"
    return session_path, events_path


VALID_DECISIONS = frozenset({"approve", "changes_requested", "reject"})
BLOCKED_IMPLEMENTATION_DECISION_INVALID = reason_codes.BLOCKED_REVIEW_DECISION_INVALID




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

def _in_implementation_presentation_gate(state: Mapping[str, object]) -> bool:
    gate = str(state.get("active_gate") or state.get("ActiveGate") or "").strip().lower()
    return gate == "implementation presentation gate"


def _implementation_package_ready(state: Mapping[str, object]) -> tuple[bool, str]:
    def _implementation_digest() -> str:
        changed_files = state.get("implementation_package_changed_files") or state.get("implementation_changed_files") or []
        findings_fixed = state.get("implementation_package_findings_fixed") or state.get("implementation_findings_fixed") or []
        findings_open = state.get("implementation_package_findings_open") or state.get("implementation_open_findings") or []
        checks = state.get("implementation_package_checks") or []
        source = "|".join(
            [
                str(state.get("implementation_package_review_object") or "Implemented result review"),
                str(state.get("implementation_package_plan_reference") or "latest approved plan record"),
                json.dumps(changed_files, ensure_ascii=True, sort_keys=True),
                json.dumps(findings_fixed, ensure_ascii=True, sort_keys=True),
                json.dumps(findings_open, ensure_ascii=True, sort_keys=True),
                json.dumps(checks, ensure_ascii=True, sort_keys=True),
                str(state.get("implementation_package_stability") or ""),
            ]
        )
        return hashlib.sha256(source.encode("utf-8")).hexdigest()

    presented = bool(state.get("implementation_package_presented"))
    stable = bool(state.get("implementation_quality_stable"))
    changed_files = state.get("implementation_package_changed_files") or state.get("implementation_changed_files")
    if not presented:
        return False, "implementation_package_presented=false"
    if not stable:
        return False, "implementation_quality_stable=false"
    if not isinstance(changed_files, list) or not changed_files:
        return False, "implementation_changed_files=missing"
    receipt = state.get("implementation_package_presentation_receipt")
    if not isinstance(receipt, Mapping):
        return False, "implementation_package_presentation_receipt=missing"
    receipt_digest = str(receipt.get("digest") or "").strip()
    receipt_contract = str(receipt.get("contract") or "").strip()
    receipt_presented_at = str(receipt.get("presented_at") or "").strip()
    current_materialization_id = str(state.get("session_materialization_event_id") or "").strip()
    current_state_revision = str(state.get("session_state_revision") or "").strip()
    if not receipt_digest:
        return False, "implementation_package_presentation_receipt.digest=missing"
    if receipt_contract != "guided-ui.v1":
        return False, "implementation_package_presentation_receipt.contract!=guided-ui.v1"
    if not receipt_presented_at:
        return False, "implementation_package_presentation_receipt.presented_at=missing"
    if not current_materialization_id:
        return False, "session_materialization_event_id=missing"
    if not current_state_revision:
        return False, "session_state_revision=missing"

    current_session_id = str(state.get("session_run_id") or "").strip()
    if not current_session_id:
        return False, "session_run_id=missing"
    last_state_change_at = str(
        state.get("implementation_package_last_state_change_at")
        or state.get("session_materialized_at")
        or ""
    ).strip()
    matched, reason = validate_receipt_match(
        receipt=receipt,
        context=ReceiptMatchContext(
            expected_receipt_type="implementation_presentation_receipt",
            expected_gate="Implementation Presentation Gate",
            expected_digest=_implementation_digest(),
            expected_session_id=current_session_id,
            expected_state_revision=current_state_revision,
            expected_scope="R-IMPLEMENTATION-DECISION-001",
            last_relevant_state_change_at=last_state_change_at,
        ),
    )
    if not matched:
        return False, f"implementation_package_presentation_receipt.match={reason}"
    if receipt_digest != _implementation_digest():
        return False, "implementation_package_presentation_receipt.digest_mismatch"
    return True, "ready"


def _has_open_critical_findings(state: Mapping[str, object]) -> bool:
    entries = state.get("implementation_open_findings")
    if not isinstance(entries, list):
        return False
    for entry in entries:
        token = str(entry or "").strip().lower()
        if token.startswith("critical:"):
            return True
    return False


def _completion_matrix_ready_for_approve(state: Mapping[str, object]) -> tuple[bool, str]:
    overall = str(
        state.get("completion_matrix_overall_status")
        or state.get("completion_matrix_status")
        or ""
    ).strip().upper()
    if overall != "PASS":
        return False, "completion_matrix_overall_status!=PASS"

    receipt = state.get("completion_matrix_receipt")
    if not isinstance(receipt, Mapping):
        return False, "completion_matrix_receipt=missing"
    if str(receipt.get("receipt_type") or "").strip() != "verification_receipt":
        return False, "completion_matrix_receipt.receipt_type!=verification_receipt"
    if str(receipt.get("status") or "").strip().upper() != "PASS":
        return False, "completion_matrix_receipt.status!=PASS"

    verified_at = str(state.get("completion_matrix_verified_at") or "").strip()
    implementation_changed_at = str(
        state.get("implementation_package_last_state_change_at")
        or state.get("session_materialized_at")
        or ""
    ).strip()
    if not verified_at:
        return False, "completion_matrix_verified_at=missing"
    if implementation_changed_at and verified_at < implementation_changed_at:
        return False, "completion_matrix_verified_at_stale"
    return True, "ready"


def apply_implementation_decision(
    *,
    decision: str,
    session_path: Path,
    events_path: Path | None = None,
    rationale: str = "",
) -> dict[str, object]:
    normalized = decision.strip().lower()
    if normalized not in VALID_DECISIONS:
        return _payload(
            "error",
            reason_code=BLOCKED_IMPLEMENTATION_DECISION_INVALID,
            message=f"Invalid decision '{decision}'. Must be one of: {', '.join(sorted(VALID_DECISIONS))}",
        )

    if not session_path.exists():
        return _payload("error", message="session state file not found")

    state_doc = _load_json(session_path)
    state_obj = state_doc.get("SESSION_STATE")
    state: dict[str, object] = state_obj if isinstance(state_obj, dict) else state_doc  # type: ignore[assignment]

    enforcement = require_complete_contracts(
        repo_root=Path(__file__).absolute().parents[2],
        required_ids=("R-IMPLEMENT-001", "R-COMPLETION-001"),
    )
    if not enforcement.ok:
        return _payload(
            "error",
            reason_code=BLOCKED_IMPLEMENTATION_DECISION_INVALID,
            message=f"{enforcement.reason}: {';'.join(enforcement.details)}",
        )

    phase_text = str(state.get("Phase") or state.get("phase") or "").strip()
    if not phase_text.startswith("6"):
        return _payload(
            "error",
            reason_code=BLOCKED_IMPLEMENTATION_DECISION_INVALID,
            message=f"Implementation decision only allowed in Phase 6. Current phase: {phase_text or 'unknown'}",
        )

    if not _in_implementation_presentation_gate(state):
        return _payload(
            "error",
            reason_code=BLOCKED_IMPLEMENTATION_DECISION_INVALID,
            message=(
                "Implementation decision requires the Implementation Presentation Gate. "
                "Run /implement or /continue until active_gate is 'Implementation Presentation Gate'."
            ),
        )

    ready, reason = _implementation_package_ready(state)
    if not ready:
        return _payload(
            "error",
            reason_code=BLOCKED_IMPLEMENTATION_DECISION_INVALID,
            message=f"Implementation decision blocked: package is incomplete ({reason}).",
        )

    if normalized == "approve" and _has_open_critical_findings(state):
        return _payload(
            "error",
            reason_code=BLOCKED_IMPLEMENTATION_DECISION_INVALID,
            message="Implementation decision approve is blocked: critical findings remain open.",
        )
    if normalized == "approve":
        matrix_ready, matrix_reason = _completion_matrix_ready_for_approve(state)
        if not matrix_ready:
            return _payload(
                "error",
                reason_code=BLOCKED_IMPLEMENTATION_DECISION_INVALID,
                message=(
                    "Implementation decision approve is blocked: completion matrix verification is incomplete "
                    f"({matrix_reason}). Run /verify-contracts first."
                ),
            )

    event_id = uuid.uuid4().hex
    ts = _now_iso()
    state["ImplementationDecision"] = {
        "decision": normalized,
        "rationale": rationale,
        "timestamp": ts,
        "event_id": event_id,
    }

    if normalized == "approve":
        state["implementation_accepted"] = True
        state["implementation_status"] = "accepted"
        state["active_gate"] = "Implementation Accepted"
        state["next_gate_condition"] = "Implemented result accepted. Continue with delivery workflow."
        state["implementation_decision_available"] = False
        next_action = "continue delivery workflow for the accepted implementation result."
    elif normalized == "changes_requested":
        state["implementation_accepted"] = False
        state["implementation_status"] = "rework_required"
        state["active_gate"] = "Implementation Rework Clarification Gate"
        state["next_gate_condition"] = (
            "Clarify implementation rework in chat, then run /implement to apply revisions."
        )
        state["implementation_rework_clarification_required"] = True
        state["implementation_decision_available"] = False
        next_action = "describe requested implementation changes in chat."
    else:
        state["implementation_accepted"] = False
        state["implementation_status"] = "blocked"
        state["active_gate"] = "Implementation Blocked"
        state["next_gate_condition"] = (
            "Implementation result rejected. Resolve blockers and rerun /implement before another decision."
        )
        state["implementation_hard_blockers"] = ["critical:IMPLEMENTATION-REJECTED:external rejection"]
        state["implementation_decision_available"] = False
        next_action = "resolve implementation blockers, then run /implement."

    _write_json_atomic(session_path, state_doc)

    audit_event: dict[str, object] = {
        "schema": "opencode.implementation-decision.v1",
        "ts_utc": ts,
        "event_id": event_id,
        "event": "IMPLEMENTATION_DECISION",
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
        implementation_status=str(state.get("implementation_status") or ""),
        next_action=next_action,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Persist /implementation-decision (approve | changes_requested | reject)"
    )
    parser.add_argument("--decision", required=True, help="approve | changes_requested | reject")
    parser.add_argument("--note", default="", help="Optional decision note")
    parser.add_argument("--quiet", action="store_true", help="Emit JSON payload only")
    args = parser.parse_args(argv)

    try:
        session_path, events_path = _resolve_active_session_path()
        payload = apply_implementation_decision(
            decision=str(args.decision),
            session_path=session_path,
            events_path=events_path,
            rationale=str(args.note),
        )
    except Exception as exc:
        payload = _payload(
            "error",
            reason_code=BLOCKED_IMPLEMENTATION_DECISION_INVALID,
            message=f"implementation-decision persist failed: {exc}",
        )

    status = str(payload.get("status") or "error").strip().lower()
    print(json.dumps(payload, ensure_ascii=True))
    return 0 if status == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
