from __future__ import annotations

from pathlib import Path
from typing import Protocol


class GitPort(Protocol):
    def repo_root(self, cwd: Path | None = None) -> Path | None: ...
