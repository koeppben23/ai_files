from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WritePolicy:
    writes_allowed: bool
    reason: str
    mode: str


def normalize_mode(raw_mode: str) -> str:
    token = str(raw_mode or "").strip().lower()
    if token in {"user", "pipeline", "agents_strict"}:
        return token
    return "user"


def compute_write_policy(*, force_read_only: bool, mode: str = "user") -> WritePolicy:
    normalized_mode = normalize_mode(mode)
    if force_read_only:
        return WritePolicy(writes_allowed=False, reason="force-read-only", mode=normalized_mode)
    return WritePolicy(
        writes_allowed=True,
        reason=f"explicit-{normalized_mode}-mode-allow",
        mode=normalized_mode,
    )
