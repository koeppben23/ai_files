"""Cross-field invariant validators for SESSION_STATE.

These validators check constraints that cannot be expressed in JSON Schema alone,
such as conditional requirements based on other field values.
"""

from __future__ import annotations

import re
from typing import Mapping


_PATH_FIELD_SUFFIXES = ("Path", "FilePath")
_PATH_FIELD_NAMES = ("TargetPath", "SourcePath")
_FORBIDDEN_PATTERNS = (
    (re.compile(r"^[A-Za-z]:"), "BLOCKED-PERSISTENCE-PATH-VIOLATION", "drive_prefix"),
    (re.compile(r"\\"), "BLOCKED-PERSISTENCE-PATH-VIOLATION", "backslash"),
    (re.compile(r"\.\."), "BLOCKED-PERSISTENCE-PATH-VIOLATION", "parent_traversal"),
)
_DEGENERATE_PATTERNS = (
    (re.compile(r"^[A-Za-z]$"), "BLOCKED-PERSISTENCE-TARGET-DEGENERATE", "single_drive_letter"),
    (re.compile(r"^[A-Za-z]:$"), "BLOCKED-PERSISTENCE-TARGET-DEGENERATE", "drive_root_token"),
    (re.compile(r"^[A-Za-z]:[^\\/]"), "BLOCKED-PERSISTENCE-TARGET-DEGENERATE", "drive_relative_path"),
)


def validate_blocked_next_invariant(state: Mapping[str, object]) -> tuple[str, ...]:
    """If Mode=BLOCKED, Next MUST start with 'BLOCKED-'."""
    mode = state.get("Mode")
    next_val = state.get("Next")

    if mode != "BLOCKED":
        return ()

    if not isinstance(next_val, str):
        return ("blocked_next_not_string",)

    if not next_val.startswith("BLOCKED-"):
        return ("blocked_next_missing_prefix",)

    return ()


def validate_confidence_mode_invariant(state: Mapping[str, object]) -> tuple[str, ...]:
    """If ConfidenceLevel < 70, Mode MUST be DRAFT or BLOCKED."""
    confidence = state.get("ConfidenceLevel")
    mode = state.get("Mode")

    if not isinstance(confidence, int):
        return ()

    if confidence >= 70:
        return ()

    if mode not in ("DRAFT", "BLOCKED"):
        return ("low_confidence_not_draft_or_blocked",)

    return ()


def validate_profile_source_blocked_invariant(state: Mapping[str, object]) -> tuple[str, ...]:
    """If ProfileSource=ambiguous, Mode MUST be BLOCKED."""
    profile_source = state.get("ProfileSource")
    mode = state.get("Mode")

    if profile_source != "ambiguous":
        return ()

    if mode != "BLOCKED":
        return ("ambiguous_profile_not_blocked",)

    return ()


def validate_reason_payloads_required(state: Mapping[str, object]) -> tuple[str, ...]:
    """If any BLOCKED-/WARN-/NOT_VERIFIED- code appears, Diagnostics.ReasonPayloads MUST exist."""
    mode = state.get("Mode")
    next_val = state.get("Next", "")

    if mode not in ("BLOCKED", "DRAFT"):
        if isinstance(next_val, str) and not next_val.startswith(("BLOCKED-", "WARN-", "NOT_VERIFIED-")):
            return ()

    diagnostics = state.get("Diagnostics")
    if not isinstance(diagnostics, dict):
        return ("missing_diagnostics_for_reason_code",)

    payloads = diagnostics.get("ReasonPayloads")
    if not isinstance(payloads, list) or len(payloads) == 0:
        return ("missing_reason_payloads",)

    return ()


def validate_session_state_invariants(session_state_document: Mapping[str, object]) -> tuple[str, ...]:
    """Run all cross-field invariant validators and return all violations."""
    state = session_state_document.get("SESSION_STATE")
    if not isinstance(state, Mapping):
        return ("missing_session_state_key",)

    errors: list[str] = []
    errors.extend(validate_blocked_next_invariant(state))
    errors.extend(validate_confidence_mode_invariant(state))
    errors.extend(validate_profile_source_blocked_invariant(state))
    errors.extend(validate_reason_payloads_required(state))
    errors.extend(validate_output_mode_architect_invariant(state))
    errors.extend(validate_rulebook_evidence_mirror(state))
    errors.extend(validate_addon_evidence_mirror(state))
    errors.extend(validate_canonical_path_invariants(state))

    return tuple(errors)


