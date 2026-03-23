from __future__ import annotations

from pathlib import Path


class InMemoryFS:
    def __init__(self) -> None:
        self._data: dict[str, str] = {}
        self._dirs: set[str] = set()

    def write_text_atomic(self, path: Path, content: str) -> None:
        self._data[str(path)] = content

    def read_text(self, path: Path) -> str:
        return self._data[str(path)]

    def exists(self, path: Path) -> bool:
        return str(path) in self._data

    def write_text(self, path: Path, content: str) -> None:
        self._data[str(path)] = content

    def mkdir_p(self, path: Path) -> None:
        self._dirs.add(str(path))

    def dir_exists(self, path: Path) -> bool:
        """Test-only helper to check if mkdir_p was called for a path."""
        return str(path) in self._dirs
