from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WriteAction:
    path: str
    outcome: str
    bytes_written: int


def is_written(action: WriteAction) -> bool:
    return action.outcome in {"written", "overwritten", "appended"}


def to_file_status(action: WriteAction) -> str:
    if action.outcome in {"written", "overwritten", "appended"}:
        return "written"
    if action.outcome in {"kept", "normalized"}:
        return "unchanged"
    if action.outcome in {"skipped_read_only", "blocked-read-only"}:
        return "blocked-read-only"
    if action.outcome == "skipped_dry_run":
        return "write-requested"
    if action.outcome in {"error", "failed"}:
        return "failed"
    return "unknown"
