from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from governance.application.ports.filesystem import FileSystemPort
from governance.application.ports.logger import ErrorLoggerPort
from governance.application.ports.process_runner import ProcessRunnerPort
from governance.domain.models.binding import Binding
from governance.domain.models.layouts import WorkspaceLayout
from governance.domain.models.repo_identity import RepoIdentity
from governance.domain.policies.write_policy import compute_write_policy

from governance.domain.errors.events import ErrorEvent


@dataclass(frozen=True)
class BootstrapResult:
    ok: bool
    gate_code: str
    write_actions: dict[str, str] = field(default_factory=dict)
    error_events: tuple[ErrorEvent, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class BootstrapInput:
    repo_identity: RepoIdentity
    binding: Binding
    layout: WorkspaceLayout
    required_artifacts: tuple[str, ...]
    force_read_only: bool = False


class BootstrapPersistenceService:
    def __init__(
        self,
        *,
        fs: FileSystemPort,
        runner: ProcessRunnerPort,
        logger: ErrorLoggerPort,
    ) -> None:
        self._fs = fs
        self._runner = runner
        self._logger = logger

    def run(self, payload: BootstrapInput) -> BootstrapResult:
        write_actions: dict[str, str] = {}
        errors: list[ErrorEvent] = []

        policy = compute_write_policy(force_read_only=payload.force_read_only)
        if not policy.writes_allowed:
            event = ErrorEvent(
                code="PERSISTENCE_READ_ONLY",
                severity="error",
                message="Bootstrap blocked by read-only policy.",
                expected="writes allowed",
                observed={"reason": policy.reason},
            )
            self._logger.write(event)
            return BootstrapResult(ok=False, gate_code=event.code, write_actions=write_actions, error_events=(event,))

        initial_state = {
            "SESSION_STATE": {
                "RepoFingerprint": payload.repo_identity.fingerprint,
                "CommitFlags": {
                    "PersistenceCommitted": False,
                    "WorkspaceReadyGateCommitted": False,
                    "WorkspaceArtifactsCommitted": False,
                },
            }
        }
        session_state_file = Path(payload.layout.session_state_file)
        identity_map_file = Path(payload.layout.identity_map_file)
        pointer_file = Path(payload.layout.pointer_file)

        self._fs.write_text_atomic(session_state_file, _canonical_json(initial_state))
        write_actions["session_state_initial"] = "written"

        identity_map = {
            "repoFingerprint": payload.repo_identity.fingerprint,
            "repoRoot": payload.repo_identity.repo_root,
            "repoName": payload.repo_identity.repo_name,
            "source": payload.repo_identity.source,
        }
        self._fs.write_text_atomic(identity_map_file, _canonical_json(identity_map))
        write_actions["identity_map"] = "written"

        run = self._runner.run([payload.binding.python_command, "diagnostics/persist_workspace_artifacts.py"])
        if run.returncode != 0:
            event = ErrorEvent(
                code="BACKFILL_NON_ZERO_EXIT",
                severity="error",
                message="Artifact backfill failed.",
                expected="return code 0",
                observed={"returncode": run.returncode, "stderr": run.stderr[:240]},
            )
            self._logger.write(event)
            errors.append(event)
            return BootstrapResult(ok=False, gate_code=event.code, write_actions=write_actions, error_events=tuple(errors))
        write_actions["artifact_backfill"] = "completed"

        missing = [path for path in payload.required_artifacts if not self._fs.exists(Path(path))]
        if missing:
            event = ErrorEvent(
                code="PHASE2_ARTIFACTS_MISSING",
                severity="error",
                message="Required artifacts missing after backfill.",
                expected="all required artifacts exist",
                observed={"missing": missing},
            )
            self._logger.write(event)
            errors.append(event)
            return BootstrapResult(ok=False, gate_code=event.code, write_actions=write_actions, error_events=tuple(errors))
        write_actions["artifact_verify"] = "verified"

        pointer_payload = {
            "schema": "opencode-session-pointer.v1",
            "activeRepoFingerprint": payload.repo_identity.fingerprint,
            "activeSessionStateFile": payload.layout.session_state_file,
        }
        pointer_text = _canonical_json(pointer_payload)
        self._fs.write_text_atomic(pointer_file, pointer_text)
        write_actions["pointer"] = "written"

        if self._fs.read_text(pointer_file) != pointer_text:
            event = ErrorEvent(
                code="POINTER_VERIFY_FAILED",
                severity="error",
                message="Pointer verification failed after write.",
                expected="pointer read-back equals write payload",
                observed={"pointerFile": str(pointer_file)},
            )
            self._logger.write(event)
            errors.append(event)
            return BootstrapResult(ok=False, gate_code=event.code, write_actions=write_actions, error_events=tuple(errors))
        write_actions["pointer_verify"] = "verified"

        final_state = {
            "SESSION_STATE": {
                "RepoFingerprint": payload.repo_identity.fingerprint,
                "CommitFlags": {
                    "PersistenceCommitted": True,
                    "WorkspaceReadyGateCommitted": True,
                    "WorkspaceArtifactsCommitted": True,
                },
            }
        }
        self._fs.write_text_atomic(session_state_file, _canonical_json(final_state))
        write_actions["session_state_final"] = "written"
        return BootstrapResult(ok=True, gate_code="OK", write_actions=write_actions, error_events=tuple(errors))


def _canonical_json(data: object) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"
