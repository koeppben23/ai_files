"""
llm_response_validator.py — Hard contract validator for LLM review and developer responses.

This module validates LLM responses against the structured output schemas defined in
governance_mandates.v1.schema.json. It enforces:
  - JSON Schema validation (all required fields, correct types)
  - Decision-rule validation (verdict-consistent findings)
  - Fail-closed on any violation

SSOT: governance_content/reference/rules.md
Schema: governance_runtime/assets/schemas/governance_mandates.v1.schema.json

Schema loading is done by callers (infrastructure/entrypoint layer) to respect
the architecture constraint that application-layer code must not perform filesystem I/O.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

_ALLOWED_REVIEW_VERDICTS = {"approve", "changes_requested"}
_ALLOWED_SEVERITIES = {"critical", "high", "medium", "low"}
_ALLOWED_FINDING_TYPES = {"defect", "risk", "contract-drift", "test-gap", "improvement"}


class ValidationResult(Enum):
    VALID = "valid"
    INVALID = "invalid"
    PARTIAL = "partial"


@dataclass
class ValidationViolation:
    field: str
    expected: str
    actual: str
    rule: str


@dataclass
class LLMResponseValidationResult:
    valid: bool
    result: ValidationResult
    verdict: str
    violations: list[ValidationViolation] = field(default_factory=list)
    findings_count: int = 0
    critical_findings: int = 0
    high_findings: int = 0
    raw_violations: list[str] = field(default_factory=list)
    error: str = ""


def _extract_output_schema(schema: dict[str, Any], name: str) -> dict[str, Any] | None:
    defs = schema.get("$defs", schema.get("$Defs", {}))
    # Find the actual key (JSON Schema uses $defs)
    key = next((k for k in defs.keys() if k == name), None)
    if key is None:
        return None
    return defs[key]


def _validate_json_schema(data: Any, schema: dict[str, Any]) -> list[str]:
    """Validate data against a JSON Schema definition using the jsonschema library."""
    try:
        import jsonschema

        validator = jsonschema.Draft7Validator(schema)
        errors = list(validator.iter_errors(data))
        return [f"{'.'.join(str(p) for p in e.path)}: {e.message}" if e.path else e.message for e in errors]
    except ImportError:
        return _validate_without_library(data, schema)
    except Exception as e:
        return [f"schema-validation-error: {e}"]


def _validate_without_library(data: Any, schema: dict[str, Any]) -> list[str]:
    """Fallback manual validator when jsonschema library is unavailable."""
    errors: list[str] = []

    def check(value: Any, s: dict[str, Any], path: str) -> None:
        stype = s.get("type")
        if stype == "object":
            if not isinstance(value, dict):
                errors.append(f"{path}: expected object, got {type(value).__name__}")
                return
            for prop, prop_schema in s.get("properties", {}).items():
                if prop not in value and prop in s.get("required", []):
                    errors.append(f"{path}.{prop}: required field missing")
                elif prop in value:
                    check(value[prop], prop_schema, f"{path}.{prop}")
        elif stype == "array":
            if not isinstance(value, list):
                errors.append(f"{path}: expected array, got {type(value).__name__}")
                return
            items_schema = s.get("items", {})
            for i, item in enumerate(value):
                check(item, items_schema, f"{path}[{i}]")
        elif stype == "string":
            if not isinstance(value, str):
                errors.append(f"{path}: expected string, got {type(value).__name__}")
            elif "minLength" in s and len(value) < s["minLength"]:
                errors.append(f"{path}: string too short (min {s['minLength']}, got {len(value)})")
            elif "enum" in s and value not in s["enum"]:
                errors.append(f"{path}: value '{value}' not in allowed set {s['enum']}")
        elif stype == "number":
            if not isinstance(value, (int, float)):
                errors.append(f"{path}: expected number, got {type(value).__name__}")

    check(data, schema, "$root")
    return errors


def _validate_review_decision_rules(data: dict[str, Any]) -> list[str]:
    """Apply decision rules from the Review mandate."""
    errors: list[str] = []
    verdict = str(data.get("verdict", "")).strip().lower()
    findings = data.get("findings", []) or []

    critical_findings = [f for f in findings if isinstance(f, dict) and f.get("severity") == "critical"]
    high_findings = [f for f in findings if isinstance(f, dict) and f.get("severity") == "high"]

    if verdict == "approve":
        defect_findings = [f for f in findings if isinstance(f, dict) and f.get("type") == "defect"]
        if defect_findings:
            errors.append(
                f"decision-rule-violation: verdict='approve' but {len(defect_findings)} defect findings present"
            )
        if critical_findings:
            errors.append(
                f"decision-rule-violation: verdict='approve' but {len(critical_findings)} critical findings present"
            )
        if high_findings:
            errors.append(
                f"decision-rule-violation: verdict='approve' but {len(high_findings)} high findings present"
            )

    if verdict == "changes_requested":
        if not findings:
            errors.append("decision-rule-violation: verdict='changes_requested' but no findings provided")

    for finding in findings:
        if not isinstance(finding, dict):
            errors.append(f"finding invalid: not a dict")
            continue
        sev = str(finding.get("severity", "")).strip().lower()
        ftype = str(finding.get("type", "")).strip().lower()
        loc = str(finding.get("location", "")).strip()
        evd = str(finding.get("evidence", "")).strip()
        imp = str(finding.get("impact", "")).strip()
        fix = str(finding.get("fix", "")).strip()
        if sev not in _ALLOWED_SEVERITIES:
            errors.append(f"finding.severity: '{sev}' not in allowed set {_ALLOWED_SEVERITIES}")
        if ftype not in _ALLOWED_FINDING_TYPES:
            errors.append(f"finding.type: '{ftype}' not in allowed set {_ALLOWED_FINDING_TYPES}")
        if len(loc) < 3:
            errors.append(f"finding.location: too short (min 3 chars)")
        if len(evd) < 10:
            errors.append(f"finding.evidence: too short (min 10 chars)")
        if len(imp) < 10:
            errors.append(f"finding.impact: too short (min 10 chars)")
        if len(fix) < 5:
            errors.append(f"finding.fix: too short (min 5 chars)")

    return errors


def _validate_developer_decision_rules(data: dict[str, Any]) -> list[str]:
    """Apply decision rules from the Developer mandate."""
    errors: list[str] = []

    required_strings = {
        "objective": 10,
        "governing_evidence": 10,
        "change_summary": 10,
        "contract_and_authority_check": 10,
        "test_evidence": 10,
        "regression_assessment": 10,
    }
    for field_name, min_len in required_strings.items():
        value = str(data.get(field_name, "")).strip()
        if len(value) < min_len:
            errors.append(f"developer.{field_name}: too short (min {min_len}, got {len(value)})")

    touched = data.get("touched_surface", [])
    if not isinstance(touched, list) or len(touched) < 1:
        errors.append("developer.touched_surface: at least 1 file/module required")

    residual = data.get("residual_risks", [])
    if not isinstance(residual, list):
        errors.append("developer.residual_risks: must be an array")

    return errors


def validate_review_response(
    data: Any,
    mandates_schema: dict[str, Any] | None = None,
    use_json_schema: bool = True,
    use_decision_rules: bool = True,
) -> LLMResponseValidationResult:
    """Validate an LLM review response against the output contract.

    Args:
        data: The parsed LLM response (should be a dict).
        mandates_schema: The compiled governance mandates schema dict. If provided and
            use_json_schema is True, JSON Schema validation is performed.
        use_json_schema: If True, validate against JSON Schema (requires mandates_schema).
        use_decision_rules: If True, apply decision rules from Review mandate.

    Returns:
        LLMResponseValidationResult with valid/invalid status and violation details.
    """
    if not isinstance(data, dict):
        return LLMResponseValidationResult(
            valid=False,
            result=ValidationResult.INVALID,
            verdict="unknown",
            raw_violations=[f"response must be a JSON object, got {type(data).__name__}"],
        )

    verdict = str(data.get("verdict", "")).strip().lower()
    if verdict not in _ALLOWED_REVIEW_VERDICTS:
        return LLMResponseValidationResult(
            valid=False,
            result=ValidationResult.INVALID,
            verdict=verdict,
            raw_violations=[f"verdict must be one of {list(_ALLOWED_REVIEW_VERDICTS)}, got '{verdict}'"],
        )

    findings = data.get("findings", []) or []
    critical_findings = [f for f in findings if isinstance(f, dict) and f.get("severity") == "critical"]
    high_findings = [f for f in findings if isinstance(f, dict) and f.get("severity") == "high"]

    all_errors: list[str] = []

    if use_json_schema and mandates_schema is not None:
        output_schema = _extract_output_schema(mandates_schema, "reviewOutputSchema")
        if output_schema:
            all_errors.extend(_validate_json_schema(data, output_schema))

    if use_decision_rules:
        all_errors.extend(_validate_review_decision_rules(data))

    violations = []
    for err in all_errors:
        violations.append(
            ValidationViolation(
                field=_extract_field_from_error(err),
                expected=_extract_expected_from_error(err),
                actual=_extract_actual_from_error(err),
                rule=err,
            )
        )

    return LLMResponseValidationResult(
        valid=len(all_errors) == 0,
        result=ValidationResult.VALID if not all_errors else ValidationResult.INVALID,
        verdict=verdict,
        violations=violations,
        raw_violations=all_errors,
        findings_count=len(findings),
        critical_findings=len(critical_findings),
        high_findings=len(high_findings),
    )


def validate_developer_response(
    data: Any,
    mandates_schema: dict[str, Any] | None = None,
    use_json_schema: bool = True,
    use_decision_rules: bool = True,
) -> LLMResponseValidationResult:
    """Validate an LLM developer response against the output contract.

    Args:
        data: The parsed LLM response (should be a dict).
        mandates_schema: The compiled governance mandates schema dict. If provided and
            use_json_schema is True, JSON Schema validation is performed.
        use_json_schema: If True, validate against JSON Schema (requires mandates_schema).
        use_decision_rules: If True, apply decision rules from Developer mandate.
    """
    if not isinstance(data, dict):
        return LLMResponseValidationResult(
            valid=False,
            result=ValidationResult.INVALID,
            verdict="unknown",
            raw_violations=[f"response must be a JSON object, got {type(data).__name__}"],
        )

    all_errors: list[str] = []

    if use_json_schema and mandates_schema is not None:
        output_schema = _extract_output_schema(mandates_schema, "developerOutputSchema")
        if output_schema:
            all_errors.extend(_validate_json_schema(data, output_schema))

    if use_decision_rules:
        all_errors.extend(_validate_developer_decision_rules(data))

    violations = []
    for err in all_errors:
        violations.append(
            ValidationViolation(
                field=_extract_field_from_error(err),
                expected=_extract_expected_from_error(err),
                actual=_extract_actual_from_error(err),
                rule=err,
            )
        )

    return LLMResponseValidationResult(
        valid=len(all_errors) == 0,
        result=ValidationResult.VALID if not all_errors else ValidationResult.INVALID,
        verdict="implementation_response",
        violations=violations,
        raw_violations=all_errors,
    )


def _extract_field_from_error(err: str) -> str:
    if ":" in err:
        prefix = err.split(":")[0].strip()
        if prefix.startswith("$root"):
            return prefix.replace("$root.", "")
        return prefix
    return err[:50]


def _extract_expected_from_error(err: str) -> str:
    if "expected" in err.lower():
        m = re.search(r"expected\s+(\w+)", err, re.IGNORECASE)
        if m:
            return m.group(1)
    if "not in allowed" in err.lower():
        m = re.search(r"not in allowed set\s+\{(.+?)\}", err)
        if m:
            return m.group(1)
    if "missing" in err.lower():
        return "required field"
    return "see rule"


def _extract_actual_from_error(err: str) -> str:
    if "got" in err.lower():
        m = re.search(r"got\s+(.+?)(?:\s*$|\s*,)", err, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    if "too short" in err.lower():
        m = re.search(r"min\s+(\d+),\s+got\s+(\d+)", err)
        if m:
            return f"length={m.group(2)}"
    if "missing" in err.lower():
        m = re.search(r"required field missing[:\s]*(.+)", err, re.IGNORECASE)
        if m:
            return f"missing: {m.group(1).strip()}"
    return "see rule"
