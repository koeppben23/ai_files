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


ACTIVATION_INTENT_FILE = "governance.activation_intent.json"


def _default_activation_intent() -> dict[str, object]:
    return {
        "schema": "opencode-activation-intent.v1",
        "default_scope": "governance-pipeline-only",
        "allowed_actions": {
            "read_only": True,
            "write_allowed_in_user_mode": True,
        },
        "default_question_policy": {
            "no_questions_before_phase4": True,
            "blocked_when_no_safe_default": True,
        },
        "single_dev_mode": True,
    }


def _is_valid_activation_intent(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("schema") != "opencode-activation-intent.v1":
        return False

    default_scope = payload.get("default_scope")
    if not isinstance(default_scope, str) or not default_scope.strip():
        return False

    allowed_actions = payload.get("allowed_actions")
    if not isinstance(allowed_actions, dict):
        return False
    read_only = allowed_actions.get("read_only")
    write_allowed = allowed_actions.get("write_allowed_in_user_mode")
    if not isinstance(read_only, bool) or not isinstance(write_allowed, bool):
        return False

    question_policy = payload.get("default_question_policy")
    if not isinstance(question_policy, dict):
        return False
    no_questions_before_phase4 = question_policy.get("no_questions_before_phase4")
    blocked_when_no_safe_default = question_policy.get("blocked_when_no_safe_default")
    if not isinstance(no_questions_before_phase4, bool) or not isinstance(blocked_when_no_safe_default, bool):
        return False

    single_dev_mode = payload.get("single_dev_mode")
    if not isinstance(single_dev_mode, bool):
        return False
    return True


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
    skip_artifact_backfill: bool = False
    backfill_command: tuple[str, ...] = field(default_factory=tuple)
    effective_mode: str = "user"
    write_policy_reasons: tuple[str, ...] = field(default_factory=tuple)
    no_commit: bool = False


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
        config_root = Path(payload.binding.config_root)
        repo_root = Path(payload.repo_identity.repo_root)
        pointer_file = Path(payload.layout.pointer_file)
        if _is_within(config_root, repo_root):
            event = ErrorEvent(
                code="CONFIG_ROOT_INSIDE_REPO",
                severity="error",
                message="Config root resolves inside repository root.",
                expected="configRoot outside repoRoot",
                observed={"configRoot": str(config_root), "repoRoot": str(repo_root)},
            )
            self._logger.write(event)
            return BootstrapResult(ok=False, gate_code=event.code, write_actions=write_actions, error_events=(event,))
        if _is_within(pointer_file, repo_root):
            event = ErrorEvent(
                code="POINTER_PATH_INSIDE_REPO",
                severity="error",
                message="Pointer path resolves inside repository root.",
                expected="pointer path outside repoRoot",
                observed={"pointerFile": str(pointer_file), "repoRoot": str(repo_root)},
            )
            self._logger.write(event)
            return BootstrapResult(ok=False, gate_code=event.code, write_actions=write_actions, error_events=(event,))
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

        activation_intent_path = config_root / ACTIVATION_INTENT_FILE
        activation_intent_valid = False
        if self._fs.exists(activation_intent_path):
            try:
                activation_intent = json.loads(self._fs.read_text(activation_intent_path))
            except Exception:
                activation_intent = None
            if _is_valid_activation_intent(activation_intent):
                activation_intent_valid = True
                write_actions["activation_intent"] = "verified"
            else:
                event = ErrorEvent(
                    code="ACTIVATION_INTENT_INVALID",
                    severity="error",
                    message="Activation intent file exists but is invalid.",
                    expected="valid opencode-activation-intent.v1 document",
                    observed={"path": str(activation_intent_path)},
                )
                self._logger.write(event)
                return BootstrapResult(ok=False, gate_code=event.code, write_actions=write_actions, error_events=(event,))
        elif payload.effective_mode == "user":
            self._fs.write_text_atomic(activation_intent_path, _canonical_json(_default_activation_intent()))
            activation_intent_valid = True
            write_actions["activation_intent"] = "created-default"
        else:
            event = ErrorEvent(
                code="ACTIVATION_INTENT_REQUIRED",
                severity="error",
                message="Activation intent missing outside user mode.",
                expected=f"{ACTIVATION_INTENT_FILE} exists and is schema-valid",
                observed={"path": str(activation_intent_path), "effectiveMode": payload.effective_mode},
            )
            self._logger.write(event)
            return BootstrapResult(ok=False, gate_code=event.code, write_actions=write_actions, error_events=(event,))

        initial_state = _session_state_payload(
            repo_fingerprint=payload.repo_identity.fingerprint,
            repo_name=payload.repo_identity.repo_name,
            persistence_committed=False,
            workspace_ready_committed=False,
            workspace_artifacts_committed=False,
            effective_mode=payload.effective_mode,
            write_policy_reasons=payload.write_policy_reasons,
        )
        session_state_file = Path(payload.layout.session_state_file)
        identity_map_file = Path(payload.layout.identity_map_file)
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

        if payload.no_commit:
            write_actions["no_commit"] = "true"
            return BootstrapResult(ok=True, gate_code="OK", write_actions=write_actions, error_events=tuple(errors))

        if payload.skip_artifact_backfill:
            write_actions["artifact_backfill"] = "skipped"
        else:
            command = list(payload.backfill_command)
            if not command:
                command = [payload.binding.python_command, "diagnostics/persist_workspace_artifacts.py"]
            run = self._runner.run(command)
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

        # Determine PointerVerified explicitly based on read-back and pointer payload validity
        pointer_verified_final = False
        try:
            pointer_readback = self._fs.read_text(pointer_file)
            pointer_json_read = json.loads(pointer_readback)
            pointer_verified_final = _is_valid_pointer_payload(
                pointer_json_read,
                expected_repo_fingerprint=payload.repo_identity.fingerprint,
                expected_session_state_file=payload.layout.session_state_file,
            )
        except Exception:
            pointer_verified_final = False

        final_state = _session_state_payload(
            repo_fingerprint=payload.repo_identity.fingerprint,
            repo_name=payload.repo_identity.repo_name,
            persistence_committed=True,
            workspace_ready_committed=True,
            workspace_artifacts_committed=True,
            effective_mode=payload.effective_mode,
            write_policy_reasons=payload.write_policy_reasons,
            pointer_verified=pointer_verified_final,
            activation_intent_valid=activation_intent_valid,
        )
        self._fs.write_text_atomic(session_state_file, _canonical_json(final_state))
        write_actions["session_state_final"] = "written"
        return BootstrapResult(ok=True, gate_code="OK", write_actions=write_actions, error_events=tuple(errors))


def _canonical_json(data: object) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"


def _is_valid_pointer_payload(
    payload: object,
    *,
    expected_repo_fingerprint: str,
    expected_session_state_file: str,
) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("schema") != "opencode-session-pointer.v1":
        return False
    if payload.get("activeRepoFingerprint") != expected_repo_fingerprint:
        return False

    active_state_file = payload.get("activeSessionStateFile")
    if not isinstance(active_state_file, str) or not active_state_file.strip():
        return False

    actual_path = Path(active_state_file.strip())
    expected_path = Path(expected_session_state_file)
    if not actual_path.is_absolute():
        return False
    return actual_path == expected_path


def _session_state_payload(
    *,
    repo_fingerprint: str,
    repo_name: str,
    persistence_committed: bool,
    workspace_ready_committed: bool,
    workspace_artifacts_committed: bool,
    effective_mode: str,
    write_policy_reasons: tuple[str, ...],
    pointer_verified: bool = False,
    activation_intent_valid: bool = False,
) -> dict[str, object]:
    repository = repo_name.strip() if repo_name.strip() else repo_fingerprint
    bootstrap_present = bool(persistence_committed)
    bootstrap_satisfied = bool(persistence_committed and workspace_ready_committed and workspace_artifacts_committed and pointer_verified)
    bootstrap_evidence = "not-initialized" if not bootstrap_present else ("bootstrap-completed" if bootstrap_satisfied else "bootstrap-in-progress")
    # Determine phase/mode based on bootstrap completion
    phase = "1.1-Bootstrap"
    mode = "BLOCKED"
    next_gate = "BLOCKED-START-REQUIRED"
    if bootstrap_satisfied and activation_intent_valid:
        phase = "1.2-ActivationIntent"
        mode = "IN_PROGRESS"
        next_gate = "P2-RepoDiscovery-ready"

    return {
        "SESSION_STATE": {
            "RepoFingerprint": repo_fingerprint,
            "PersistenceCommitted": persistence_committed,
            "WorkspaceReadyGateCommitted": workspace_ready_committed,
            "WorkspaceArtifactsCommitted": workspace_artifacts_committed,
            "phase_transition_evidence": False,
            "session_state_version": 1,
            "ruleset_hash": "deferred",
            "Phase": phase,
            "Mode": mode,
            "ConfidenceLevel": 0,
            "Next": next_gate,
            "OutputMode": "ARCHITECT",
            "DecisionSurface": {},
            "Bootstrap": {
                "Present": bootstrap_present,
                "Satisfied": bootstrap_satisfied,
                "Evidence": bootstrap_evidence,
            },
            "Scope": {
                "Repository": repository,
                "RepositoryType": "",
                "ExternalAPIs": [],
                "BusinessRules": "pending",
            },
            "LoadedRulebooks": {
                "core": "",
                "profile": "",
                "templates": "",
                "addons": {},
            },
            "AddonsEvidence": {},
            "RulebookLoadEvidence": {
                "top_tier": {
                    "quality_index": "${COMMANDS_HOME}/QUALITY_INDEX.md",
                    "conflict_resolution": "${COMMANDS_HOME}/CONFLICT_RESOLUTION.md",
                },
                "core": "deferred",
                "profile": "deferred",
                "templates": "deferred",
                "addons": {},
            },
            "ActiveProfile": "",
            "ProfileSource": "deferred",
            "ProfileEvidence": "",
            "Gates": {
                "P5-Architecture": "pending",
                "P5.3-TestQuality": "pending",
                "P5.4-BusinessRules": "pending",
                "P5.5-TechnicalDebt": "pending",
                "P5.6-RollbackSafety": "pending",
                "P6-ImplementationQA": "pending",
            },
            "CreatedAt": "deferred",
            "ActivationIntent": {
                "FilePath": f"${{CONFIG_ROOT}}/{ACTIVATION_INTENT_FILE}",
                "Schema": "opencode-activation-intent.v1",
                "Status": "valid" if activation_intent_valid else "missing",
                "AutoSatisfied": bool(activation_intent_valid),
            },
            "writePolicy": {
                "mode": effective_mode,
                "reasons": list(write_policy_reasons),
            },
            "CommitFlags": {
                "PersistenceCommitted": persistence_committed,
                "WorkspaceReadyGateCommitted": workspace_ready_committed,
                "WorkspaceArtifactsCommitted": workspace_artifacts_committed,
                "PointerVerified": pointer_verified,
            },
        }
    }


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except Exception:
        return False
