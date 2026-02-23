from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RulebookRef:
    identifier: str
    sha256: str
    anchors_version: str
    source_kind: str


@dataclass(frozen=True)
class RulebookSet:
    core: RulebookRef | None = None
    master: RulebookRef | None = None
    profile: RulebookRef | None = None
    addons: tuple[RulebookRef, ...] = field(default_factory=tuple)
