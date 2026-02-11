"""Wave D response contract builder for strict/compat outputs.

This module centralizes deterministic response envelope construction so runtime
rendering can enforce one next-action mechanism and stable status vocabulary.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

ResponseMode = Literal["STRICT", "COMPAT"]
ResponseStatus = Literal["BLOCKED", "WARN", "OK", "NOT_VERIFIED"]
NextActionType = Literal["command", "reply_with_one_number", "manual_step"]


@dataclass(frozen=True)
class NextAction:
    """Deterministic next action descriptor with one selected mechanism."""

    type: NextActionType
    command: str


@dataclass(frozen=True)
class Snapshot:
    """Compact confidence/risk/scope snapshot."""

    confidence: str
    risk: str
    scope: str


@dataclass(frozen=True)
class StrictResponseEnvelope:
    """Strict response envelope used when host supports full structure."""

    mode: ResponseMode
    status: ResponseStatus
    session_state: dict[str, object]
    next_action: NextAction
    snapshot: Snapshot
    reason_payload: dict[str, object]


@dataclass(frozen=True)
class CompatResponseEnvelope:
    """Compat response envelope for host-constrained formatting."""

    mode: ResponseMode
    status: ResponseStatus
    required_inputs: tuple[str, ...]
    recovery: str
    next_action: NextAction
    reason_payload: dict[str, object]


def _normalize_status(status: str) -> ResponseStatus:
    """Normalize incoming status values to canonical response vocabulary."""

    normalized = status.strip().upper()
    if normalized in {"BLOCKED", "WARN", "OK", "NOT_VERIFIED"}:
        return normalized
    raise ValueError(f"unsupported response status: {status!r}")


def _validate_next_action(next_action: NextAction) -> None:
    """Validate next action contract for deterministic one-mechanism output."""

    if not next_action.command.strip():
        raise ValueError("next_action command/instruction must be non-empty")


def build_strict_response(
    *,
    status: str,
    session_state: dict[str, object],
    next_action: NextAction,
    snapshot: Snapshot,
    reason_payload: dict[str, object],
) -> dict[str, object]:
    """Build strict response envelope dict with validated invariants."""

    _validate_next_action(next_action)
    envelope = StrictResponseEnvelope(
        mode="STRICT",
        status=_normalize_status(status),
        session_state=session_state,
        next_action=next_action,
        snapshot=snapshot,
        reason_payload=reason_payload,
    )
    payload = asdict(envelope)
    payload["next_action"]["type"] = next_action.type
    return payload


def build_compat_response(
    *,
    status: str,
    required_inputs: tuple[str, ...],
    recovery: str,
    next_action: NextAction,
    reason_payload: dict[str, object],
) -> dict[str, object]:
    """Build compat response envelope dict with validated invariants."""

    _validate_next_action(next_action)
    if not recovery.strip():
        raise ValueError("compat recovery must be non-empty")
    if _normalize_status(status) == "BLOCKED" and len(required_inputs) == 0:
        raise ValueError("blocked compat responses must include required_inputs")
    envelope = CompatResponseEnvelope(
        mode="COMPAT",
        status=_normalize_status(status),
        required_inputs=tuple(item.strip() for item in required_inputs if item.strip()),
        recovery=recovery.strip(),
        next_action=next_action,
        reason_payload=reason_payload,
    )
    payload = asdict(envelope)
    payload["next_action"]["type"] = next_action.type
    return payload
