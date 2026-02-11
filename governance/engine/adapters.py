"""Host adapter contracts for Wave B engine orchestration.

Adapters normalize host-specific access (Desktop/CLI/CI) into a deterministic
interface that the engine can consume without direct host branching.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
from typing import Literal, Mapping, Protocol


CwdTrustLevel = Literal["trusted", "untrusted"]


@dataclass(frozen=True)
class HostCapabilities:
    """Capability flags that influence deterministic engine behavior."""

    cwd_trust: CwdTrustLevel
    fs_read: bool
    git_available: bool


class HostAdapter(Protocol):
    """Minimal host interface for Wave B orchestration."""

    def capabilities(self) -> HostCapabilities:
        """Return static capability flags for the current host/runtime."""

        ...

    def environment(self) -> Mapping[str, str]:
        """Return host environment variables used by context resolution."""

        ...

    def cwd(self) -> Path:
        """Return current working directory as seen by the host."""

        ...


@dataclass(frozen=True)
class LocalHostAdapter:
    """Default adapter for local CLI execution contexts."""

    cwd_trust: CwdTrustLevel = "trusted"
    fs_read: bool = True
    git_available: bool = True

    def capabilities(self) -> HostCapabilities:
        return HostCapabilities(cwd_trust=self.cwd_trust, fs_read=self.fs_read, git_available=self.git_available)

    def environment(self) -> Mapping[str, str]:
        return os.environ

    def cwd(self) -> Path:
        return Path.cwd().resolve()


@dataclass(frozen=True)
class OpenCodeDesktopAdapter:
    """Desktop host adapter with conservative capability defaults.

    Desktop mode treats cwd as untrusted by default and enables parent git-root
    search in the orchestrator.
    """

    cwd_trust: CwdTrustLevel = "untrusted"
    fs_read: bool = True
    git_available_override: bool | None = None

    def capabilities(self) -> HostCapabilities:
        git_available = self.git_available_override
        if git_available is None:
            disabled = os.getenv("OPENCODE_DISABLE_GIT", "").strip() == "1"
            git_available = (shutil.which("git") is not None) and not disabled
        return HostCapabilities(cwd_trust=self.cwd_trust, fs_read=self.fs_read, git_available=git_available)

    def environment(self) -> Mapping[str, str]:
        return os.environ

    def cwd(self) -> Path:
        return Path.cwd().resolve()
