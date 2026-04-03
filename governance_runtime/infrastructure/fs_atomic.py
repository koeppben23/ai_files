"""Atomic file system operations.

Canonical runtime implementation for atomic filesystem writes/replaces.
"""

from __future__ import annotations

import errno
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any, Callable, TypeVar

T = TypeVar("T")


def _is_windows() -> bool:
    """Return True when running on Windows.

    Encapsulated so test code can ``monkeypatch.setattr(fs_atomic, "_is_windows", …)``
    instead of globally patching ``os.name``, which poisons ``pathlib.Path()``
    and pytest internals on cross-platform CI.
    """
    return os.name == "nt"


def _platform_path(path: Path) -> str:
    """Return *raw* on POSIX; add ``\\\\?\\`` long-path prefix on Windows.

    The guard ``raw.startswith("/")`` is a safety net: if ``_is_windows()``
    returns True while running on a POSIX host (e.g. in tests), the
    resulting absolute path is still ``/…``-rooted and must never receive a
    UNC prefix.
    """
    raw = os.path.abspath(str(path))
    if not _is_windows() or raw.startswith("/"):
        return raw
    if raw.startswith("\\\\?\\"):
        return raw
    if raw.startswith("\\\\"):
        return "\\\\?\\UNC\\" + raw[2:]
    return "\\\\?\\" + raw


def is_retryable_replace_error(exc: OSError) -> bool:
    return getattr(exc, "errno", None) in {errno.EACCES, errno.EPERM, errno.EBUSY, 13, 16}


def bounded_retry(fn: Callable[[], T], attempts: int = 5, backoff_ms: int = 50) -> T:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return fn()
        except OSError as exc:
            last_error = exc
            if attempt == attempts - 1 or not is_retryable_replace_error(exc):
                raise
            time.sleep(backoff_ms / 1000.0)
    if last_error is not None:
        raise last_error
    raise RuntimeError("bounded_retry failed without exception")


def fsync_dir(path: Path) -> None:
    """Flush directory metadata to disk after an atomic rename.

    On Windows, directory fsync is not supported — opening a directory
    with ``O_RDONLY`` raises ``PermissionError``.  ``os.replace()``
    remains the relevant atomicity boundary on Windows, but this does
    **not** provide the same durability guarantee as POSIX directory
    fsync.  We return early with an explicit platform check rather than
    silently swallowing the ``PermissionError``.
    """
    if _is_windows():
        return
    try:
        fd = os.open(_platform_path(path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def safe_replace_with_retries(tmp: Path, target: Path, *, attempts: int = 5, backoff_ms: int = 50) -> int:
    def _replace() -> None:
        os.replace(_platform_path(tmp), _platform_path(target))
        fsync_dir(target.parent)

    for attempt in range(attempts):
        try:
            _replace()
            return attempt
        except OSError as exc:
            if attempt == attempts - 1 or not is_retryable_replace_error(exc):
                raise
            time.sleep(backoff_ms / 1000.0)
    return 0


def safe_replace(tmp: Path, target: Path, *, attempts: int = 5, backoff_ms: int = 50) -> None:
    safe_replace_with_retries(tmp, target, attempts=attempts, backoff_ms=backoff_ms)


def atomic_write_text(path: Path, text: str, newline_lf: bool = True, attempts: int = 5, backoff_ms: int = 50) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    payload = text.replace("\r\n", "\n") if newline_lf else text
    try:
        # Use a very short prefix to avoid exceeding Windows MAX_PATH (260 chars).
        # The full filename (e.g. "review-decision-record.json.") is unnecessary
        # for uniqueness — tempfile already guarantees a unique random suffix.
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n" if newline_lf else None,
            dir=_platform_path(path.parent),
            prefix=".",
            suffix=".tmp",
            delete=False,
        ) as tmp:
            tmp.write(payload)
            tmp.flush()
            os.fsync(tmp.fileno())
            temp_path = Path(tmp.name)
        return safe_replace_with_retries(temp_path, path, attempts=attempts, backoff_ms=backoff_ms)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink(missing_ok=True)


def atomic_write_json(path: Path, obj: Any, *, ensure_ascii: bool = True, indent: int = 2) -> None:
    text = json.dumps(obj, indent=indent, ensure_ascii=ensure_ascii) + "\n"
    atomic_write_text(path, text, newline_lf=True)
