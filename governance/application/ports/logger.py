"""Logger port interface.

.. deprecated::
    Use governance_runtime.application.ports.logger instead.
    This module will be removed in a future release.
"""

from __future__ import annotations

from typing import Protocol

from governance.domain.errors.events import ErrorEvent


class ErrorLoggerPort(Protocol):
    def write(self, event: ErrorEvent) -> None: ...
