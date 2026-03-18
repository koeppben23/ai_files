from __future__ import annotations

import json
from pathlib import Path

from governance_runtime.domain.errors.events import ErrorEvent
from governance.infrastructure.adapters.filesystem.atomic_write import atomic_write


def write_error(path: Path, event: ErrorEvent) -> None:
    payload = json.dumps(event.__dict__, ensure_ascii=True) + "\n"
    atomic_write(path, payload)
