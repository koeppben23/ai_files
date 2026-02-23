from __future__ import annotations

from typing import Protocol

from kernel.domain.errors.events import ErrorEvent


class ErrorLoggerPort(Protocol):
    def write(self, event: ErrorEvent) -> None: ...
