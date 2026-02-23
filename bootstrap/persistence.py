from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import json

from governance.paths.canonical import CanonicalPath, ensure_absolute_no_traversal
from governance.paths.layout import WorkspaceLayout, ConfigLayout
from governance.paths.binding import BindingEvidence
from diagnostics.io.actions import ActionOutcome
from diagnostics.io.atomic_write import atomic_write_json
from diagnostics.io.fs_verify import verify_pointer, verify_artifacts
from diagnostics.errors.global_handler import emit_gate_failure
from .repo_identity import RepoIdentity
from .backfill_client import BackfillSummary, run_backfill_subprocess


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
        
        self.config_layout = ConfigLayout.from_path(binding.config_root.path)
        self.workspace_layout = WorkspaceLayout.from_fingerprint(
            binding.workspaces_home.path,
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
            config_root=self.binding.config_root.path,
            repo_root=self.identity.root,
            workspaces_home=self.binding.workspaces_home.path,
        )
    
    def _write_pointer(self, dry_run: bool) -> ActionOutcome:
        pointer_data = {
            "schema": "opencode-session-pointer.v1",
            "activeRepoFingerprint": self.identity.fingerprint,
            "workspaceSession": str(self.workspace_layout.workspace_session_path),
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
            "mode": self.binding.mode,
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
