"""Pure hash utilities - stateless, no IO, deterministic.

This module belongs to the shared/support layer and can be imported
by any layer including application services.
"""

from __future__ import annotations

import hashlib


def sha256_text(value: str) -> str:
    """Return hex SHA-256 digest of a UTF-8 encoded string.

    Pure, deterministic helper with no side effects.
    """
    return hashlib.sha256(value.encode("utf-8")).hexdigest()