from __future__ import annotations

from pathlib import Path


class InMemoryFS:
    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    def write_text_atomic(self, path: Path, content: str) -> None:
        self._data[str(path)] = content

    def read_text(self, path: Path) -> str:
        return self._data[str(path)]

    def exists(self, path: Path) -> bool:
        return str(path) in self._data
