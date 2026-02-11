"""Reason payload schema and validators for deterministic output contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from governance.engine.reason_codes import REASON_CODE_NONE

ReasonStatus = Literal["BLOCKED", "WARN", "OK", "NOT_VERIFIED"]


@dataclass(frozen=True)
class ReasonPayload:
    """Structured reason payload emitted by orchestrator/runtime outputs."""

    status: ReasonStatus
    reason_code: str
    primary_action: str
    recovery: str
    command: str
    impact: str
    missing_evidence: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return deterministic dict representation for serialization/tests."""

        return asdict(self)


def validate_reason_payload(payload: ReasonPayload) -> tuple[str, ...]:
    """Validate reason payload contract invariants and return error keys."""

    errors: list[str] = []
    if payload.status == "BLOCKED":
        if not payload.primary_action.strip():
            errors.append("blocked_primary_action_required")
        if not payload.recovery.strip():
            errors.append("blocked_recovery_required")
        if not payload.command.strip():
            errors.append("blocked_command_required")
    elif payload.status == "WARN":
        if not payload.impact.strip():
            errors.append("warn_impact_required")
    elif payload.status == "NOT_VERIFIED":
        if len(payload.missing_evidence) == 0:
            errors.append("not_verified_missing_evidence_required")
        if not payload.primary_action.strip():
            errors.append("not_verified_primary_action_required")
    elif payload.status == "OK":
        if payload.reason_code != REASON_CODE_NONE:
            errors.append("ok_reason_code_must_be_none")
    return tuple(errors)


def build_reason_payload(
    *,
    status: ReasonStatus,
    reason_code: str,
    primary_action: str = "",
    recovery: str = "",
    command: str = "",
    impact: str = "",
    missing_evidence: tuple[str, ...] = (),
) -> ReasonPayload:
    """Create a validated reason payload, raising on contract errors."""

    payload = ReasonPayload(
        status=status,
        reason_code=reason_code.strip(),
        primary_action=primary_action.strip(),
        recovery=recovery.strip(),
        command=command.strip(),
        impact=impact.strip(),
        missing_evidence=tuple(sorted(set(missing_evidence))),
    )
    errors = validate_reason_payload(payload)
    if errors:
        raise ValueError("invalid reason payload: " + ",".join(errors))
    return payload
