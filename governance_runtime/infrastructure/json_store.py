"""Shared JSON I/O utilities for governance runtime.

Provides atomic write, JSONL append, and JSON load for governance
artifacts (session state, events, plan records, etc.).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Mapping


def load_json(path: Path) -> dict[str, object]:
    """Read and parse a JSON file. Raises on any failure."""
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}, got {type(data).__name__}")
    return data


def write_json_atomic(path: Path, payload: Mapping[str, object]) -> None:
    """Atomically write a JSON dict to a file using temp file + os.replace."""
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def append_jsonl(path: Path, event: Mapping[str, object]) -> None:
    """Append a JSON object as a single line to a JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=True, separators=(",", ":")) + "\n")
