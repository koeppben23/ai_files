"""Git port interface.

.. deprecated::
    Use governance_runtime.application.ports.git instead.
    This module will be removed in a future release.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class GitPort(Protocol):
    def repo_root(self, cwd: Path | None = None) -> Path | None: ...
