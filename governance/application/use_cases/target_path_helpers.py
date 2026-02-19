"""Target path parsing and output request helpers."""

from __future__ import annotations

import re


VARIABLE_CAPTURE = re.compile(r"^\$\{([A-Z0-9_]+)\}")


def extract_target_variable(target_path: str) -> str | None:
    """Extract canonical variable token from target path string."""

    match = VARIABLE_CAPTURE.match(target_path.strip())
    if match is None:
        return None
    return match.group(1)


def is_code_output_request(requested_action: str | None) -> bool:
    """Fail-closed: any non-empty action in phase 4 is treated as a code-output
    request unless it matches a known read-only / observation-only allowlist.
    This prevents denylist bypass via synonym substitution (A8-F01)."""
    action = (requested_action or "").strip().lower()
    if not action:
        return False
    safe_patterns = (
        "review", "explain", "summarize", "describe", "list",
        "check", "verify", "inspect", "read", "show", "status",
        "plan", "outline", "analyse", "analyze", "compare",
    )
    return not any(token in action for token in safe_patterns)
