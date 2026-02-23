from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class CanonicalPath:
    path: Path
    
    def __post_init__(self):
        if not self.path.is_absolute():
            raise ValueError(f"Path must be absolute: {self.path}")
        
        path_str = str(self.path)
        if ".." in path_str:
            raise ValueError(f"Path traversal detected: {self.path}")
    
    def __str__(self) -> str:
        return str(self.path)
    
    def __fspath__(self):
        return str(self.path)
    
    def joinpath(self, *args) -> "CanonicalPath":
        new_path = self.path.joinpath(*args)
        return CanonicalPath(new_path.resolve())


def ensure_absolute_no_traversal(path: Path) -> CanonicalPath:
    resolved = path.resolve()
    return CanonicalPath(resolved)


def validate_no_traversal(path: Path, base: Path) -> bool:
    try:
        resolved = path.resolve()
        base_resolved = base.resolve()
        return str(resolved).startswith(str(base_resolved))
    except (OSError, ValueError):
        return False
