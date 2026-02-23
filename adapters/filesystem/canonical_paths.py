from __future__ import annotations

import os
from pathlib import Path


def canonical_absolute(path: str) -> Path:
    token = path.strip()
    if not token:
        raise ValueError("path must not be empty")
    candidate = Path(token).expanduser()
    if not candidate.is_absolute():
        raise ValueError("path must be absolute")
    return Path(os.path.normpath(os.path.abspath(str(candidate))))
