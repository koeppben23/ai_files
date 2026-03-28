"""Canonical Next Action contract for rail entrypoints.

This module defines the structured Next Action fields that every rail
result must contain when a user-facing follow-up action exists.

Contract fields:
    next_action_code: Machine-readable action code (optional but recommended)
    next_action: Human-readable action description (required when action exists)
    next_action_command: CLI command to execute (only when deterministically safe)

Rendering rules:
    Quiet mode: JSON only (fields are present but no extra text line)
    Normal mode: JSON + "Next action: <command or description>" line
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class NextAction:
    """Structured next action for rail results."""

    code: str | None = None  # e.g. "RETRY_PLAN_WITH_EXPLICIT_TEXT"
    text: str | None = None  # e.g. "Retry planning with explicit plan text input."
    command: str | None = None  # e.g. "/plan --plan-text ..." (only when deterministically safe)

    def to_dict(self) -> dict[str, str]:
        """Convert to dict for JSON serialization. Omits None values."""
        result: dict[str, str] = {}
        if self.code:
            result["next_action_code"] = self.code
        if self.text:
            result["next_action"] = self.text
        if self.command:
            result["next_action_command"] = self.command
        return result

    def render_line(self) -> str | None:
        """Render the Next action line for normal mode output.
        
        Returns None if no action is available.
        Prefers command over text for deterministic execution.
        """
        if self.command:
            return f"Next action: {self.command}"
        if self.text:
            return f"Next action: {self.text}"
        return None


def render_next_action_line(payload: Mapping[str, object]) -> str | None:
    """Extract and render next action line from a rail payload.
    
    This is the canonical renderer - it derives nothing, only displays
    what's in the payload.
    """
    command = payload.get("next_action_command")
    if command:
        return f"Next action: {command}"
    text = payload.get("next_action")
    if text:
        return f"Next action: {text}"
    return None


# --- Predefined Next Actions ---

class NextActions:
    """Predefined next actions for common rail states."""

    CONTINUE = NextAction(
        code="CONTINUE",
        text="run /continue.",
        command="/continue",
    )

    PLAN_RETRY_WITH_EXPLICIT = NextAction(
        code="RETRY_PLAN_WITH_EXPLICIT_TEXT",
        text="Retry planning with explicit plan text input.",
        command="/plan --plan-text ...",
    )

    TICKET_REQUIRED = NextAction(
        code="TICKET_REQUIRED",
        text="Provide ticket/task details to continue.",
        command="/ticket",
    )

    IMPLEMENT_START = NextAction(
        code="IMPLEMENT_START",
        text="run /implement.",
        command="/implement",
    )

    REVIEW_DECISION = NextAction(
        code="REVIEW_DECISION",
        text="Submit review decision.",
        command="/review-decision <approve|changes_requested|reject>",
    )

    DESCRIBE_CHANGES = NextAction(
        code="DESCRIBE_CHANGES",
        text="describe the requested changes in chat.",
        command=None,  # No deterministic command - user must type
    )

    TICKET_REVISED = NextAction(
        code="TICKET_REVISED",
        text="run /ticket with revised task details.",
        command="/ticket",
    )
