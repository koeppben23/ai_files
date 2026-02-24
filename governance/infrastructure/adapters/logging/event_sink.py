from __future__ import annotations

import json
import os
from pathlib import Path
import time
from typing import Any

from governance.infrastructure.fs_atomic import atomic_write_text


def _append_line_with_lock(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_attempts = 10
    lock_backoff_sec = 0.03
    lock_length = 0x7FFFFFFF
    handle = None
    try:
        for attempt in range(lock_attempts):
            try:
                handle = path.open("a+", encoding="utf-8", newline="\n")
                break
            except OSError:
                if attempt == lock_attempts - 1:
                    raise
                time.sleep(lock_backoff_sec)

        if handle is None:
            raise OSError("unable to open jsonl target for append")

        for attempt in range(lock_attempts):
            try:
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, lock_length)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                break
            except OSError:
                if attempt == lock_attempts - 1:
                    raise
                time.sleep(lock_backoff_sec)

        for attempt in range(lock_attempts):
            try:
                handle.seek(0, os.SEEK_END)
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())
                break
            except OSError:
                if attempt == lock_attempts - 1:
                    raise
                time.sleep(lock_backoff_sec)
    finally:
        if handle is not None:
            try:
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, lock_length)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
            handle.close()


def write_jsonl_event(path: Path, event: dict[str, Any], *, append: bool) -> None:
    line = json.dumps(event, ensure_ascii=True, separators=(",", ":")) + "\n"
    if append:
        _append_line_with_lock(path, line)
        return
    atomic_write_text(path, line, newline_lf=True)
