from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from governance.infrastructure.fs_atomic import atomic_write_text


def write_jsonl_event(path: Path, event: dict[str, Any], *, append: bool) -> None:
    line = json.dumps(event, ensure_ascii=True, separators=(",", ":")) + "\n"
    if append and path.exists():
        existing = path.read_text(encoding="utf-8")
        atomic_write_text(path, existing + line, newline_lf=True)
        return
    atomic_write_text(path, line, newline_lf=True)
