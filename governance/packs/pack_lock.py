"""Legacy compatibility bridge for pack lock resolution.

DEPRECATED: use governance_runtime.infrastructure.pack_lock.
"""

from governance_runtime.infrastructure.pack_lock import (
    LOCK_SCHEMA,
    PackManifest,
    normalize_manifest,
    resolve_pack_lock,
    write_pack_lock,
)

__all__ = [
    "LOCK_SCHEMA",
    "PackManifest",
    "normalize_manifest",
    "resolve_pack_lock",
    "write_pack_lock",
]
