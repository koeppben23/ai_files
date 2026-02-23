from __future__ import annotations

from dataclasses import dataclass, field

from kernel.domain.errors.events import ErrorEvent


@dataclass(frozen=True)
class BootstrapResult:
    ok: bool
    gate_code: str
    write_actions: dict[str, str] = field(default_factory=dict)
    error_events: tuple[ErrorEvent, ...] = field(default_factory=tuple)
