"""Backward-compatible canonical JSON import surface.

.. deprecated::
    Use governance_runtime.engine.canonical_json instead.
    This module will be removed in a future release.

Canonical implementation lives in `governance.domain.canonical_json`.
"""

from __future__ import annotations

from governance_runtime.engine.canonical_json import (  # noqa: F401
    canonical_json_bytes,
    canonical_json_clone,
    canonical_json_hash,
    canonical_json_text,
)
