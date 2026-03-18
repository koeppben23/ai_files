"""Backward-compatible canonical JSON import surface.

Canonical implementation lives in `governance.domain.canonical_json`.
"""

from governance_runtime.domain.canonical_json import (  # noqa: F401
    canonical_json_bytes,
    canonical_json_clone,
    canonical_json_hash,
    canonical_json_text,
)
