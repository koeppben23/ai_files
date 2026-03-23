from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional

from governance_runtime.infrastructure.binding_evidence_resolver import BindingEvidence
from governance_runtime.infrastructure.io_actions import ActionOutcome
from governance_runtime.infrastructure.io_atomic_write import atomic_write_json
from governance_runtime.infrastructure.io_verify import verify_pointer
from .repo_identity import RepoIdentity
from .backfill_client import BackfillSummary, run_backfill_subprocess


@dataclass(frozen=True)
class _PathBox:
    path: Path


@dataclass(frozen=True)
class _ConfigLayout:
    pointer_path: _PathBox

    @classmethod
    def from_path(cls, config_root: Path) -> "_ConfigLayout":
        return cls(pointer_path=_PathBox(path=config_root / "SESSION_STATE.json"))


@dataclass(frozen=True)
class _WorkspaceLayout:
    workspace_session_path: _PathBox

    @classmethod
    def from_fingerprint(cls, workspaces_home: Path, fingerprint: str) -> "_WorkspaceLayout":
        return cls(workspace_session_path=_PathBox(path=workspaces_home / fingerprint / "SESSION_STATE.json"))


def _as_path(value: object) -> Path:
    if isinstance(value, Path):
        return value
    candidate = getattr(value, "path", None)
    if isinstance(candidate, Path):
        return candidate
    return Path(str(value))


@dataclass
class BootstrapResult:
    success: bool
    repo_fingerprint: str
    artifacts_committed: bool
    pointer_verified: bool
    persistence_committed: bool
    error: Optional[str] = None
    actions: List[ActionOutcome] = field(default_factory=list)


class BootstrapPersistenceService:
    def __init__(
        self,
        binding: BindingEvidence,
        identity: RepoIdentity,
        write_policy: bool = True,
    ):
        self.binding = binding
        self.identity = identity
        self.write_policy = write_policy
        
        config_root = _as_path(binding.config_root)
        workspaces_home = _as_path(binding.workspaces_home)
        self.config_layout = _ConfigLayout.from_path(config_root)
        self.workspace_layout = _WorkspaceLayout.from_fingerprint(
            workspaces_home,
            identity.fingerprint,
        )
    
    def run(self, dry_run: bool = False) -> BootstrapResult:
        if not self.write_policy and not dry_run:
            return BootstrapResult(
                success=False,
                repo_fingerprint=self.identity.fingerprint,
                artifacts_committed=False,
                pointer_verified=False,
                persistence_committed=False,
                error="Writes not allowed",
            )
        
        backfill_result = self._run_backfill(dry_run)
        if not backfill_result.success and not dry_run:
            return BootstrapResult(
                success=False,
                repo_fingerprint=self.identity.fingerprint,
                artifacts_committed=False,
                pointer_verified=False,
                persistence_committed=False,
                error="Backfill failed",
            )
        
        pointer_result = self._write_pointer(dry_run)
        if not pointer_result.success and not dry_run:
            return BootstrapResult(
                success=False,
                repo_fingerprint=self.identity.fingerprint,
                artifacts_committed=backfill_result.success,
                pointer_verified=False,
                persistence_committed=False,
                error="Pointer write failed",
            )
        
        if not dry_run:
            verified, error = verify_pointer(
                self.config_layout.pointer_path.path,
                self.identity.fingerprint,
            )
            if not verified:
                return BootstrapResult(
                    success=False,
                    repo_fingerprint=self.identity.fingerprint,
                    artifacts_committed=backfill_result.success,
                    pointer_verified=False,
                    persistence_committed=False,
                    error=f"Pointer verification failed: {error}",
                )
        
        state_result = self._write_session_state(
            artifacts_committed=backfill_result.success,
            pointer_verified=True,
            dry_run=dry_run,
        )
        
        return BootstrapResult(
            success=True,
            repo_fingerprint=self.identity.fingerprint,
            artifacts_committed=backfill_result.success,
            pointer_verified=True,
            persistence_committed=state_result.success,
            error=None,
        )
    
    def _run_backfill(self, dry_run: bool) -> BackfillSummary:
        if dry_run:
            return BackfillSummary(
                success=True,
                phase2_ok=True,
                status="ok",
                artifacts={},
            )
        
        return run_backfill_subprocess(
            repo_fingerprint=self.identity.fingerprint,
            config_root=_as_path(self.binding.config_root),
            repo_root=self.identity.root,
            workspaces_home=_as_path(self.binding.workspaces_home),
        )
    
    def _write_pointer(self, dry_run: bool) -> ActionOutcome:
        session_file = self.workspace_layout.workspace_session_path.path
        try:
            rel_path = session_file.relative_to(_as_path(self.binding.config_root))
            rel_value = str(rel_path).replace("\\", "/")
        except ValueError:
            rel_value = f"workspaces/{self.identity.fingerprint}/SESSION_STATE.json"
        pointer_data = {
            "schema": "opencode-session-pointer.v1",
            "activeRepoFingerprint": self.identity.fingerprint,
            "activeSessionStateFile": str(session_file),
            "activeSessionStateRelativePath": rel_value,
        }
        
        return atomic_write_json(
            self.config_layout.pointer_path.path,
            pointer_data,
            dry_run=dry_run,
        )
    
    def _write_session_state(
        self,
        artifacts_committed: bool,
        pointer_verified: bool,
        dry_run: bool,
    ) -> ActionOutcome:
        state_data = {
            "schema": "opencode-session.v1",
            "phase_token": "1.1-Bootstrap",
            "mode": str(getattr(self.binding, "mode", "user")),
            "CommitFlags": {
                "PersistenceCommitted": artifacts_committed and pointer_verified,
                "WorkspaceReadyGateCommitted": artifacts_committed and pointer_verified,
                "WorkspaceArtifactsCommitted": artifacts_committed,
                "PointerVerified": pointer_verified,
            },
            "Scope": {
                "Repository": self.identity.name,
            },
        }
        
        return atomic_write_json(
            self.workspace_layout.workspace_session_path.path,
            state_data,
            dry_run=dry_run,
        )
