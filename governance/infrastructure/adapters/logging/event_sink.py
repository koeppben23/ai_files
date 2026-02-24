from __future__ import annotations

import json
import os
from pathlib import Path
import time
from typing import Any

from governance.infrastructure.fs_atomic import atomic_write_text


def _append_line_with_lock(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_attempts = 8
    lock_backoff_sec = 0.02
    with path.open("a+", encoding="utf-8", newline="\n") as handle:
        for attempt in range(lock_attempts):
            try:
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                break
            except OSError:
                if attempt == lock_attempts - 1:
                    raise
                time.sleep(lock_backoff_sec)

        try:
            handle.seek(0, os.SEEK_END)
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def write_jsonl_event(path: Path, event: dict[str, Any], *, append: bool) -> None:
    line = json.dumps(event, ensure_ascii=True, separators=(",", ":")) + "\n"
    if append:
        _append_line_with_lock(path, line)
        return
    atomic_write_text(path, line, newline_lf=True)
