"""Per-workspace lock helpers for deterministic persistence operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
import uuid

try:
    from governance.infrastructure.fs_atomic import atomic_write_text
except Exception:
    def atomic_write_text(path: Path, text: str, newline_lf: bool = True, attempts: int = 5, backoff_ms: int = 50) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = text.replace("\r\n", "\n") if newline_lf else text
        with path.open("w", encoding="utf-8", newline="\n" if newline_lf else None) as handle:
            handle.write(payload)


@dataclass(frozen=True)
class WorkspaceLock:
    lock_dir: Path
    lock_id: str

    def release(self) -> None:
        owner = self.lock_dir / "owner.json"
        if owner.exists():
            owner.unlink(missing_ok=True)
        if self.lock_dir.exists():
            self.lock_dir.rmdir()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def acquire_workspace_lock(
    *,
    workspaces_home: Path,
    repo_fingerprint: str,
    ttl_seconds: int = 120,
    timeout_seconds: int = 10,
    poll_interval_seconds: float = 0.1,
) -> WorkspaceLock:
    lock_dir = workspaces_home / repo_fingerprint / ".lock"
    lock_dir.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()

    while True:
        try:
            lock_dir.mkdir(parents=False, exist_ok=False)
            lock_id = uuid.uuid4().hex
            payload = {
                "lock_id": lock_id,
                "pid": os.getpid(),
                "acquired_at": _utc_now().isoformat(timespec="seconds"),
            }
            atomic_write_text(lock_dir / "owner.json", json.dumps(payload, ensure_ascii=True) + "\n", newline_lf=True)
            return WorkspaceLock(lock_dir=lock_dir, lock_id=lock_id)
        except FileExistsError:
            owner = lock_dir / "owner.json"
            stale = False
            if owner.exists():
                try:
                    payload = json.loads(owner.read_text(encoding="utf-8"))
                    acquired_at_raw = payload.get("acquired_at")
                    if isinstance(acquired_at_raw, str) and acquired_at_raw.strip():
                        acquired = datetime.fromisoformat(acquired_at_raw.replace("Z", "+00:00"))
                        if acquired.tzinfo is None:
                            acquired = acquired.replace(tzinfo=timezone.utc)
                        stale = (_utc_now() - acquired).total_seconds() > ttl_seconds
                except Exception:
                    stale = True
            else:
                stale = True

            if stale:
                try:
                    if owner.exists():
                        owner.unlink(missing_ok=True)
                    lock_dir.rmdir()
                except OSError:
                    pass

            if (time.monotonic() - started) >= timeout_seconds:
                raise TimeoutError("workspace lock timeout")
            time.sleep(poll_interval_seconds)
