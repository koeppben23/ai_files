"""Pack loader content policy guards for Wave C.

These checks enforce allowlisted pack artifact types and reject execution-like
directives so packs remain declarative policy artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from pathlib import Path
from typing import Mapping

ALLOWED_PACK_SUFFIXES = frozenset({".md", ".yaml", ".yml", ".txt", ".template"})

_EXEC_LINE = re.compile(r"^\s*!\S+")
_YAML_EXEC_KEY = re.compile(r"^\s*(exec|run|shell)\s*:", re.IGNORECASE)
_SHELL_FENCE = re.compile(r"^\s*```\s*(sh|bash|zsh|shell)\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class PackPolicyViolation:
    """One deterministic pack policy violation record."""

    path: str
    rule: str
    detail: str


def validate_pack_file_type(path: str) -> PackPolicyViolation | None:
    """Validate one pack artifact path against extension allowlist."""

    suffix = Path(path).suffix.lower()
    if suffix in ALLOWED_PACK_SUFFIXES:
        return None
    return PackPolicyViolation(
        path=path,
        rule="pack-file-type-allowlist",
        detail=f"forbidden file type: {suffix or '<no-ext>'}",
    )


def validate_pack_text(path: str, content: str) -> list[PackPolicyViolation]:
    """Validate pack text content for forbidden execution directives."""

    violations: list[PackPolicyViolation] = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        if _EXEC_LINE.match(line):
            violations.append(
                PackPolicyViolation(
                    path=path,
                    rule="pack-no-command-lines",
                    detail=f"line {line_number}: command-style directive is forbidden",
                )
            )
        if _YAML_EXEC_KEY.match(line):
            violations.append(
                PackPolicyViolation(
                    path=path,
                    rule="pack-no-exec-yaml-keys",
                    detail=f"line {line_number}: runtime execution key is forbidden",
                )
            )
        if _SHELL_FENCE.match(line):
            violations.append(
                PackPolicyViolation(
                    path=path,
                    rule="pack-no-shell-fences",
                    detail=f"line {line_number}: shell fenced block marker is forbidden",
                )
            )
    return violations


def validate_pack_artifacts(files_by_path: Mapping[str, str]) -> list[PackPolicyViolation]:
    """Validate pack artifacts deterministically and return sorted violations."""

    violations: list[PackPolicyViolation] = []
    for path in sorted(files_by_path):
        type_violation = validate_pack_file_type(path)
        if type_violation is not None:
            violations.append(type_violation)
            continue
        violations.extend(validate_pack_text(path, files_by_path[path]))

    return sorted(violations, key=lambda item: (item.path, item.rule, item.detail))
