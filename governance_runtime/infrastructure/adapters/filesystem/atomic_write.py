from __future__ import annotations

import os
import tempfile
from pathlib import Path

from governance_runtime.domain.models.write_action import WriteAction


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=str(path.parent),
            prefix=path.name + ".",
            suffix=".tmp",
            delete=False,
        ) as tmp:
            tmp.write(content)
            tmp.flush()
            os.fsync(tmp.fileno())
            temp_path = Path(tmp.name)
        os.replace(str(temp_path), str(path))
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink(missing_ok=True)


def atomic_write_action(path: Path, content: str, *, dry_run: bool = False, read_only: bool = False) -> WriteAction:
    if read_only:
        return WriteAction(path=str(path), outcome="skipped_read_only", bytes_written=0)
    if dry_run:
        return WriteAction(path=str(path), outcome="skipped_dry_run", bytes_written=0)
    atomic_write(path, content)
    return WriteAction(path=str(path), outcome="written", bytes_written=len(content.encode("utf-8")))
