from __future__ import annotations

import errno
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any, Callable, TypeVar

T = TypeVar("T")


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
    try:
        fd = os.open(str(path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def safe_replace(tmp: Path, target: Path, *, attempts: int = 5, backoff_ms: int = 50) -> None:
    def _replace() -> None:
        os.replace(str(tmp), str(target))
        fsync_dir(target.parent)

    bounded_retry(_replace, attempts=attempts, backoff_ms=backoff_ms)


def atomic_write_text(path: Path, text: str, newline_lf: bool = True, attempts: int = 5, backoff_ms: int = 50) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    payload = text.replace("\r\n", "\n") if newline_lf else text
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n" if newline_lf else None,
            dir=str(path.parent),
            prefix=path.name + ".",
            suffix=".tmp",
            delete=False,
        ) as tmp:
            tmp.write(payload)
            tmp.flush()
            os.fsync(tmp.fileno())
            temp_path = Path(tmp.name)
        safe_replace(temp_path, path, attempts=attempts, backoff_ms=backoff_ms)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink(missing_ok=True)


def atomic_write_json(path: Path, obj: Any, *, ensure_ascii: bool = True, indent: int = 2) -> None:
    text = json.dumps(obj, indent=indent, ensure_ascii=ensure_ascii) + "\n"
    atomic_write_text(path, text, newline_lf=True)
