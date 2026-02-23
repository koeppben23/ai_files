from __future__ import annotations

from dataclasses import dataclass

from kernel.domain.models.rulebooks import RulebookSet


@dataclass(frozen=True)
class LoadedRulebooks:
    rules: RulebookSet
    source: str
