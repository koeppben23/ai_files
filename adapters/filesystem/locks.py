from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LockToken:
    lock_id: str
