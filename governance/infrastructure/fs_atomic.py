"""Legacy compatibility bridge for atomic filesystem operations.

DEPRECATED: use governance_runtime.infrastructure.fs_atomic.
"""

from governance_runtime.infrastructure.fs_atomic import (  # noqa: F401
    atomic_write_json,
    atomic_write_text,
    bounded_retry,
    fsync_dir,
    is_retryable_replace_error,
    safe_replace,
    safe_replace_with_retries,
)

__all__ = [
    "atomic_write_json",
    "atomic_write_text",
    "bounded_retry",
    "fsync_dir",
    "is_retryable_replace_error",
    "safe_replace",
    "safe_replace_with_retries",
]
