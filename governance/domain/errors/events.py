"""Error events for governance runtime.

.. deprecated::
    Use governance_runtime.domain.errors.events instead.
    This module will be removed in a future release.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ErrorEvent:
    code: str
    severity: str
    message: str
    expected: str | None = None
    observed: Any = None
    remediation: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
