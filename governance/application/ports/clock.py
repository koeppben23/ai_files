"""Clock port interface.

.. deprecated::
    Use governance_runtime.application.ports.clock instead.
    This module will be removed in a future release.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class ClockPort(Protocol):
    def now(self) -> datetime: ...
