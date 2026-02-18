"""Canonical persistence target policy guards.

Wave A intent: centralize target validation rules without changing runtime wiring.
This module is deterministic and fail-closed; callers can use the result object to
block writes before any filesystem mutation.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from governance.engine.reason_codes import (
    BLOCKED_PERSISTENCE_PATH_VIOLATION,
    BLOCKED_PERSISTENCE_TARGET_DEGENERATE,
    REASON_CODE_NONE,
)


_CANONICAL_VARIABLE_PATH = re.compile(r"^\$\{([A-Z0-9_]+)\}(.*)$")
_PATH_SEPARATOR_RUN = re.compile(r"[\\/]+")

_ALLOWED_CANONICAL_VARIABLES = frozenset(
    {
        "COMMANDS_HOME",
        "CONFIG_ROOT",
        "OPENCODE_HOME",
        "PROFILES_HOME",
        "REPO_BUSINESS_RULES_FILE",
        "REPO_CACHE_FILE",
        "REPO_DECISION_PACK_FILE",
        "REPO_DIGEST_FILE",
        "REPO_HOME",
        "REPO_OVERRIDES_HOME",
        "SESSION_STATE_FILE",
        "SESSION_STATE_POINTER_FILE",
        "WORKSPACES_HOME",
        "WORKSPACE_MEMORY_FILE",
    }
)

_DRIVE_LETTER_ONLY = re.compile(r"^[A-Za-z]$")
_DRIVE_ROOT_ONLY = re.compile(r"^[A-Za-z]:$")
_DRIVE_RELATIVE = re.compile(r"^[A-Za-z]:[^\\/].*")
_SINGLE_SEGMENT_RELATIVE = re.compile(r"^[^\\/]+$")

DETAIL_OK = "ok"
DETAIL_KEY_EMPTY_TARGET = "empty_target"
DETAIL_KEY_DRIVE_LETTER_ONLY = "drive_letter_only"
DETAIL_KEY_DRIVE_ROOT_ONLY = "drive_root_only"
DETAIL_KEY_DRIVE_RELATIVE = "drive_relative"
DETAIL_KEY_SINGLE_SEGMENT_RELATIVE = "single_segment_relative"
DETAIL_KEY_NON_VARIABLE_PATH = "non_variable_path"
DETAIL_KEY_INVALID_VARIABLE_TOKEN = "invalid_variable_token"
DETAIL_KEY_UNKNOWN_VARIABLE = "unknown_variable"
DETAIL_KEY_PARENT_TRAVERSAL = "parent_traversal"


@dataclass(frozen=True)
class WriteTargetPolicyResult:
    """Validation outcome for one target-path string."""

    valid: bool
    reason_code: str
    detail_key: str
    detail: str


def _looks_like_variable_path(target_path: str) -> bool:
    """Return True when path starts with a canonical variable token."""

    return target_path.startswith("${")


def _extract_variable_parts(target_path: str) -> tuple[str, str] | None:
    """Extract `${VARIABLE}` and suffix from canonical variable-form paths."""

    match = _CANONICAL_VARIABLE_PATH.fullmatch(target_path)
    if not match:
        return None
    return match.group(1), match.group(2)


def _contains_parent_traversal(path_suffix: str) -> bool:
    """Detect parent traversal segments in variable-path suffixes."""

    normalized = _PATH_SEPARATOR_RUN.sub("/", path_suffix)
    segments = [segment for segment in normalized.split("/") if segment not in ("", ".")]
    return any(segment == ".." for segment in segments)


def evaluate_target_path(target_path: str) -> WriteTargetPolicyResult:
    """Evaluate one target path string against canonical fail-closed rules.

    The policy mirrors baseline constraints for degenerate and non-canonical
    persistence targets and returns explicit reason codes for deterministic
    recovery messaging.
    """

    path = target_path.strip()
    if not path:
        return WriteTargetPolicyResult(
            valid=False,
            reason_code=BLOCKED_PERSISTENCE_TARGET_DEGENERATE,
            detail_key=DETAIL_KEY_EMPTY_TARGET,
            detail="target path must not be empty",
        )

    if _DRIVE_LETTER_ONLY.fullmatch(path):
        return WriteTargetPolicyResult(
            valid=False,
            reason_code=BLOCKED_PERSISTENCE_TARGET_DEGENERATE,
            detail_key=DETAIL_KEY_DRIVE_LETTER_ONLY,
            detail="target path is a single drive letter",
        )

    if _DRIVE_ROOT_ONLY.fullmatch(path):
        return WriteTargetPolicyResult(
            valid=False,
            reason_code=BLOCKED_PERSISTENCE_TARGET_DEGENERATE,
            detail_key=DETAIL_KEY_DRIVE_ROOT_ONLY,
            detail="target path is drive-root token only",
        )

    if _DRIVE_RELATIVE.fullmatch(path):
        return WriteTargetPolicyResult(
            valid=False,
            reason_code=BLOCKED_PERSISTENCE_TARGET_DEGENERATE,
            detail_key=DETAIL_KEY_DRIVE_RELATIVE,
            detail="target path is drive-relative",
        )

    if _SINGLE_SEGMENT_RELATIVE.fullmatch(path) and not _looks_like_variable_path(path):
        return WriteTargetPolicyResult(
            valid=False,
            reason_code=BLOCKED_PERSISTENCE_TARGET_DEGENERATE,
            detail_key=DETAIL_KEY_SINGLE_SEGMENT_RELATIVE,
            detail="target path is non-variable single-segment relative",
        )

    if not _looks_like_variable_path(path):
        return WriteTargetPolicyResult(
            valid=False,
            reason_code=BLOCKED_PERSISTENCE_PATH_VIOLATION,
            detail_key=DETAIL_KEY_NON_VARIABLE_PATH,
            detail="target path must use canonical variable form",
        )

    variable_parts = _extract_variable_parts(path)
    if variable_parts is None:
        return WriteTargetPolicyResult(
            valid=False,
            reason_code=BLOCKED_PERSISTENCE_PATH_VIOLATION,
            detail_key=DETAIL_KEY_INVALID_VARIABLE_TOKEN,
            detail="target path must start with a valid ${VARIABLE} token",
        )

    variable_name, suffix = variable_parts
    if variable_name not in _ALLOWED_CANONICAL_VARIABLES:
        return WriteTargetPolicyResult(
            valid=False,
            reason_code=BLOCKED_PERSISTENCE_PATH_VIOLATION,
            detail_key=DETAIL_KEY_UNKNOWN_VARIABLE,
            detail="target path uses an unknown canonical variable",
        )

    if _contains_parent_traversal(suffix):
        return WriteTargetPolicyResult(
            valid=False,
            reason_code=BLOCKED_PERSISTENCE_PATH_VIOLATION,
            detail_key=DETAIL_KEY_PARENT_TRAVERSAL,
            detail="target path must not contain parent traversal segments",
        )

    return WriteTargetPolicyResult(
        valid=True,
        reason_code=REASON_CODE_NONE,
        detail_key=DETAIL_OK,
        detail="ok",
    )
