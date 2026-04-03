from __future__ import annotations

from governance_runtime.receipts.match import ReceiptMatchContext, validate_receipt_match


def _context() -> ReceiptMatchContext:
    return ReceiptMatchContext(
        expected_receipt_type="governance_review_presentation_receipt",
        expected_gate="Evidence Presentation Gate",
        expected_digest="abc123",
        expected_session_id="sess-1",
        expected_state_revision="10",
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
            "state_revision": "10",
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
            "state_revision": "10",
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
            "state_revision": "10",
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
            "state_revision": "10",
            "source_command": "/continue",
        },
        context=_context(),
    )
    assert ok is True
    assert reason == "ready"


def test_receipt_state_revision_newer_is_accepted() -> None:
    ok, reason = validate_receipt_match(
        receipt={
            "receipt_type": "governance_review_presentation_receipt",
            "requirement_scope": "R-REVIEW-DECISION-001",
            "content_digest": "abc123",
            "rendered_at": "2026-03-12T10:00:03Z",
            "render_event_id": "mat-11",
            "gate": "Evidence Presentation Gate",
            "session_id": "sess-1",
            "state_revision": "11",
            "source_command": "/continue",
        },
        context=_context(),
    )
    assert ok is True
    assert reason == "ready"


def test_receipt_state_revision_older_is_blocked() -> None:
    ok, reason = validate_receipt_match(
        receipt={
            "receipt_type": "governance_review_presentation_receipt",
            "requirement_scope": "R-REVIEW-DECISION-001",
            "content_digest": "abc123",
            "rendered_at": "2026-03-12T10:00:03Z",
            "render_event_id": "mat-9",
            "gate": "Evidence Presentation Gate",
            "session_id": "sess-1",
            "state_revision": "9",
            "source_command": "/continue",
        },
        context=_context(),
    )
    assert ok is False
    assert reason == "BLOCKED-RECEIPT-STATE-REVISION-MISMATCH"


# ---------------------------------------------------------------------------
# Missing-field BLOCKED codes (each field omitted or empty)
# ---------------------------------------------------------------------------

def _valid_receipt() -> dict[str, str]:
    """Return a receipt that passes all checks against ``_context()``."""
    return {
        "receipt_type": "governance_review_presentation_receipt",
        "gate": "Evidence Presentation Gate",
        "content_digest": "abc123",
        "session_id": "sess-1",
        "state_revision": "10",
        "requirement_scope": "R-REVIEW-DECISION-001",
        "rendered_at": "2026-03-12T10:00:01Z",
    }


def test_receipt_missing_type_blocks() -> None:
    r = _valid_receipt()
    r.pop("receipt_type")
    ok, reason = validate_receipt_match(receipt=r, context=_context())
    assert ok is False
    assert reason == "BLOCKED-RECEIPT-MISSING-TYPE"


def test_receipt_empty_type_blocks() -> None:
    r = _valid_receipt()
    r["receipt_type"] = "  "
    ok, reason = validate_receipt_match(receipt=r, context=_context())
    assert ok is False
    assert reason == "BLOCKED-RECEIPT-MISSING-TYPE"


def test_receipt_missing_gate_blocks() -> None:
    r = _valid_receipt()
    r.pop("gate")
    ok, reason = validate_receipt_match(receipt=r, context=_context())
    assert ok is False
    assert reason == "BLOCKED-RECEIPT-MISSING-GATE"


def test_receipt_missing_digest_blocks() -> None:
    r = _valid_receipt()
    r.pop("content_digest")
    ok, reason = validate_receipt_match(receipt=r, context=_context())
    assert ok is False
    assert reason == "BLOCKED-RECEIPT-MISSING-DIGEST"


def test_receipt_missing_session_blocks() -> None:
    r = _valid_receipt()
    r.pop("session_id")
    ok, reason = validate_receipt_match(receipt=r, context=_context())
    assert ok is False
    assert reason == "BLOCKED-RECEIPT-MISSING-SESSION"


