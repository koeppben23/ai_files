from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum


class FileStatus(str, Enum):
    CREATED = "created"
    OVERWRITTEN = "overwritten"
    UNCHANGED = "unchanged"
    BLOCKED_READ_ONLY = "blocked-read-only"
    WRITE_REQUESTED = "write-requested"


@dataclass
class LoadedRulebooks:
    core: List[str] = field(default_factory=list)
    domain: List[str] = field(default_factory=list)
    local: List[str] = field(default_factory=list)


@dataclass
class CommitFlags:
    PersistenceCommitted: bool = False
    WorkspaceReadyGateCommitted: bool = False
    WorkspaceArtifactsCommitted: bool = False
    PointerVerified: bool = False


@dataclass
class SessionState:
    schema: str = "opencode-session.v1"
    phase_token: str = "0-None"
    profile: Optional[str] = None
    mode: str = "user"
    Scope: Dict[str, Any] = field(default_factory=dict)
    LoadedRulebooks: "LoadedRulebooks" = field(default_factory=LoadedRulebooks)
    CommitFlags: "CommitFlags" = field(default_factory=CommitFlags)
    Files: Dict[str, FileStatus] = field(default_factory=dict)
    IdentityMap: Dict[str, str] = field(default_factory=dict)
    Metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "schema": self.schema,
            "phase_token": self.phase_token,
            "profile": self.profile,
            "mode": self.mode,
            "Scope": self.Scope,
            "LoadedRulebooks": {
                "core": self.LoadedRulebooks.core,
                "domain": self.LoadedRulebooks.domain,
                "local": self.LoadedRulebooks.local,
            },
            "CommitFlags": {
                "PersistenceCommitted": self.CommitFlags.PersistenceCommitted,
                "WorkspaceReadyGateCommitted": self.CommitFlags.WorkspaceReadyGateCommitted,
                "WorkspaceArtifactsCommitted": self.CommitFlags.WorkspaceArtifactsCommitted,
                "PointerVerified": self.CommitFlags.PointerVerified,
            },
            "Files": {k: v.value for k, v in self.Files.items()},
            "IdentityMap": self.IdentityMap,
            "Metadata": self.Metadata,
        }
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionState":
        if not isinstance(data, dict):
            return cls()
        
        loaded_rulebooks_data = data.get("LoadedRulebooks", {})
        loaded_rulebooks = LoadedRulebooks(
            core=loaded_rulebooks_data.get("core", []),
            domain=loaded_rulebooks_data.get("domain", []),
            local=loaded_rulebooks_data.get("local", []),
        )
        
        commit_flags_data = data.get("CommitFlags", {})
        commit_flags = CommitFlags(
            PersistenceCommitted=commit_flags_data.get("PersistenceCommitted", False),
            WorkspaceReadyGateCommitted=commit_flags_data.get("WorkspaceReadyGateCommitted", False),
            WorkspaceArtifactsCommitted=commit_flags_data.get("WorkspaceArtifactsCommitted", False),
            PointerVerified=commit_flags_data.get("PointerVerified", False),
        )
        
        files_data = data.get("Files", {})
        files = {}
        for k, v in files_data.items():
            try:
                files[k] = FileStatus(v)
            except ValueError:
                files[k] = FileStatus.UNCHANGED
        
        return cls(
            schema=data.get("schema", "opencode-session.v1"),
            phase_token=data.get("phase_token", "0-None"),
            profile=data.get("profile"),
            mode=data.get("mode", "user"),
            Scope=data.get("Scope", {}),
            LoadedRulebooks=loaded_rulebooks,
            CommitFlags=commit_flags,
            Files=files,
            IdentityMap=data.get("IdentityMap", {}),
            Metadata=data.get("Metadata", {}),
        )
