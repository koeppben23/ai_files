from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from governance.engine.lifecycle import rollback_engine_activation, stage_engine_activation


@dataclass(frozen=True)
class LifecycleState:
    payload: dict[str, Any]


class EngineLifecycleRepository:
    def __init__(self, paths_file: Path):
        self.paths_file = paths_file

    def stage_activation(self, *, engine_version: str, engine_sha256: str, ruleset_hash: str, now_utc: datetime | None = None) -> LifecycleState:
        payload = stage_engine_activation(
            paths_file=self.paths_file,
            engine_version=engine_version,
            engine_sha256=engine_sha256,
            ruleset_hash=ruleset_hash,
            now_utc=now_utc,
        )
        return LifecycleState(payload=payload)

    def rollback(self, *, trigger: str, now_utc: datetime | None = None) -> LifecycleState:
        payload = rollback_engine_activation(paths_file=self.paths_file, trigger=trigger, now_utc=now_utc)
        return LifecycleState(payload=payload)
