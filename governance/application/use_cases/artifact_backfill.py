from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BackfillSummary:
    actions: dict[str, str] = field(default_factory=dict)
    missing: tuple[str, ...] = field(default_factory=tuple)
    phase2_ok: bool = False
