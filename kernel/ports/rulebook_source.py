from __future__ import annotations

from typing import Protocol

from kernel.domain.models.rulebooks import RulebookRef


class RulebookSourcePort(Protocol):
    def load(self, identifier: str) -> RulebookRef | None: ...
