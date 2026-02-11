from __future__ import annotations

import pytest

from governance.engine.reason_payload import (
    ReasonPayload,
    build_reason_payload,
    validate_reason_payload,
)


@pytest.mark.governance
def test_reason_payload_blocked_requires_primary_recovery_and_command():
    """Blocked payloads must include exactly the required recovery tuple fields."""

    payload = ReasonPayload(
        status="BLOCKED",
        reason_code="BLOCKED-EXAMPLE",
        surface="${WORKSPACE_MEMORY_FILE}",
        signals_used=("gate",),
        primary_action="",
        recovery_steps=(),
        next_command="",
        impact="x",
        missing_evidence=(),
        deviation={},
        expiry="none",
    )
    errors = set(validate_reason_payload(payload))
    assert "blocked_primary_action_required" in errors
    assert "blocked_recovery_steps_exactly_one_required" in errors
    assert "blocked_next_command_required" in errors


@pytest.mark.governance
def test_reason_payload_not_verified_requires_missing_evidence():
    """NOT_VERIFIED payloads must include missing evidence identifiers."""

    payload = ReasonPayload(
        status="NOT_VERIFIED",
        reason_code="NOT_VERIFIED-MISSING-EVIDENCE",
        surface="${WORKSPACE_MEMORY_FILE}",
        signals_used=("evidence",),
        primary_action="Provide evidence",
        recovery_steps=("Gather host evidence",),
        next_command="show diagnostics",
        impact="x",
        missing_evidence=(),
        deviation={},
        expiry="none",
    )
    assert "not_verified_missing_evidence_required" in set(validate_reason_payload(payload))


@pytest.mark.governance
def test_reason_payload_builder_produces_valid_warn_payload():
    """Builder should create valid WARN payloads with deterministic normalization."""

    payload = build_reason_payload(
        status="WARN",
        reason_code="WARN-PERMISSION-LIMITED",
        surface="${WORKSPACE_MEMORY_FILE}",
        next_command="none",
        recovery_steps=("review",),
        impact="degraded",
    )
    assert payload.status == "WARN"
    assert payload.reason_code == "WARN-PERMISSION-LIMITED"
    assert payload.missing_evidence == ()


@pytest.mark.governance
def test_reason_payload_builder_rejects_invalid_ok_payload():
    """OK payloads must use `none` as reason code."""

    with pytest.raises(ValueError, match="ok_reason_code_must_be_none"):
        build_reason_payload(
            status="OK",
            reason_code="WARN-SHOULD-NOT-APPEAR",
            surface="${WORKSPACE_MEMORY_FILE}",
        )
