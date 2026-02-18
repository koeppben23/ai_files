"""Reason payload schema and validators for deterministic output contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

from governance.engine._embedded_reason_registry import EMBEDDED_REASON_CODE_TO_SCHEMA_REF
from governance.engine._embedded_reason_schemas import EMBEDDED_REASON_SCHEMAS
from governance.engine.reason_codes import REASON_CODE_NONE, is_registered_reason_code
from governance.engine.sanitization import sanitize_for_output

ReasonStatus = Literal["BLOCKED", "WARN", "OK", "NOT_VERIFIED"]
DecisionOutcome = Literal["ALLOW", "BLOCKED"]


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
    decision_outcome: DecisionOutcome = "ALLOW"
    context: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Return deterministic dict representation for serialization/tests."""

        payload = asdict(self)
        context = payload.get("context", {})
        if isinstance(context, dict):
            payload["context"] = dict(sorted(context.items()))
        return sanitize_for_output(payload)


def validate_reason_payload(payload: ReasonPayload) -> tuple[str, ...]:
    """Validate reason payload contract invariants and return error keys."""

    errors: list[str] = []
    expected_outcome: DecisionOutcome = "BLOCKED" if payload.status == "BLOCKED" else "ALLOW"
    if payload.decision_outcome != expected_outcome:
        errors.append("decision_outcome_mismatch")
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


_SCHEMA_CACHE: dict[str, dict[str, object]] = {}


def _resolve_schema_ref_for_reason(reason_code: str) -> str | None:
    normalized = reason_code.strip()
    if not normalized:
        return None
    embedded_ref = EMBEDDED_REASON_CODE_TO_SCHEMA_REF.get(normalized)
    if embedded_ref:
        return embedded_ref
    return None


def _load_schema(schema_ref: str) -> dict[str, object]:
    embedded_schema = EMBEDDED_REASON_SCHEMAS.get(schema_ref)
    if embedded_schema is not None:
        return embedded_schema

    cached = _SCHEMA_CACHE.get(schema_ref)
    if cached is not None:
        return cached

    # No __file__-based fallback: schemas must be embedded.
    raise ValueError(f"reason_schema_missing:{schema_ref}")


def _validate_against_schema(*, schema: dict[str, object], value: object, path: str = "$") -> list[str]:
    errors: list[str] = []

    expected_type = schema.get("type")
    if expected_type == "object":
        if not isinstance(value, dict):
            return [f"{path}:expected object"]

        properties = schema.get("properties")
        if not isinstance(properties, dict):
            properties = {}

        required = schema.get("required")
        if isinstance(required, list):
            for key in required:
                if isinstance(key, str) and key not in value:
                    errors.append(f"{path}.{key}:required")

        if schema.get("additionalProperties") is False:
            allowed = {k for k in properties.keys() if isinstance(k, str)}
            for key in value.keys():
                if isinstance(key, str) and key not in allowed:
                    errors.append(f"{path}.{key}:unexpected")

        for key, child in properties.items():
            if not isinstance(key, str) or key not in value or not isinstance(child, dict):
                continue
            errors.extend(_validate_against_schema(schema=child, value=value[key], path=f"{path}.{key}"))

    elif expected_type == "array":
        if not isinstance(value, list):
            return [f"{path}:expected array"]
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for idx, item in enumerate(value):
                errors.extend(_validate_against_schema(schema=item_schema, value=item, path=f"{path}[{idx}]"))

    elif expected_type == "string":
        if not isinstance(value, str):
            return [f"{path}:expected string"]
        min_len = schema.get("minLength")
        if isinstance(min_len, int) and len(value) < min_len:
            errors.append(f"{path}:minLength")
        enum = schema.get("enum")
        if isinstance(enum, list) and value not in enum:
            errors.append(f"{path}:enum")

    elif expected_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            return [f"{path}:expected integer"]
        minimum = schema.get("minimum")
        if isinstance(minimum, int) and value < minimum:
            errors.append(f"{path}:minimum")

    return errors


def validate_reason_context_schema(reason_code: str, context: dict[str, object]) -> tuple[str, ...]:
    """Validate reason context against registered payload schema when available."""

    schema_ref = _resolve_schema_ref_for_reason(reason_code)
    if not schema_ref:
        return ()

    schema = _load_schema(schema_ref)
    errors = _validate_against_schema(schema=schema, value=context, path="$")
    if not errors:
        return ()
    return tuple(f"schema:{schema_ref}:{entry}" for entry in sorted(set(errors)))


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

    normalized_reason_code = reason_code.strip()
    normalized_context = dict(sorted(sanitize_for_output(context or {}).items()))
    if (
        status == "BLOCKED"
        and normalized_reason_code.startswith("BLOCKED-")
        and "failure_class" not in normalized_context
    ):
        normalized_context["failure_class"] = "blocked_decision"

    payload = ReasonPayload(
        status=status,
        decision_outcome="BLOCKED" if status == "BLOCKED" else "ALLOW",
        reason_code=normalized_reason_code,
        surface=surface.strip(),
        signals_used=tuple(sorted(set(s.strip() for s in signals_used if s.strip()))),
        primary_action=primary_action.strip(),
        recovery_steps=tuple(step.strip() for step in recovery_steps if step.strip()),
        next_command=next_command.strip(),
        impact=impact.strip(),
        missing_evidence=tuple(sorted(set(missing_evidence))),
        deviation=dict(sorted(sanitize_for_output(deviation or {}).items())),
        expiry=expiry.strip() or "none",
        context=normalized_context,
    )
    errors = list(validate_reason_payload(payload))
    if payload.status == "BLOCKED" and not is_registered_reason_code(payload.reason_code, allow_none=False):
        errors.append("blocked_reason_code_unregistered")
    errors.extend(validate_reason_context_schema(payload.reason_code, payload.context))
    if errors:
        raise ValueError("invalid reason payload: " + ",".join(errors))
    return payload
