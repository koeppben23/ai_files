"""Canonical user-facing next-action resolver.

This module is the single source of truth for operator guidance lines that are
rendered at the bottom of session readouts and reused by mutating rails.

The underlying transition model is defined in:
    governance_runtime.application.services.transition_model
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from governance_runtime.application.services.transition_model import (
    resolve_next_action as _resolve_from_model,
)


@dataclass(frozen=True)
class NextActionRender:
    """Rendered next action for operator guidance."""

    command: str
    label: str
    kind: str
    reason: str


def resolve_next_action(snapshot: Mapping[str, object]) -> NextActionRender:
    """Resolve the canonical next action using the transition model.

    Args:
        snapshot: The session state snapshot.

    Returns:
        NextActionRender with command, label, kind, and reason.
    """
    result = _resolve_from_model(snapshot)
    return NextActionRender(
        command=result.command,
        label=result.label,
        kind=result.kind.value,
        reason=result.reason,
    )
