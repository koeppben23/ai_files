"""Canonical persistence target policy guards.

Wave A intent: centralize target validation rules without changing runtime wiring.
This module is deterministic and fail-closed; callers can use the result object to
block writes before any filesystem mutation.
"""

from __future__ import annotations

from dataclasses import dataclass
import re


BLOCKED_PERSISTENCE_TARGET_DEGENERATE = "BLOCKED-PERSISTENCE-TARGET-DEGENERATE"
BLOCKED_PERSISTENCE_PATH_VIOLATION = "BLOCKED-PERSISTENCE-PATH-VIOLATION"

_DRIVE_LETTER_ONLY = re.compile(r"^[A-Za-z]$")
_DRIVE_ROOT_ONLY = re.compile(r"^[A-Za-z]:$")
_DRIVE_RELATIVE = re.compile(r"^[A-Za-z]:[^\\/].*")
_SINGLE_SEGMENT_RELATIVE = re.compile(r"^[^\\/]+$")


@dataclass(frozen=True)
class WriteTargetPolicyResult:
    """Validation outcome for one target-path string."""

    valid: bool
    reason_code: str
    detail: str


def _looks_like_variable_path(target_path: str) -> bool:
    """Return True when path starts with a canonical variable token."""

    return target_path.startswith("${")


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
            detail="target path must not be empty",
        )

    if _DRIVE_LETTER_ONLY.fullmatch(path):
        return WriteTargetPolicyResult(
            valid=False,
            reason_code=BLOCKED_PERSISTENCE_TARGET_DEGENERATE,
            detail="target path is a single drive letter",
        )

    if _DRIVE_ROOT_ONLY.fullmatch(path):
        return WriteTargetPolicyResult(
            valid=False,
            reason_code=BLOCKED_PERSISTENCE_TARGET_DEGENERATE,
            detail="target path is drive-root token only",
        )

    if _DRIVE_RELATIVE.fullmatch(path):
        return WriteTargetPolicyResult(
            valid=False,
            reason_code=BLOCKED_PERSISTENCE_TARGET_DEGENERATE,
            detail="target path is drive-relative",
        )

    if _SINGLE_SEGMENT_RELATIVE.fullmatch(path) and not _looks_like_variable_path(path):
        return WriteTargetPolicyResult(
            valid=False,
            reason_code=BLOCKED_PERSISTENCE_TARGET_DEGENERATE,
            detail="target path is non-variable single-segment relative",
        )

    if not _looks_like_variable_path(path):
        return WriteTargetPolicyResult(
            valid=False,
            reason_code=BLOCKED_PERSISTENCE_PATH_VIOLATION,
            detail="target path must use canonical variable form",
        )

    return WriteTargetPolicyResult(valid=True, reason_code="none", detail="ok")
