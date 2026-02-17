"""Reason payload schema and validators for deterministic output contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
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


_REPO_ROOT = Path(__file__).resolve().parents[2]
_REASON_REGISTRY_PATH = _REPO_ROOT / "diagnostics" / "reason_codes.registry.json"
_SCHEMA_CACHE: dict[str, dict[str, object]] = {}
_REASON_SCHEMA_REF_CACHE: dict[str, str] | None = None


def _load_reason_schema_refs() -> dict[str, str]:
    global _REASON_SCHEMA_REF_CACHE
    if _REASON_SCHEMA_REF_CACHE is not None:
        return _REASON_SCHEMA_REF_CACHE

    if not _REASON_REGISTRY_PATH.exists():
        raise ValueError(
            "reason schema registry missing: "
            f"{_REASON_REGISTRY_PATH} (expected diagnostics/reason_codes.registry.json)"
        )

    payload = json.loads(_REASON_REGISTRY_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(
            "reason schema registry invalid: expected JSON object at "
            f"{_REASON_REGISTRY_PATH}"
        )

    schema_tag = payload.get("schema")
    if schema_tag != "governance.reason-codes.registry.v1":
        raise ValueError(
            "reason schema registry schema mismatch: "
            f"expected governance.reason-codes.registry.v1, got {schema_tag!r}"
        )

    entries = payload.get("codes")
    if not isinstance(entries, list):
        raise ValueError(
            "reason schema registry invalid: 'codes' must be an array in "
            f"{_REASON_REGISTRY_PATH}"
        )

    refs: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        code = entry.get("code")
        ref = entry.get("payload_schema_ref")
        if isinstance(code, str) and code.strip() and isinstance(ref, str) and ref.strip():
            refs[code.strip()] = ref.strip()

    if not refs:
        raise ValueError(
            "reason schema registry contains no usable code->schema mappings in "
            f"{_REASON_REGISTRY_PATH}"
        )

    _REASON_SCHEMA_REF_CACHE = refs
    return refs


def _load_schema(schema_ref: str) -> dict[str, object]:
    cached = _SCHEMA_CACHE.get(schema_ref)
    if cached is not None:
        return cached
    schema_path = _REPO_ROOT / schema_ref
    if not schema_path.exists():
        raise ValueError(
            "reason payload schema missing: "
            f"{schema_path} (from registry ref {schema_ref!r})"
        )
    payload = json.loads(schema_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid schema payload: {schema_ref}")
    _SCHEMA_CACHE[schema_ref] = payload
    return payload


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

    schema_refs = _load_reason_schema_refs()
    schema_ref = schema_refs.get(reason_code.strip())
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
    errors = list(validate_reason_payload(payload))
    errors.extend(validate_reason_context_schema(payload.reason_code, payload.context))
    if errors:
        raise ValueError("invalid reason payload: " + ",".join(errors))
    return payload
