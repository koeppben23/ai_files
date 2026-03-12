"""Strict receipt matching rules for decision gates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping


def _parse_utc(text: str) -> datetime | None:
    token = str(text or "").strip()
    if not token:
        return None
    if token.endswith("Z"):
        token = token[:-1] + "+00:00"
    try:
        value = datetime.fromisoformat(token)
    except ValueError:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class ReceiptMatchContext:
    expected_receipt_type: str
    expected_gate: str
    expected_digest: str
    expected_session_id: str
    expected_state_revision: str
    expected_scope: str
    last_relevant_state_change_at: str


def validate_receipt_match(*, receipt: Mapping[str, object], context: ReceiptMatchContext) -> tuple[bool, str]:
    receipt_type = str(receipt.get("receipt_type") or "").strip()
    gate = str(receipt.get("gate") or "").strip()
    digest = str(receipt.get("content_digest") or receipt.get("digest") or "").strip()
    session_id = str(receipt.get("session_id") or "").strip()
    state_revision = str(receipt.get("state_revision") or receipt.get("render_event_id") or "").strip()
    scope = str(receipt.get("requirement_scope") or "").strip()
    rendered_at = str(receipt.get("rendered_at") or receipt.get("presented_at") or "").strip()

    if not receipt_type:
        return False, "BLOCKED-RECEIPT-MISSING-TYPE"
    if not gate:
        return False, "BLOCKED-RECEIPT-MISSING-GATE"
    if not digest:
        return False, "BLOCKED-RECEIPT-MISSING-DIGEST"
    if not session_id:
        return False, "BLOCKED-RECEIPT-MISSING-SESSION"
    if not state_revision:
        return False, "BLOCKED-RECEIPT-MISSING-STATE-REVISION"
    if not scope:
        return False, "BLOCKED-RECEIPT-MISSING-SCOPE"
    if not rendered_at:
        return False, "BLOCKED-RECEIPT-MISSING-TIMESTAMP"

    if receipt_type != context.expected_receipt_type:
        return False, "BLOCKED-RECEIPT-TYPE-MISMATCH"
    if gate.lower() != context.expected_gate.strip().lower():
        return False, "BLOCKED-RECEIPT-GATE-MISMATCH"
    if digest != context.expected_digest:
        return False, "BLOCKED-RECEIPT-DIGEST-MISMATCH"
    if session_id != context.expected_session_id:
        return False, "BLOCKED-RECEIPT-SESSION-MISMATCH"
    if state_revision != context.expected_state_revision:
        return False, "BLOCKED-RECEIPT-STATE-REVISION-MISMATCH"
    if scope != context.expected_scope:
        return False, "BLOCKED-RECEIPT-SCOPE-MISMATCH"

    receipt_time = _parse_utc(rendered_at)
    state_time = _parse_utc(context.last_relevant_state_change_at)
    if receipt_time is None or state_time is None:
        return False, "BLOCKED-RECEIPT-INVALID-TIMESTAMP"
    if receipt_time < state_time:
        return False, "BLOCKED-RECEIPT-STALE-TIMESTAMP"

    return True, "ready"
