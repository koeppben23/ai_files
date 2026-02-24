from dataclasses import dataclass
from pathlib import Path


def _has_parent_traversal(path: Path) -> bool:
    return any(part == ".." for part in path.parts)


@dataclass(frozen=True)
class CanonicalPath:
    path: Path
    
    def __post_init__(self):
        if not self.path.is_absolute():
            raise ValueError(f"Path must be absolute: {self.path}")
        
        if _has_parent_traversal(self.path):
            raise ValueError(f"Path traversal detected: {self.path}")
    
    def __str__(self) -> str:
        return str(self.path)
    
    def __fspath__(self):
        return str(self.path)
    
    def joinpath(self, *args) -> "CanonicalPath":
        new_path = self.path.joinpath(*args)
        if _has_parent_traversal(new_path):
            raise ValueError(f"Path traversal detected: {new_path}")
        return CanonicalPath(new_path)


def ensure_absolute_no_traversal(path: Path) -> CanonicalPath:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        raise ValueError(f"Path must be absolute: {path}")
    if _has_parent_traversal(candidate):
        raise ValueError(f"Path traversal detected: {path}")
    return CanonicalPath(candidate)


def validate_no_traversal(path: Path, base: Path) -> bool:
    try:
        candidate = ensure_absolute_no_traversal(path).path
        base_path = ensure_absolute_no_traversal(base).path
        candidate.relative_to(base_path)
        return True
    except (ValueError, RuntimeError):
        return False
