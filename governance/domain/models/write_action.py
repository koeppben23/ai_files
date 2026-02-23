from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WriteAction:
    path: str
    outcome: str
    bytes_written: int


def is_written(action: WriteAction) -> bool:
    return action.outcome in {"written", "overwritten", "appended"}
