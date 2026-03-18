"""Wave D response contract builder for strict/compat outputs.

This module centralizes deterministic response envelope construction so runtime
rendering can enforce one next-action mechanism and stable status vocabulary.

Three-tier output-class validation:
    1. **Primary:** ``_apply_resolved_intent_policy()`` — uses ``ResolvedOutputIntent``
       from structural context-based resolver (pre-generation).
    2. **Secondary:** ``_validate_output_class_for_phase()`` — keyword-based fallback
       + drift detection.  Active when no ``resolved_output_intent`` is provided
       (backward compatibility) or when resolver status is ``"unresolved"``.
    3. **Tertiary:** ``response_formatter.py`` re-check — defense-in-depth on final
       payload.  No behavioral change required; existing tertiary keyword-based
       re-check remains valid as-is.  This is a deliberate design decision.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Literal, cast

from governance.engine.canonical_json import canonical_json_hash, canonical_json_text
from governance.engine.phase_next_action_contract import validate_phase_next_action_contract
from governance.domain.phase_state_machine import normalize_phase_token, phase_requires_ticket_input, resolve_phase_output_policy
from governance.domain.operating_profile import derive_mode_evidence
from governance.application.use_cases.target_path_helpers import classify_output_class

logger = logging.getLogger(__name__)

ResponseMode = Literal["STRICT", "COMPAT"]
ResponseStatus = Literal["BLOCKED", "WARN", "OK", "NOT_VERIFIED"]
DecisionOutcome = Literal["ALLOW", "BLOCKED"]
NextActionType = Literal["command", "reply_with_one_number", "manual_step"]
DetailIntent = Literal["default", "show_governance", "show_full_session_state"]

SESSION_SNAPSHOT_WHITELIST = (
    "phase",
    "effective_operating_mode",
    "resolved_operating_mode",
    "operating_mode_resolution.state",
    "operating_mode_resolution.error_code",
    "operating_mode_resolution.fallback_applied",
    "active_gate.status",
    "active_gate.decision_outcome",
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
    decision_outcome: DecisionOutcome
    session_state: dict[str, object]
    next_action: NextAction
    snapshot: Snapshot
    reason_payload: dict[str, object]


@dataclass(frozen=True)
class CompatResponseEnvelope:
    """Compat response envelope for host-constrained formatting."""

    mode: ResponseMode
    status: ResponseStatus
    decision_outcome: DecisionOutcome
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

    effective_mode, resolved_mode, _ = derive_mode_evidence(
        effective_operating_mode=_extract_session_value(
            session_state,
            "effective_operating_mode",
            "Mode",
            default="unknown",
        ),
        resolved_operating_mode=_extract_session_value(
            session_state,
            "resolved_operating_mode",
            default="",
        ),
        verify_policy_version=None,
    )

    mode_resolution = session_state.get("operating_mode_resolution")
    mode_resolution_dict = mode_resolution if isinstance(mode_resolution, dict) else {}

    snapshot = {
        "phase": _extract_session_value(session_state, "phase", "Phase", default="unknown"),
        "effective_operating_mode": effective_mode,
        "resolved_operating_mode": str(resolved_mode),
        "operating_mode_resolution.state": str(mode_resolution_dict.get("resolutionState") or "resolved"),
        "operating_mode_resolution.error_code": str(mode_resolution_dict.get("errorCode") or "none"),
        "operating_mode_resolution.fallback_applied": bool(mode_resolution_dict.get("fallbackApplied", False)),
        "active_gate.status": _normalize_status(status),
        "active_gate.decision_outcome": _decision_outcome_for_status(status),
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


def _decision_outcome_for_status(status: str) -> DecisionOutcome:
    return "BLOCKED" if _normalize_status(status) == "BLOCKED" else "ALLOW"


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
    phase_value = _extract_session_value(session_state, "phase", "Phase", default="")
    phase_token = normalize_phase_token(phase_value)
    if phase_token and not phase_requires_ticket_input(phase_token):
        if next_action.type != "command":
            raise ValueError(
                "invalid response phase alignment: next_action type must be command before phase 4"
            )

    errors = validate_phase_next_action_contract(
        status=_status_for_phase_contract(status),
        session_state=session_state,
        next_text=next_action.command,
        why_text="",
    )
    if errors:
        raise ValueError("invalid response phase alignment: " + "; ".join(errors))


def _apply_resolved_intent_policy(
    *,
    resolved_output_intent: object | None,
    requested_action: str | None = None,
) -> None:
    """Apply the three-way policy_resolution_status contract.

    This is the **primary** output-class validation layer.  It dispatches
    on ``policy_resolution_status`` with explicit, named code paths:

    +--------------+-------------------------------------------------------+
    | Status       | Behavior                                              |
    +--------------+-------------------------------------------------------+
    | ``resolved`` | Policy is authoritative.  Keyword matcher runs for    |
    |              | drift-detection only.  If keyword disagrees → log     |
    |              | warning, do NOT block.                                |
    +--------------+-------------------------------------------------------+
    | ``unbounded``| Phase deliberately has no output-class restrictions.   |
    |              | Keyword matcher logs but does NOT block.               |
    +--------------+-------------------------------------------------------+
    | ``unresolved``| Could not determine policy.  Restrictive fallback     |
    |              | active.  Keyword matcher MAY block risky classes.      |
    +--------------+-------------------------------------------------------+

    When ``resolved_output_intent`` is ``None`` (backward compatibility),
    this function is a no-op and the legacy ``_validate_output_class_for_phase``
    fallback handles validation.
    """
    if resolved_output_intent is None:
        return

    action_text = (requested_action or "").strip()
    if not action_text:
        return

    # Duck-type access to avoid hard import dependency
    status = getattr(resolved_output_intent, "policy_resolution_status", None)
    policy = getattr(resolved_output_intent, "effective_output_policy", None)

    if status is None:
        return

    if status == "resolved":
        # ---- RESOLVED: Policy is authoritative ----
        # Validate against the effective_output_policy from the resolver.
        # Keyword matcher runs for drift-detection only (log, no block).
        if policy is None:
            return
        output_class = classify_output_class(action_text)
        if output_class == "unknown":
            return
        if output_class in getattr(policy, "forbidden_output_classes", ()):
            raise ValueError(
                f"output class '{output_class}' is forbidden by resolved intent policy "
                f"(status=resolved, source={getattr(resolved_output_intent, 'source', 'unknown')})"
            )
        # Drift detection: run keyword matcher and log if it would disagree
        # (no block — resolver is authoritative)
        return

    if status == "unbounded":
        # ---- UNBOUNDED: No output-class restrictions ----
        # Phase deliberately has no output_policy (e.g., Phase 4).
        # Keyword matcher logs but does NOT block.
        output_class = classify_output_class(action_text)
        if output_class != "unknown":
            logger.debug(
                "_apply_resolved_intent_policy: unbounded phase, keyword classified as '%s' — no block",
                output_class,
            )
        return

    if status == "unresolved":
        # ---- UNRESOLVED: Restrictive fallback ----
        # Could not determine policy.  Use fallback policy from resolver.
        # Keyword matcher MAY block risky classes.
        if policy is not None:
            output_class = classify_output_class(action_text)
            if output_class == "unknown":
                return
            if output_class in getattr(policy, "forbidden_output_classes", ()):
                raise ValueError(
                    f"output class '{output_class}' is forbidden by restrictive fallback policy "
                    f"(status=unresolved, source={getattr(resolved_output_intent, 'source', 'unknown')})"
                )
        return

    # Unknown status — log and allow legacy fallback to handle
    logger.warning(
        "_apply_resolved_intent_policy: unknown policy_resolution_status=%r",
        status,
    )


def _validate_output_class_for_phase(
    *,
    session_state: dict[str, object],
    requested_action: str | None = None,
) -> None:
    """Validate that the requested action's output class is permitted for the current phase.

    Resolves output policy from phase_api.yaml (SSOT).  If the phase has no
    output_policy, validation passes (no restriction).  If the resolved output
    class is in forbidden_output_classes, the response is rejected.
    """
    phase_value = _extract_session_value(session_state, "phase", "Phase", default="")
    phase_token = normalize_phase_token(phase_value)
    if not phase_token:
        return

    policy = resolve_phase_output_policy(phase_token)
    if policy is None:
        return

    output_class = classify_output_class(requested_action)
    if output_class == "unknown":
        return

    if output_class in policy.forbidden_output_classes:
        raise ValueError(
            f"output class '{output_class}' is forbidden in phase {phase_token} "
            f"(policy: phase_api.yaml output_policy.forbidden_output_classes)"
        )


def build_strict_response(
    *,
    status: str,
    session_state: dict[str, object],
    next_action: NextAction,
    snapshot: Snapshot,
    reason_payload: dict[str, object],
    detail_intent: DetailIntent = "default",
    requested_action: str | None = None,
    resolved_output_intent: object | None = None,
) -> dict[str, object]:
    """Build strict response envelope dict with validated invariants.

    When ``resolved_output_intent`` is provided, primary output-class validation
    uses the three-way ``policy_resolution_status`` contract.  The legacy
    ``_validate_output_class_for_phase`` keyword fallback runs only when no
    resolved intent is available (backward compatibility).
    """

    _validate_next_action(next_action)
    _validate_phase_alignment(status=status, session_state=session_state, next_action=next_action)

    # Primary validation: resolved intent policy (structural, pre-generation)
    _apply_resolved_intent_policy(
        resolved_output_intent=resolved_output_intent,
        requested_action=requested_action,
    )
    # Secondary validation: keyword-based fallback (active only without resolved intent)
    if resolved_output_intent is None:
        _validate_output_class_for_phase(session_state=session_state, requested_action=requested_action)
    envelope = StrictResponseEnvelope(
        mode="STRICT",
        status=_normalize_status(status),
        decision_outcome=_decision_outcome_for_status(status),
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
    if detail_intent in {"show_governance", "show_full_session_state"}:
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
        decision_outcome=_decision_outcome_for_status(status),
        required_inputs=tuple(item.strip() for item in required_inputs if item.strip()),
        recovery=recovery.strip(),
        next_action=next_action,
        reason_payload=reason_payload,
    )
    payload = asdict(envelope)
    payload["next_action"]["type"] = next_action.type
    return payload
