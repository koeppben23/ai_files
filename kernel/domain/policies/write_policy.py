from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WritePolicy:
    writes_allowed: bool
    reason: str


def compute_write_policy(*, force_read_only: bool) -> WritePolicy:
    if force_read_only:
        return WritePolicy(writes_allowed=False, reason="force-read-only")
    return WritePolicy(writes_allowed=True, reason="default-allow")
