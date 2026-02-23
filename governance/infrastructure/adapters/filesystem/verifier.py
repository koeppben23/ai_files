from __future__ import annotations

from pathlib import Path


def verify_exists(path: Path) -> bool:
    return path.exists()