def validate_output_mode_architect_invariant(state: Mapping[str, object]) -> tuple[str, ...]:
    """If OutputMode=ARCHITECT, DecisionSurface MUST exist."""
    output_mode = state.get("OutputMode")
    decision_surface = state.get("DecisionSurface")

    if output_mode != "ARCHITECT":
        return ()

    if decision_surface is None:
        return ("architect_mode_missing_decision_surface",)

    return ()


def validate_rulebook_evidence_mirror(state: Mapping[str, object]) -> tuple[str, ...]:
    """If LoadedRulebooks.core is non-empty, RulebookLoadEvidence.core MUST exist."""
    loaded = state.get("LoadedRulebooks")
    evidence = state.get("RulebookLoadEvidence")

    if not isinstance(loaded, dict):
        return ()

    core_path = loaded.get("core")
    if not isinstance(core_path, str) or not core_path.strip():
        return ()

    if not isinstance(evidence, dict):
        return ("missing_rulebook_load_evidence",)

    if "core" not in evidence:
        return ("rulebook_evidence_missing_core",)

    return ()


def validate_addon_evidence_mirror(state: Mapping[str, object]) -> tuple[str, ...]:
    """If addon is in LoadedRulebooks.addons, AddonsEvidence.<key> MUST exist."""
    loaded = state.get("LoadedRulebooks")
    addons_evidence = state.get("AddonsEvidence")

    if not isinstance(loaded, dict):
        return ()

    loaded_addons = loaded.get("addons")
    if not isinstance(loaded_addons, dict) or len(loaded_addons) == 0:
        return ()

    if not isinstance(addons_evidence, dict):
        return ("missing_addons_evidence_for_loaded_addons",)

    missing: list[str] = []
    for addon_key in loaded_addons.keys():
        if addon_key not in addons_evidence:
            missing.append(addon_key)

    if missing:
        return (f"addons_evidence_missing:{','.join(sorted(missing))}",)

    return ()


def _is_path_field(key: str) -> bool:
    """Check if a field is a canonical path field based on naming conventions."""
    if key.endswith(_PATH_FIELD_SUFFIXES):
        return True
    if key in _PATH_FIELD_NAMES:
        return True
    return False


def _validate_path_value(path_value: str, field_path: str) -> tuple[str, ...]:
    """Validate a single path value against forbidden and degenerate patterns."""
    if not isinstance(path_value, str) or not path_value.strip():
        return ()

    errors: list[str] = []

    for pattern, reason_code, pattern_name in _FORBIDDEN_PATTERNS:
        if pattern.search(path_value):
            errors.append(f"path_violation:{field_path}:{reason_code}:{pattern_name}")

    for pattern, reason_code, pattern_name in _DEGENERATE_PATTERNS:
        if pattern.search(path_value):
            errors.append(f"path_violation:{field_path}:{reason_code}:{pattern_name}")

    single_segment = re.match(r"^[^\\/]+$", path_value)
    if single_segment and not path_value.startswith("${"):
        errors.append(f"path_violation:{field_path}:BLOCKED-PERSISTENCE-TARGET-DEGENERATE:single_segment_without_variable")

    return tuple(errors)


def validate_canonical_path_invariants(state: Mapping[str, object]) -> tuple[str, ...]:
    """Validate all canonical path fields against forbidden patterns.

    From SESSION_STATE_SCHEMA.md lines 68-118:
    - Forbidden patterns (→ BLOCKED-PERSISTENCE-PATH-VIOLATION):
      - Windows drive prefixes, backslashes, parent traversal
    - Degenerate patterns (→ BLOCKED-PERSISTENCE-TARGET-DEGENERATE):
      - Single drive letter, drive root token, drive-relative path
      - Single-segment relative path WITHOUT ${...}
    """
    errors: list[str] = []

    def check_object(obj: Mapping[str, object], prefix: str) -> None:
        for key, value in obj.items():
            field_path = f"{prefix}.{key}" if prefix else key

            if _is_path_field(key) and isinstance(value, str):
                errors.extend(_validate_path_value(value, field_path))
            elif isinstance(value, dict):
                check_object(value, field_path)

    check_object(state, "SESSION_STATE")
    return tuple(errors)
