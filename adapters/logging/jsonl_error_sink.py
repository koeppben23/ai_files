from __future__ import annotations

import json
from pathlib import Path

from adapters.filesystem.atomic_write import atomic_write
from kernel.domain.errors.events import ErrorEvent


def write_error(path: Path, event: ErrorEvent) -> None:
    payload = json.dumps(event.__dict__, ensure_ascii=True) + "\n"
    atomic_write(path, payload)
