"""Host adapter contracts for Wave B engine orchestration.

Adapters normalize host-specific access (Desktop/CLI/CI) into a deterministic
interface that the engine can consume without direct host branching.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Literal, Mapping, Protocol

from governance.engine.canonical_json import canonical_json_hash
from governance.engine.path_contract import (
    PathContractError,
    canonical_config_root,
    normalize_absolute_path,
)


CwdTrustLevel = Literal["trusted", "untrusted"]
OperatingMode = Literal["user", "system", "pipeline", "agents_strict"]


def _default_config_root() -> Path:
    """Resolve canonical config root under user home on every OS."""

    return canonical_config_root()


def _resolve_env_path(env: Mapping[str, str], key: str) -> Path | None:
    """Resolve an environment path deterministically.

    Fail-closed on relative paths to avoid CWD-dependent resolution.
    """
    raw = str(env.get(key, "")).strip()
    if not raw:
        return None
    try:
        return normalize_absolute_path(raw, purpose=f"env:{key}")
    except PathContractError:
        return None


def _candidate_config_roots(env: Mapping[str, str]) -> list[Path]:
    """Return deterministic config-root candidates for binding discovery."""

    _ = env
    candidates: list[Path] = [_default_config_root().resolve()]

    seen: set[Path] = set()
    ordered: list[Path] = []
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        ordered.append(candidate)
    return ordered


def _allow_cwd_binding_discovery(env: Mapping[str, str]) -> bool:
    """Return True only when explicit dev override enables CWD binding search."""

    return str(env.get("OPENCODE_ALLOW_CWD_BINDINGS", "")).strip() == "1"


def _discover_binding_file(config_root: Path, env: Mapping[str, str]) -> Path | None:
    """Discover installer-owned governance.paths.json deterministically."""

    candidates: list[Path] = [config_root / "commands" / "governance.paths.json"]
    for root in _candidate_config_roots(env):
        candidates.append(root / "commands" / "governance.paths.json")
    if _allow_cwd_binding_discovery(env):
        cwd = Path.cwd().resolve()
        for parent in (cwd, *cwd.parents):
            candidates.append(parent / "commands" / "governance.paths.json")

    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if resolved.exists():
            return resolved
    return None


def _resolve_bound_paths(config_root: Path, env: Mapping[str, str]) -> tuple[Path, Path, bool]:
    """Resolve commands/workspaces homes with governance.paths.json precedence."""

    commands_home = config_root / "commands"
    workspaces_home = config_root / "workspaces"
    binding_file = _discover_binding_file(config_root, env)
    if binding_file is None:
        return commands_home, workspaces_home, False

    try:
        payload = json.loads(binding_file.read_text(encoding="utf-8"))
    except Exception:
        return commands_home, workspaces_home, False

    if not isinstance(payload, dict):
        return commands_home, workspaces_home, False
    paths = payload.get("paths")
    if not isinstance(paths, dict):
        return commands_home, workspaces_home, False

    commands_raw = paths.get("commandsHome")
    workspaces_raw = paths.get("workspacesHome")
    if not isinstance(commands_raw, str) or not commands_raw.strip():
        return commands_home, workspaces_home, False
    if not isinstance(workspaces_raw, str) or not workspaces_raw.strip():
        return commands_home, workspaces_home, False
    try:
        normalized_commands = normalize_absolute_path(commands_raw, purpose="paths.commandsHome")
        normalized_workspaces = normalize_absolute_path(workspaces_raw, purpose="paths.workspacesHome")
    except PathContractError:
        return commands_home, workspaces_home, False
    return normalized_commands, normalized_workspaces, True


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

    val = str(env.get("CI", "")).strip().lower()
    if not val or val in {"0", "false", "no", "off"}:
        return False
    # Fail-closed: any non-false CI value means pipeline/system context.
    return True


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
    def capabilities_hash(self) -> str:
        """Deterministic short hash for capability fingerprint (stable across environments).

        Returns a 16-hex-character representation suitable for activation fingerprints.
        This mirrors the historical stable_hash output but exposes a stable alias for tests.
        """
        return self.stable_hash()

    @property
    def fs_read(self) -> bool:
        """Back-compat alias for previous capability contract."""

        return self.fs_read_commands_home

    def stable_hash(self) -> str:
        """Return deterministic capabilities hash for audit/activation hashing."""

        return self.stable_hash_full()[:16]

    def stable_hash_full(self) -> str:
        """Return full deterministic capabilities hash (preferred for activation)."""

        return canonical_json_hash(asdict(self))


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
        config_root = _default_config_root().resolve()
        commands_home, workspaces_home, binding_ok = _resolve_bound_paths(config_root, env)
        # Fail-closed: ignore relative OPENCODE_REPO_ROOT to avoid CWD-dependent resolution
        repo_root = _resolve_env_path(env, "OPENCODE_REPO_ROOT") or self.cwd()
        exec_allowed = os.access(sys.executable, os.X_OK)
        git_disabled = str(env.get("OPENCODE_DISABLE_GIT", "")).strip() == "1"
        git_available = (shutil.which("git") is not None) and not git_disabled
        return HostCapabilities(
            cwd_trust=self.cwd_trust,
            fs_read_commands_home=_path_readable(commands_home) if binding_ok else False,
            fs_write_config_root=_path_writable(config_root),
            fs_write_commands_home=_path_writable(commands_home) if binding_ok else False,
            fs_write_workspaces_home=_path_writable(workspaces_home) if binding_ok else False,
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
        config_root = _default_config_root().resolve()
        commands_home, workspaces_home, binding_ok = _resolve_bound_paths(config_root, env)
        # Fail-closed: ignore relative OPENCODE_REPO_ROOT to avoid CWD-dependent resolution
        repo_root = _resolve_env_path(env, "OPENCODE_REPO_ROOT") or self.cwd()
        disabled = str(env.get("OPENCODE_DISABLE_GIT", "")).strip() == "1"
        git_available = self.git_available_override
        if git_available is None:
            git_available = (shutil.which("git") is not None) and not disabled
        return HostCapabilities(
            cwd_trust=self.cwd_trust,
            fs_read_commands_home=_path_readable(commands_home) if binding_ok else False,
            fs_write_config_root=_path_writable(config_root),
            fs_write_commands_home=_path_writable(commands_home) if binding_ok else False,
            fs_write_workspaces_home=_path_writable(workspaces_home) if binding_ok else False,
            fs_write_repo_root=_path_writable(repo_root),
            exec_allowed=os.access(sys.executable, os.X_OK),
            git_available=bool(git_available),
        )

    def environment(self) -> Mapping[str, str]:
        return os.environ

    def cwd(self) -> Path:
        return Path.cwd().resolve()

    def default_operating_mode(self) -> OperatingMode:
        # CI has deterministic precedence over host defaults.
        if _is_ci_env(self.environment()):
            return "pipeline"
        return self.operating_mode
