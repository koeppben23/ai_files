"""Reason payload schema and validators for deterministic output contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

from governance.engine.reason_codes import REASON_CODE_NONE

ReasonStatus = Literal["BLOCKED", "WARN", "OK", "NOT_VERIFIED"]


@dataclass(frozen=True)
class ReasonPayload:
    """Structured reason payload emitted by orchestrator/runtime outputs."""

    status: ReasonStatus
    reason_code: str
    surface: str
    signals_used: tuple[str, ...]
    primary_action: str
    recovery_steps: tuple[str, ...]
    next_command: str
    impact: str
    missing_evidence: tuple[str, ...]
    deviation: dict[str, str]
    expiry: str
    context: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Return deterministic dict representation for serialization/tests."""

        payload = asdict(self)
        context = payload.get("context", {})
        if isinstance(context, dict):
            payload["context"] = dict(sorted(context.items()))
        return payload


def validate_reason_payload(payload: ReasonPayload) -> tuple[str, ...]:
    """Validate reason payload contract invariants and return error keys."""

    errors: list[str] = []
    if payload.status == "BLOCKED":
        if not payload.primary_action.strip():
            errors.append("blocked_primary_action_required")
        if len(payload.recovery_steps) != 1 or not payload.recovery_steps[0].strip():
            errors.append("blocked_recovery_steps_exactly_one_required")
        if not payload.next_command.strip():
            errors.append("blocked_next_command_required")
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
    if not payload.surface.strip():
        errors.append("surface_required")
    if payload.status in {"BLOCKED", "NOT_VERIFIED"} and len(payload.signals_used) == 0:
        errors.append("signals_used_required")
    return tuple(errors)


def build_reason_payload(
    *,
    status: ReasonStatus,
    reason_code: str,
    surface: str,
    signals_used: tuple[str, ...] = (),
    primary_action: str = "",
    recovery_steps: tuple[str, ...] = (),
    next_command: str = "",
    impact: str = "",
    missing_evidence: tuple[str, ...] = (),
    deviation: dict[str, str] | None = None,
    expiry: str = "none",
    context: dict[str, object] | None = None,
) -> ReasonPayload:
    """Create a validated reason payload, raising on contract errors."""

    payload = ReasonPayload(
        status=status,
        reason_code=reason_code.strip(),
        surface=surface.strip(),
        signals_used=tuple(sorted(set(s.strip() for s in signals_used if s.strip()))),
        primary_action=primary_action.strip(),
        recovery_steps=tuple(step.strip() for step in recovery_steps if step.strip()),
        next_command=next_command.strip(),
        impact=impact.strip(),
        missing_evidence=tuple(sorted(set(missing_evidence))),
        deviation=dict(sorted((deviation or {}).items())),
        expiry=expiry.strip() or "none",
        context=dict(sorted((context or {}).items())),
    )
    errors = validate_reason_payload(payload)
    if errors:
        raise ValueError("invalid reason payload: " + ",".join(errors))
    return payload
