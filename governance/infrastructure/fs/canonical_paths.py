from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from governance.infrastructure.path_contract import normalize_absolute_path


class CanonicalPathError(RuntimeError):
    pass


@dataclass(frozen=True)
class CanonicalPaths:
    commands_home: Path
    workspaces_home: Path

    def resolve_workspace_path(self, repo_fingerprint: str, relative_path: str) -> Path:
        token = str(repo_fingerprint or "").strip()
        if not token:
            raise CanonicalPathError("repo fingerprint is required")
        return _resolve_relative(self.workspaces_home / token, relative_path, "workspace path")

    def resolve_commands_path(self, relative_path: str) -> Path:
        return _resolve_relative(self.commands_home, relative_path, "commands path")


def _resolve_relative(base: Path, relative_path: str, purpose: str) -> Path:
    rel = Path(str(relative_path or "").strip())
    if not str(rel):
        raise CanonicalPathError(f"{purpose}: empty relative path")
    if rel.is_absolute():
        raise CanonicalPathError(f"{purpose}: absolute paths are forbidden")
    if ".." in rel.parts:
        raise CanonicalPathError(f"{purpose}: parent traversal is forbidden")

    candidate = Path(str(base / rel))
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise CanonicalPathError(f"{purpose}: path escapes canonical base") from exc

    current = base
    for part in rel.parts:
        current = current / part
        if current.is_symlink():
            raise CanonicalPathError(f"{purpose}: symlink escape is forbidden ({current})")

    return candidate


def build_canonical_paths(binding_paths: Mapping[str, object]) -> CanonicalPaths:
    commands_home = normalize_absolute_path(str(binding_paths.get("commandsHome", "")), purpose="paths.commandsHome")
    workspaces_home = normalize_absolute_path(str(binding_paths.get("workspacesHome", "")), purpose="paths.workspacesHome")
    return CanonicalPaths(commands_home=commands_home, workspaces_home=workspaces_home)
