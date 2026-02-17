"""Wave D response contract builder for strict/compat outputs.

This module centralizes deterministic response envelope construction so runtime
rendering can enforce one next-action mechanism and stable status vocabulary.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal, cast

from governance.engine.canonical_json import canonical_json_hash, canonical_json_text
from governance.engine.phase_next_action_contract import validate_phase_next_action_contract

ResponseMode = Literal["STRICT", "COMPAT"]
ResponseStatus = Literal["BLOCKED", "WARN", "OK", "NOT_VERIFIED"]
NextActionType = Literal["command", "reply_with_one_number", "manual_step"]
DetailIntent = Literal["default", "show_diagnostics", "show_full_session_state"]

SESSION_SNAPSHOT_WHITELIST = (
    "phase",
    "effective_operating_mode",
    "active_gate.status",
    "active_gate.reason_code",
    "next_action",
    "missing_evidence_count",
    "activation_hash",
    "ruleset_hash",
    "repo_fingerprint",
    "state_unchanged",
    "delta_mode",
    "snapshot_hash",
)

SESSION_SNAPSHOT_MAX_CHARS = 900


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


def _hash_payload(payload: dict[str, object]) -> str:
    """Return deterministic sha256 over canonical JSON payload."""

    return canonical_json_hash(payload)


def _extract_session_value(session_state: dict[str, object], *keys: str, default: str = "") -> str:
    """Read first non-empty scalar value from candidate keys."""

    for key in keys:
        value = session_state.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, (int, float)):
            return str(value)
    return default


def build_session_snapshot(
    *,
    status: str,
    session_state: dict[str, object],
    next_action: NextAction,
    reason_payload: dict[str, object],
) -> dict[str, object]:
    """Build compact default session projection from full state and reason payload."""

    reason_code = str(reason_payload.get("reason_code", "")).strip()
    if not reason_code:
        reason_code = "none"
    if reason_code.lower() == "none" and _normalize_status(status) == "OK":
        reason_code = "none"

    missing_evidence_value = reason_payload.get("missing_evidence")
    missing_evidence_count = (
        len(missing_evidence_value)
        if isinstance(missing_evidence_value, (list, tuple))
        else 0
    )

    snapshot = {
        "phase": _extract_session_value(session_state, "phase", "Phase", default="unknown"),
        "effective_operating_mode": _extract_session_value(
            session_state,
            "effective_operating_mode",
            "Mode",
            default="unknown",
        ).lower(),
        "active_gate.status": _normalize_status(status),
        "active_gate.reason_code": reason_code,
        "next_action": next_action.command.strip(),
        "missing_evidence_count": missing_evidence_count,
        "activation_hash": _extract_session_value(session_state, "activation_hash"),
        "ruleset_hash": _extract_session_value(session_state, "ruleset_hash"),
        "repo_fingerprint": _extract_session_value(session_state, "repo_fingerprint", default="unknown"),
        "state_unchanged": bool(session_state.get("state_unchanged", False)),
        "delta_mode": _extract_session_value(session_state, "delta_mode", default="delta-only"),
    }
    if not snapshot["activation_hash"]:
        raise ValueError("session snapshot requires activation_hash")
    snapshot["snapshot_hash"] = _hash_payload(snapshot)
    if len(canonical_json_text(snapshot)) > SESSION_SNAPSHOT_MAX_CHARS:
        raise ValueError("session snapshot exceeds compact output budget")
    return snapshot


def _normalize_status(status: str) -> ResponseStatus:
    """Normalize incoming status values to canonical response vocabulary."""

    normalized = status.strip().upper()
    if normalized in {"BLOCKED", "WARN", "OK", "NOT_VERIFIED"}:
        return cast(ResponseStatus, normalized)
    raise ValueError(f"unsupported response status: {status!r}")


def _validate_next_action(next_action: NextAction) -> None:
    """Validate next action contract for deterministic one-mechanism output."""

    if not next_action.command.strip():
        raise ValueError("next_action command/instruction must be non-empty")


def _status_for_phase_contract(status: str) -> str:
    normalized = status.strip().upper()
    if normalized == "OK":
        return "normal"
    if normalized in {"WARN", "NOT_VERIFIED"}:
        return "degraded"
    if normalized == "BLOCKED":
        return "blocked"
    return normalized.lower()


def _validate_phase_alignment(*, status: str, session_state: dict[str, object], next_action: NextAction) -> None:
    errors = validate_phase_next_action_contract(
        status=_status_for_phase_contract(status),
        session_state=session_state,
        next_text=next_action.command,
        why_text="",
    )
    if errors:
        raise ValueError("invalid response phase alignment: " + "; ".join(errors))


def build_strict_response(
    *,
    status: str,
    session_state: dict[str, object],
    next_action: NextAction,
    snapshot: Snapshot,
    reason_payload: dict[str, object],
    detail_intent: DetailIntent = "default",
) -> dict[str, object]:
    """Build strict response envelope dict with validated invariants."""

    _validate_next_action(next_action)
    _validate_phase_alignment(status=status, session_state=session_state, next_action=next_action)
    envelope = StrictResponseEnvelope(
        mode="STRICT",
        status=_normalize_status(status),
        session_state=build_session_snapshot(
            status=status,
            session_state=session_state,
            next_action=next_action,
            reason_payload=reason_payload,
        ),
        next_action=next_action,
        snapshot=snapshot,
        reason_payload=reason_payload,
    )
    payload = asdict(envelope)
    payload["next_action"]["type"] = next_action.type
    if detail_intent in {"show_diagnostics", "show_full_session_state"}:
        payload["session_state_full"] = session_state
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
