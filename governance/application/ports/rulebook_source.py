"""Rulebook source port interface.

.. deprecated::
    Use governance_runtime.application.ports.rulebook_source instead.
    This module will be removed in a future release.
"""

from __future__ import annotations

from typing import Protocol

from governance.domain.models.rulebooks import RulebookRef


class RulebookSourcePort(Protocol):
    def load(self, identifier: str) -> RulebookRef | None: ...
