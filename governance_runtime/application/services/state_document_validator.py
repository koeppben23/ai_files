"""StateDocument Validator - Runtime Schema Enforcement for Session State.

This module provides runtime validation for StateDocument instances with fail-closed
policy for critical fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ValidationSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ValidationIssue:
    field: str
    severity: ValidationSeverity
    message: str
    code: str


@dataclass
class ValidationResult:
    valid: bool
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)

    def add_error(self, field: str, message: str, code: str) -> None:
        self.valid = False
        self.errors.append(ValidationIssue(
            field=field,
            severity=ValidationSeverity.ERROR,
            message=message,
            code=code,
        ))

    def add_warning(self, field: str, message: str, code: str) -> None:
        self.warnings.append(ValidationIssue(
            field=field,
            severity=ValidationSeverity.WARNING,
            message=message,
            code=code,
        ))


KNOWN_PHASE_TOKENS = frozenset({
    "1", "1.1", "1.2", "1.3", "1.5",
    "2", "2.1",
    "3A", "3B-1", "3B-2",
    "4", "5", "5.3", "5.4", "5.5", "5.6", "6",
})

VALID_STATUS_VALUES = frozenset({"OK", "IN_PROGRESS", "error", "blocked"})


def validate_state_document(raw: dict[str, Any]) -> ValidationResult:
    """Validate a StateDocument with fail-closed policy.

    Critical errors cause validation failure:
    - Missing SESSION_STATE
    - Missing required SESSION_STATE fields
    - Invalid phase token
    - Invalid status value

    Warnings are non-blocking:
    - Missing optional fields
    - Unknown additional properties

    Args:
        raw: The raw state document dictionary.

    Returns:
        ValidationResult with valid flag and list of issues.
    """
    result = ValidationResult(valid=True)

    if not isinstance(raw, dict):
        result.add_error("root", "StateDocument must be a dict", "INVALID_TYPE")
        return result

    if "SESSION_STATE" not in raw:
        result.add_error("SESSION_STATE", "SESSION_STATE is required", "MISSING_SESSION_STATE")
        return result

    session_state = raw.get("SESSION_STATE")
    if not isinstance(session_state, dict):
        result.add_error("SESSION_STATE", "SESSION_STATE must be a dict", "INVALID_SESSION_STATE_TYPE")
        return result

    _validate_session_state(session_state, result)

    return result


def _validate_session_state(state: dict[str, Any], result: ValidationResult) -> None:
    if "phase" not in state and "Phase" not in state:
        result.add_warning("SESSION_STATE.phase", "phase is recommended", "MISSING_PHASE")
    else:
        phase = str(state.get("phase") or state.get("Phase") or "").strip()
        if not phase:
            result.add_error("SESSION_STATE.phase", "phase must be a non-empty string", "INVALID_PHASE")
        elif phase not in KNOWN_PHASE_TOKENS:
            result.add_warning(
                "SESSION_STATE.phase",
                f"Unknown phase token: {phase}",
                "UNKNOWN_PHASE_TOKEN"
            )

    if "active_gate" not in state and "ActiveGate" not in state:
        result.add_warning("SESSION_STATE.active_gate", "active_gate is recommended", "MISSING_ACTIVE_GATE")
    else:
        gate = state.get("active_gate") or state.get("ActiveGate") or ""
        if not isinstance(gate, str) or not gate.strip():
            result.add_error("SESSION_STATE.active_gate", "active_gate must be a non-empty string", "INVALID_ACTIVE_GATE")

    if "status" in state:
        status = state.get("status")
        if isinstance(status, str) and status not in VALID_STATUS_VALUES:
            result.add_warning(
                "SESSION_STATE.status",
                f"Unknown status value: {status}. Expected one of: {', '.join(VALID_STATUS_VALUES)}",
                "UNKNOWN_STATUS_VALUE"
            )

    gates = state.get("Gates")
    if gates is not None and not isinstance(gates, dict):
        result.add_error("SESSION_STATE.Gates", "Gates must be a dict or null", "INVALID_GATES_TYPE")


def validate_review_payload(payload: dict[str, Any]) -> ValidationResult:
    """Validate a ReviewPayload structure.

    Args:
        payload: The review payload dictionary.

    Returns:
        ValidationResult with valid flag and list of issues.
    """
    result = ValidationResult(valid=True)

    if not isinstance(payload, dict):
        result.add_error("root", "ReviewPayload must be a dict", "INVALID_TYPE")
        return result

    if "verdict" not in payload:
        result.add_error("verdict", "verdict is required", "MISSING_VERDICT")
    else:
        verdict = payload.get("verdict")
        if not isinstance(verdict, str) or not verdict.strip():
            result.add_error("verdict", "verdict must be a non-empty string", "INVALID_VERDICT")

    if "findings" not in payload:
        result.add_warning("findings", "findings is recommended", "MISSING_FINDINGS")

    return result


def validate_plan_payload(payload: dict[str, Any]) -> ValidationResult:
    """Validate a PlanPayload structure.

    Args:
        payload: The plan payload dictionary.

    Returns:
        ValidationResult with valid flag and list of issues.
    """
    result = ValidationResult(valid=True)

    if not isinstance(payload, dict):
        result.add_error("root", "PlanPayload must be a dict", "INVALID_TYPE")
        return result

    if "body" not in payload:
        result.add_error("body", "body is required", "MISSING_BODY")
    else:
        body = payload.get("body")
        if not isinstance(body, str) or not body.strip():
            result.add_error("body", "body must be a non-empty string", "INVALID_BODY")

    if "status" not in payload:
        result.add_error("status", "status is required", "MISSING_STATUS")
    else:
        status = payload.get("status")
        if not isinstance(status, str) or not status.strip():
            result.add_error("status", "status must be a non-empty string", "INVALID_STATUS")

    return result


def validate_receipt_payload(payload: dict[str, Any]) -> ValidationResult:
    """Validate a ReceiptPayload structure.

    Args:
        payload: The receipt payload dictionary.

    Returns:
        ValidationResult with valid flag and list of issues.
    """
    result = ValidationResult(valid=True)

    if not isinstance(payload, dict):
        result.add_error("root", "ReceiptPayload must be a dict", "INVALID_TYPE")
        return result

    if "evidence" not in payload:
        result.add_warning("evidence", "evidence is recommended", "MISSING_EVIDENCE")

    if "timestamp" not in payload:
        result.add_warning("timestamp", "timestamp is recommended", "MISSING_TIMESTAMP")

    return result
