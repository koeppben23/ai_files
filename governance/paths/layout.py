from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .canonical import CanonicalPath, ensure_absolute_no_traversal


@dataclass(frozen=True)
class WorkspaceLayout:
    root: CanonicalPath
    fingerprint: str
    
    @property
    def workspace_session_path(self) -> CanonicalPath:
        return self.root.joinpath("SESSION_STATE.json")
    
    @property
    def identity_map_path(self) -> CanonicalPath:
        return self.root.joinpath("identity-map.json")
    
    @property
    def repo_cache_path(self) -> CanonicalPath:
        return self.root.joinpath("repo-cache.yaml")
    
    @property
    def repo_map_digest_path(self) -> CanonicalPath:
        return self.root.joinpath("repo-map-digest.md")
    
    @property
    def workspace_memory_path(self) -> CanonicalPath:
        return self.root.joinpath("workspace-memory.yaml")
    
    @property
    def decision_pack_path(self) -> CanonicalPath:
        return self.root.joinpath("decision-pack.md")
    
    @property
    def logs_path(self) -> CanonicalPath:
        return self.root.joinpath("logs")
    
    @property
    def error_log_path(self) -> CanonicalPath:
        return self.logs_path.joinpath("error.log.jsonl")
    
    @classmethod
    def from_fingerprint(cls, workspaces_home: Path, fingerprint: str) -> "WorkspaceLayout":
        workspace_root = workspaces_home / fingerprint
        canonical_root = ensure_absolute_no_traversal(workspace_root)
        return cls(root=canonical_root, fingerprint=fingerprint)


@dataclass(frozen=True)
class ConfigLayout:
    config_root: CanonicalPath
    
    @property
    def pointer_path(self) -> CanonicalPath:
        return self.config_root.joinpath("SESSION_STATE.json")
    
    @property
    def commands_home(self) -> CanonicalPath:
        return self.config_root.joinpath("commands")
    
    @property
    def workspaces_home(self) -> CanonicalPath:
        return self.config_root.joinpath("workspaces")
    
    @classmethod
    def from_path(cls, config_root: Path) -> "ConfigLayout":
        canonical = ensure_absolute_no_traversal(config_root)
        return cls(config_root=canonical)
