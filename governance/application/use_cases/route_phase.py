from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RoutedPhase:
    phase: str
    blocked_code: str | None
    reason: str
    next_action: str
