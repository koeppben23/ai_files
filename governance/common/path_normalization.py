from __future__ import annotations

import os
from pathlib import Path


def normalize_for_fingerprint(path: Path) -> str:
    """Return deterministic normalized path material for fingerprint hashing."""

    normalized = os.path.normpath(os.path.abspath(str(path.expanduser())))
    normalized = normalized.replace("\\", "/")
    if os.name == "nt":
        return normalized.casefold()
    return normalized