def test_receipt_missing_state_revision_blocks() -> None:
    r = _valid_receipt()
    r.pop("state_revision")
    # Also remove render_event_id fallback
    r.pop("render_event_id", None)
    ok, reason = validate_receipt_match(receipt=r, context=_context())
    assert ok is False
    assert reason == "BLOCKED-RECEIPT-MISSING-STATE-REVISION"


def test_receipt_missing_scope_blocks() -> None:
    r = _valid_receipt()
    r.pop("requirement_scope")
    ok, reason = validate_receipt_match(receipt=r, context=_context())
    assert ok is False
    assert reason == "BLOCKED-RECEIPT-MISSING-SCOPE"


def test_receipt_missing_timestamp_blocks() -> None:
    r = _valid_receipt()
    r.pop("rendered_at")
    # Also remove presented_at fallback
    r.pop("presented_at", None)
    ok, reason = validate_receipt_match(receipt=r, context=_context())
    assert ok is False
    assert reason == "BLOCKED-RECEIPT-MISSING-TIMESTAMP"


# ---------------------------------------------------------------------------
# Mismatch BLOCKED codes (field present but wrong value)
# ---------------------------------------------------------------------------

def test_receipt_type_mismatch_blocks() -> None:
    r = _valid_receipt()
    r["receipt_type"] = "wrong_receipt_type"
    ok, reason = validate_receipt_match(receipt=r, context=_context())
    assert ok is False
    assert reason == "BLOCKED-RECEIPT-TYPE-MISMATCH"


def test_receipt_gate_mismatch_blocks() -> None:
    r = _valid_receipt()
    r["gate"] = "Wrong Gate"
    ok, reason = validate_receipt_match(receipt=r, context=_context())
    assert ok is False
    assert reason == "BLOCKED-RECEIPT-GATE-MISMATCH"


def test_receipt_session_mismatch_blocks() -> None:
    r = _valid_receipt()
    r["session_id"] = "different-session"
    ok, reason = validate_receipt_match(receipt=r, context=_context())
    assert ok is False
    assert reason == "BLOCKED-RECEIPT-SESSION-MISMATCH"


def test_receipt_scope_mismatch_blocks() -> None:
    r = _valid_receipt()
    r["requirement_scope"] = "R-DIFFERENT-SCOPE-001"
    ok, reason = validate_receipt_match(receipt=r, context=_context())
    assert ok is False
    assert reason == "BLOCKED-RECEIPT-SCOPE-MISMATCH"


def test_receipt_invalid_timestamp_blocks() -> None:
    """Both rendered_at and context timestamp must parse; unparseable blocks."""
    r = _valid_receipt()
    r["rendered_at"] = "not-a-date"
    ok, reason = validate_receipt_match(receipt=r, context=_context())
    assert ok is False
    assert reason == "BLOCKED-RECEIPT-INVALID-TIMESTAMP"


def test_receipt_invalid_context_timestamp_blocks() -> None:
    """If the context's state-change timestamp is unparseable, block."""
    ctx = ReceiptMatchContext(
        expected_receipt_type="governance_review_presentation_receipt",
        expected_gate="Evidence Presentation Gate",
        expected_digest="abc123",
        expected_session_id="sess-1",
        expected_state_revision="10",
        expected_scope="R-REVIEW-DECISION-001",
        last_relevant_state_change_at="not-a-date",
    )
    r = _valid_receipt()
    ok, reason = validate_receipt_match(receipt=r, context=ctx)
    assert ok is False
    assert reason == "BLOCKED-RECEIPT-INVALID-TIMESTAMP"


# ---------------------------------------------------------------------------
# Gate case-insensitive matching (existing code uses .lower())
# ---------------------------------------------------------------------------

def test_receipt_gate_case_insensitive_match() -> None:
    r = _valid_receipt()
    r["gate"] = "evidence presentation gate"  # all lowercase
    ok, reason = validate_receipt_match(receipt=r, context=_context())
    assert ok is True
    assert reason == "ready"


# ---------------------------------------------------------------------------
# Edge: completely empty receipt
# ---------------------------------------------------------------------------

def test_receipt_empty_dict_blocks_at_first_check() -> None:
    ok, reason = validate_receipt_match(receipt={}, context=_context())
    assert ok is False
    assert reason == "BLOCKED-RECEIPT-MISSING-TYPE"
