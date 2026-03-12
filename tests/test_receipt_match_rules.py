from __future__ import annotations

from governance.receipts.match import ReceiptMatchContext, validate_receipt_match


def _context() -> ReceiptMatchContext:
    return ReceiptMatchContext(
        expected_receipt_type="governance_review_presentation_receipt",
        expected_gate="Evidence Presentation Gate",
        expected_digest="abc123",
        expected_session_id="sess-1",
        expected_state_revision="mat-1",
        expected_scope="R-REVIEW-DECISION-001",
        last_relevant_state_change_at="2026-03-12T10:00:00Z",
    )


def test_receipt_match_happy_path() -> None:
    ok, reason = validate_receipt_match(
        receipt={
            "receipt_type": "governance_review_presentation_receipt",
            "requirement_scope": "R-REVIEW-DECISION-001",
            "content_digest": "abc123",
            "rendered_at": "2026-03-12T10:00:01Z",
            "render_event_id": "mat-1",
            "gate": "Evidence Presentation Gate",
            "session_id": "sess-1",
            "state_revision": "mat-1",
            "source_command": "/continue",
        },
        context=_context(),
    )
    assert ok is True
    assert reason == "ready"


def test_receipt_match_bad_digest_mismatch() -> None:
    ok, reason = validate_receipt_match(
        receipt={
            "receipt_type": "governance_review_presentation_receipt",
            "requirement_scope": "R-REVIEW-DECISION-001",
            "content_digest": "different",
            "rendered_at": "2026-03-12T10:00:01Z",
            "render_event_id": "mat-1",
            "gate": "Evidence Presentation Gate",
            "session_id": "sess-1",
            "state_revision": "mat-1",
            "source_command": "/continue",
        },
        context=_context(),
    )
    assert ok is False
    assert reason == "BLOCKED-RECEIPT-DIGEST-MISMATCH"


def test_receipt_match_corner_stale_timestamp_blocks() -> None:
    ok, reason = validate_receipt_match(
        receipt={
            "receipt_type": "governance_review_presentation_receipt",
            "requirement_scope": "R-REVIEW-DECISION-001",
            "content_digest": "abc123",
            "rendered_at": "2026-03-12T09:59:59Z",
            "render_event_id": "mat-1",
            "gate": "Evidence Presentation Gate",
            "session_id": "sess-1",
            "state_revision": "mat-1",
            "source_command": "/continue",
        },
        context=_context(),
    )
    assert ok is False
    assert reason == "BLOCKED-RECEIPT-STALE-TIMESTAMP"


def test_receipt_match_edge_legacy_alias_digest_and_presented_at() -> None:
    ok, reason = validate_receipt_match(
        receipt={
            "receipt_type": "governance_review_presentation_receipt",
            "requirement_scope": "R-REVIEW-DECISION-001",
            "digest": "abc123",
            "presented_at": "2026-03-12T10:00:02Z",
            "render_event_id": "mat-1",
            "gate": "Evidence Presentation Gate",
            "session_id": "sess-1",
            "state_revision": "mat-1",
            "source_command": "/continue",
        },
        context=_context(),
    )
    assert ok is True
    assert reason == "ready"
