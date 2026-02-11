"""Host adapter contracts for Wave B engine orchestration.

Adapters normalize host-specific access (Desktop/CLI/CI) into a deterministic
interface that the engine can consume without direct host branching.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Literal, Mapping, Protocol


CwdTrustLevel = Literal["trusted", "untrusted"]
OperatingMode = Literal["user", "system", "pipeline"]


def _default_config_root() -> Path:
    """Resolve config root using deterministic cross-platform defaults."""

    if os.name == "nt":
        user_profile = os.environ.get("USERPROFILE")
        if user_profile:
            return Path(user_profile) / ".config" / "opencode"
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "opencode"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    return (Path(xdg) if xdg else Path.home() / ".config") / "opencode"


def _path_writable(path: Path) -> bool:
    """Return True when path (or nearest existing parent) is writable."""

    candidate = path if path.exists() else path.parent
    while True:
        if candidate.exists():
            return os.access(candidate, os.W_OK)
        if candidate == candidate.parent:
            return False
        candidate = candidate.parent


def _path_readable(path: Path) -> bool:
    """Return True when path exists and can be read."""

    return path.exists() and os.access(path, os.R_OK)


def _is_ci_env(env: Mapping[str, str]) -> bool:
    """Return True when environment indicates pipeline/system execution."""

    return str(env.get("CI", "")).strip().lower() == "true"


@dataclass(frozen=True)
class HostCapabilities:
    """Capability flags that influence deterministic engine behavior."""

    cwd_trust: CwdTrustLevel
    fs_read_commands_home: bool
    fs_write_config_root: bool
    fs_write_commands_home: bool
    fs_write_workspaces_home: bool
    fs_write_repo_root: bool
    exec_allowed: bool
    git_available: bool

    @property
    def fs_read(self) -> bool:
        """Back-compat alias for previous capability contract."""

        return self.fs_read_commands_home

    def stable_hash(self) -> str:
        """Return deterministic capabilities hash for audit/activation hashing."""

        encoded = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


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

    def default_operating_mode(self) -> OperatingMode:
        """Return adapter default operating mode when no higher signal exists."""

        ...


@dataclass(frozen=True)
class LocalHostAdapter:
    """Default adapter for local CLI execution contexts."""

    cwd_trust: CwdTrustLevel = "trusted"
    operating_mode: OperatingMode = "user"

    def capabilities(self) -> HostCapabilities:
        env = self.environment()
        config_root = Path(env.get("OPENCODE_CONFIG_ROOT", "")).expanduser().resolve() if env.get("OPENCODE_CONFIG_ROOT") else _default_config_root().resolve()
        commands_home = config_root / "commands"
        workspaces_home = config_root / "workspaces"
        repo_root = Path(env.get("OPENCODE_REPO_ROOT", str(self.cwd()))).expanduser().resolve()
        exec_allowed = os.access(sys.executable, os.X_OK)
        git_disabled = str(env.get("OPENCODE_DISABLE_GIT", "")).strip() == "1"
        git_available = (shutil.which("git") is not None) and not git_disabled
        return HostCapabilities(
            cwd_trust=self.cwd_trust,
            fs_read_commands_home=_path_readable(commands_home),
            fs_write_config_root=_path_writable(config_root),
            fs_write_commands_home=_path_writable(commands_home),
            fs_write_workspaces_home=_path_writable(workspaces_home),
            fs_write_repo_root=_path_writable(repo_root),
            exec_allowed=exec_allowed,
            git_available=git_available,
        )

    def environment(self) -> Mapping[str, str]:
        return os.environ

    def cwd(self) -> Path:
        return Path.cwd().resolve()

    def default_operating_mode(self) -> OperatingMode:
        return self.operating_mode


@dataclass(frozen=True)
class OpenCodeDesktopAdapter:
    """Desktop host adapter with conservative capability defaults.

    Desktop mode treats cwd as untrusted by default and enables parent git-root
    search in the orchestrator.
    """

    cwd_trust: CwdTrustLevel = "untrusted"
    operating_mode: OperatingMode = "user"
    git_available_override: bool | None = None

    def capabilities(self) -> HostCapabilities:
        env = self.environment()
        config_root = Path(env.get("OPENCODE_CONFIG_ROOT", "")).expanduser().resolve() if env.get("OPENCODE_CONFIG_ROOT") else _default_config_root().resolve()
        commands_home = config_root / "commands"
        workspaces_home = config_root / "workspaces"
        repo_root = Path(env.get("OPENCODE_REPO_ROOT", str(self.cwd()))).expanduser().resolve()
        disabled = str(env.get("OPENCODE_DISABLE_GIT", "")).strip() == "1"
        git_available = self.git_available_override
        if git_available is None:
            git_available = (shutil.which("git") is not None) and not disabled
        return HostCapabilities(
            cwd_trust=self.cwd_trust,
            fs_read_commands_home=_path_readable(commands_home),
            fs_write_config_root=_path_writable(config_root),
            fs_write_commands_home=_path_writable(commands_home),
            fs_write_workspaces_home=_path_writable(workspaces_home),
            fs_write_repo_root=_path_writable(repo_root),
            exec_allowed=os.access(sys.executable, os.X_OK),
            git_available=bool(git_available),
        )

    def environment(self) -> Mapping[str, str]:
        return os.environ

    def cwd(self) -> Path:
        return Path.cwd().resolve()

    def default_operating_mode(self) -> OperatingMode:
        if _is_ci_env(self.environment()):
            return "pipeline"
        return self.operating_mode
