from __future__ import annotations

from pathlib import Path
from typing import Protocol, Sequence


class GitPort(Protocol):
    """Protocol for Git operations.
    
    Application code should depend on this protocol, not the concrete
    implementation. Infrastructure provides the GitCliClient implementation.
    """

    def resolve_repo_root(self, cwd: Path | None = None) -> Path | None:
        """Resolve the Git repository root (top-level directory)."""
        ...

    def is_inside_work_tree(self, cwd: Path | None = None) -> bool:
        """Check if the given path is inside a Git working tree."""
        ...

    def get_origin_remote(self, cwd: Path | None = None) -> str | None:
        """Get the URL of the 'origin' remote."""
        ...

    def get_config(
        self,
        key: str,
        cwd: Path | None = None,
        scope: str | None = None,
    ) -> str | None:
        """Get a Git configuration value."""
        ...

    def status_porcelain(self, cwd: Path | None = None) -> list[str]:
        """Get git status in porcelain format."""
        ...

    def rev_parse(self, args: Sequence[str], cwd: Path | None = None) -> str | None:
        """Execute git rev-parse with given arguments."""
        ...

    def merge_base(self, left: str, right: str, cwd: Path | None = None) -> str | None:
        """Find the merge base of two commits."""
        ...

    def diff_name_only(
        self,
        left: str,
        right: str | None = None,
        cwd: Path | None = None,
    ) -> list[str]:
        """Get list of files that differ between two commits."""
        ...

    def ls_remote(
        self,
        remote: str,
        ref: str | None = None,
        cwd: Path | None = None,
    ) -> list[str]:
        """List remote references."""
        ...

    def is_safe_directory(self, path: Path | None = None) -> bool:
        """Check if the directory is marked as safe for Git operations."""
        ...

    def get_safe_directories(self, cwd: Path | None = None) -> list[str]:
        """Get list of configured safe directories."""
        ...
