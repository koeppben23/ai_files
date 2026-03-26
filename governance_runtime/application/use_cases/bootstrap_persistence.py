from __future__ import annotations

import json
import os
import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from governance_runtime.application.ports.filesystem import FileSystemPort
from governance_runtime.application.ports.logger import ErrorLoggerPort
from governance_runtime.application.ports.process_runner import ProcessRunnerPort
from governance_runtime.application.ports.gateways import HostAdapter
from governance_runtime.application.use_cases.bootstrap_session import evaluate_bootstrap_identity
from governance_runtime.domain.models.binding import Binding
from governance_runtime.domain.models.layouts import WorkspaceLayout
from governance_runtime.domain.models.repo_identity import RepoIdentity
from governance_runtime.domain.policies.write_policy import compute_write_policy

from governance_runtime.domain.errors.events import ErrorEvent


ACTIVATION_INTENT_FILE = "governance.activation_intent.json"
REPO_POLICY_RELATIVE_PATH = ".opencode/governance-repo-policy.json"


def _read_default_governance_config() -> str:
    """Read the default governance-config.json from package assets.
    
    Uses importlib.resources for robust resolution that works with:
    - Source tree (development)
    - Installed packages (pip install)
    - Bundled executables (PyInstaller, etc.)
    
    Returns:
        File content as string.
        
    Raises:
        FileNotFoundError: If asset cannot be found or read.
    """
    import importlib.resources
    try:
        asset_ref = importlib.resources.files("governance_runtime.assets.config") / "governance-config.json"
        return asset_ref.read_text(encoding="utf-8")
    except (FileNotFoundError, TypeError) as exc:
        module_root = Path(__file__).parent.parent.parent
        fallback_path = module_root / "assets" / "config" / "governance-config.json"
        if fallback_path.is_file():
            return fallback_path.read_text(encoding="utf-8")
        raise FileNotFoundError(
            f"governance-runtime asset 'governance-config.json' not found. "
            f"Checked: importlib.resources and {fallback_path}. "
            f"Error: {exc}"
        ) from exc



def _default_activation_intent() -> dict[str, object]:
    return {
        "schema": "opencode-activation-intent.v1",
        "discovery_scope": "full",
        "discovery_patterns": [],
        "discovery_excludes": [],
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


def _activation_intent_sha256(payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_valid_activation_intent(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("schema") != "opencode-activation-intent.v1":
        return False

    discovery_scope = payload.get("discovery_scope")
    if discovery_scope not in {"full", "governance-only", "changed-files-only"}:
        return False

    discovery_patterns = payload.get("discovery_patterns", [])
    discovery_excludes = payload.get("discovery_excludes", [])
    if not isinstance(discovery_patterns, list) or not isinstance(discovery_excludes, list):
        return False
    if any(not isinstance(item, str) for item in discovery_patterns):
        return False
    if any(not isinstance(item, str) for item in discovery_excludes):
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

    def run(self, payload: BootstrapInput, created_at: str) -> BootstrapResult:
        write_actions: dict[str, str] = {}
        errors: list[ErrorEvent] = []

        policy = compute_write_policy(force_read_only=payload.force_read_only, mode=payload.effective_mode)
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
        activation_intent_sha256 = ""
        activation_intent_scope = "unknown"
        if self._fs.exists(activation_intent_path):
            try:
                activation_intent = json.loads(self._fs.read_text(activation_intent_path))
            except Exception:
                activation_intent = None
            if _is_valid_activation_intent(activation_intent):
                activation_intent_valid = True
                activation_intent_sha256 = _activation_intent_sha256(activation_intent)
                if isinstance(activation_intent, dict):
                    activation_intent_scope = str(activation_intent.get("discovery_scope") or "full")
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
            created_activation_intent = _default_activation_intent()
            self._fs.write_text_atomic(activation_intent_path, _canonical_json(created_activation_intent))
            activation_intent_valid = True
            activation_intent_sha256 = _activation_intent_sha256(created_activation_intent)
            activation_intent_scope = str(created_activation_intent.get("discovery_scope") or "full")
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

        repo_policy_path = repo_root / REPO_POLICY_RELATIVE_PATH
        if not self._fs.exists(repo_policy_path):
            self._fs.mkdir_p(repo_policy_path.parent)
            default_repo_mode = "team" if payload.effective_mode in {"pipeline", "agents_strict"} else "solo"
            repo_policy = {
                "schema": "opencode-governance-repo-policy.v1",
                "repoFingerprint": payload.repo_identity.fingerprint,
                "operatingMode": default_repo_mode,
                "source": "bootstrap-init",
                "createdAt": created_at,
            }
            self._fs.write_text_atomic(repo_policy_path, _canonical_json(repo_policy))
            write_actions["repo_policy"] = "created"
        else:
            write_actions["repo_policy"] = "present"

        initial_state = _session_state_payload(
            repo_fingerprint=payload.repo_identity.fingerprint,
            repo_name=payload.repo_identity.repo_name,
            persistence_committed=False,
            workspace_ready_committed=False,
            workspace_artifacts_committed=False,
            effective_mode=payload.effective_mode,
            write_policy_reasons=payload.write_policy_reasons,
            created_at=created_at,
            intent_path=f"${{CONFIG_ROOT}}/{ACTIVATION_INTENT_FILE}",
            activation_intent_valid=activation_intent_valid,
            intent_sha256=activation_intent_sha256,
            intent_effective_scope=activation_intent_scope,
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

        # Ensure deterministic runtime/audit directory split exists so
        # downstream consumers do not need lazy creation.
        workspace_root = Path(payload.layout.repo_home)
        self._fs.mkdir_p(workspace_root / "logs")
        self._fs.mkdir_p(
            Path(payload.binding.workspaces_home)
            / "governance-records"
            / payload.repo_identity.fingerprint
            / "runs"
        )
        write_actions["workspace_dirs"] = "ensured"

        # Materialize governance-config.json to workspace if not present (idempotent).
        governance_config_path = workspace_root / "governance-config.json"
        if not self._fs.exists(governance_config_path):
            try:
                default_config_content = _read_default_governance_config()
                self._fs.write_text_atomic(governance_config_path, default_config_content)
                write_actions["governance_config"] = "materialized"
            except FileNotFoundError as exc:
                self._logger.write(ErrorEvent(
                    code="GOVERNANCE_CONFIG_ASSET_MISSING",
                    severity="warning",
                    message=f"governance-config.json asset not found: {exc}",
                    expected="governance-runtime asset available",
                    observed={"error": str(exc)},
                ))
                write_actions["governance_config"] = "skipped-no-asset"
        else:
            write_actions["governance_config"] = "present"

        if payload.no_commit:
            write_actions["no_commit"] = "true"
            return BootstrapResult(ok=True, gate_code="OK", write_actions=write_actions, error_events=tuple(errors))

        if payload.skip_artifact_backfill:
            write_actions["artifact_backfill"] = "skipped"
        else:
            command = list(payload.backfill_command)
            if not command:
                command = [payload.binding.python_command, "-m", "governance_runtime.entrypoints.persist_workspace_artifacts"]
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
            "activeSessionStateRelativePath": f"workspaces/{payload.repo_identity.fingerprint}/SESSION_STATE.json",
        }
        pointer_text = _canonical_json(pointer_payload)
        self._fs.write_text_atomic(pointer_file, pointer_text)
        write_actions["pointer"] = "written"

        pointer_readback = self._fs.read_text(pointer_file)
        pointer_verified_final = False
        try:
            pointer_json_read = json.loads(pointer_readback)
            pointer_verified_final = _is_valid_pointer_payload(
                pointer_json_read,
                expected_repo_fingerprint=payload.repo_identity.fingerprint,
                expected_session_state_file=payload.layout.session_state_file,
            )
        except Exception:
            pointer_verified_final = False

        if not pointer_verified_final:
            event = ErrorEvent(
                code="POINTER_VERIFY_FAILED",
                severity="error",
                message="Pointer verification failed after write.",
                expected="pointer read-back is valid and canonical",
                observed={"pointerFile": str(pointer_file)},
            )
            self._logger.write(event)
            errors.append(event)
            return BootstrapResult(ok=False, gate_code=event.code, write_actions=write_actions, error_events=tuple(errors))

        write_actions["pointer_verify"] = "verified"

        if not pointer_verified_final:
            event = ErrorEvent(
                code="POINTER_VERIFY_FAILED",
                severity="error",
                message="Pointer verification failed after read-back.",
                expected="pointer read-back is valid and canonical",
                observed={"pointerFile": str(pointer_file)},
            )
            self._logger.write(event)
            errors.append(event)
            return BootstrapResult(ok=False, gate_code=event.code, write_actions=write_actions, error_events=tuple(errors))

        final_state = _session_state_payload(
            repo_fingerprint=payload.repo_identity.fingerprint,
            repo_name=payload.repo_identity.repo_name,
            persistence_committed=True,
            workspace_ready_committed=True,
            workspace_artifacts_committed=True,
            effective_mode=payload.effective_mode,
            write_policy_reasons=payload.write_policy_reasons,
            created_at=created_at,
            pointer_verified=pointer_verified_final,
            activation_intent_valid=activation_intent_valid,
            intent_path=f"${{CONFIG_ROOT}}/{ACTIVATION_INTENT_FILE}",
            intent_sha256=activation_intent_sha256,
            intent_effective_scope=activation_intent_scope,
        )
        merged_final_state = _merge_final_session_state(
            existing_text=self._fs.read_text(session_state_file),
            fallback_state=final_state,
            repo_fingerprint=payload.repo_identity.fingerprint,
            persistence_committed=True,
            workspace_ready_committed=True,
            workspace_artifacts_committed=True,
            pointer_verified=pointer_verified_final,
            bootstrap_present=True,
            bootstrap_satisfied=True,
            bootstrap_evidence="bootstrap-completed",
            effective_mode=payload.effective_mode,
            write_policy_reasons=payload.write_policy_reasons,
            activation_intent_valid=activation_intent_valid,
            intent_path=f"${{CONFIG_ROOT}}/{ACTIVATION_INTENT_FILE}",
            intent_sha256=activation_intent_sha256,
            intent_effective_scope=activation_intent_scope,
        )
        self._fs.write_text_atomic(session_state_file, _canonical_json(merged_final_state))
        write_actions["session_state_final"] = "written"
        return BootstrapResult(ok=True, gate_code="OK", write_actions=write_actions, error_events=tuple(errors))


def _canonical_json(data: object) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n"


def _merge_final_session_state(
    *,
    existing_text: str,
    fallback_state: dict[str, object],
    repo_fingerprint: str,
    persistence_committed: bool,
    workspace_ready_committed: bool,
    workspace_artifacts_committed: bool,
    pointer_verified: bool,
    bootstrap_present: bool,
    bootstrap_satisfied: bool,
    bootstrap_evidence: str,
    effective_mode: str,
    write_policy_reasons: tuple[str, ...],
    activation_intent_valid: bool,
    intent_path: str,
    intent_sha256: str,
    intent_effective_scope: str,
) -> dict[str, object]:
    try:
        parsed = json.loads(existing_text)
    except Exception:
        parsed = None

    if not isinstance(parsed, dict):
        return fallback_state

    session = parsed.get("SESSION_STATE")
    if not isinstance(session, dict):
        return fallback_state

    fallback_session = fallback_state.get("SESSION_STATE")
    if isinstance(fallback_session, dict):
        session["phase"] = fallback_session.get("Phase")
        session["next"] = fallback_session.get("Next")
        session["Mode"] = fallback_session.get("Mode")
        session.setdefault("OutputMode", fallback_session.get("OutputMode"))

    session["RepoFingerprint"] = repo_fingerprint
    session["PersistenceCommitted"] = persistence_committed
    session["WorkspaceReadyGateCommitted"] = workspace_ready_committed
    session["WorkspaceArtifactsCommitted"] = workspace_artifacts_committed

    bootstrap = session.get("Bootstrap")
    bootstrap_block = dict(bootstrap) if isinstance(bootstrap, dict) else {}
    bootstrap_block["Present"] = bootstrap_present
    bootstrap_block["Satisfied"] = bootstrap_satisfied
    bootstrap_block["Evidence"] = bootstrap_evidence
    session["Bootstrap"] = bootstrap_block

    activation = session.get("ActivationIntent")
    activation_block = dict(activation) if isinstance(activation, dict) else {}
    activation_block["FilePath"] = intent_path
    activation_block["Schema"] = "opencode-activation-intent.v1"
    activation_block["Status"] = "valid" if activation_intent_valid else "missing"
    activation_block["AutoSatisfied"] = bool(activation_intent_valid)
    activation_block["DiscoveryScope"] = "full" if activation_intent_valid else "unknown"
    session["ActivationIntent"] = activation_block

    intent = session.get("Intent")
    intent_block = dict(intent) if isinstance(intent, dict) else {}
    intent_block["Path"] = intent_path
    intent_block["Sha256"] = intent_sha256
    intent_block["EffectiveScope"] = intent_effective_scope
    session["Intent"] = intent_block

    session["writePolicy"] = {
        "mode": effective_mode,
        "reasons": list(write_policy_reasons),
    }
    session["CommitFlags"] = {
        "PersistenceCommitted": persistence_committed,
        "WorkspaceReadyGateCommitted": workspace_ready_committed,
        "WorkspaceArtifactsCommitted": workspace_artifacts_committed,
        "PointerVerified": pointer_verified,
    }

    parsed["SESSION_STATE"] = session
    return parsed


def _is_valid_pointer_payload(
    payload: object,
    *,
    expected_repo_fingerprint: str,
    expected_session_state_file: str,
) -> bool:
    def _is_absolute_path(value: str) -> bool:
        if os.path.isabs(value):
            return True
        return value.startswith("/")
    if not isinstance(payload, dict):
        return False
    if payload.get("schema") != "opencode-session-pointer.v1":
        return False
    if payload.get("activeRepoFingerprint") != expected_repo_fingerprint:
        return False

    active_state_file = payload.get("activeSessionStateFile")
    if not isinstance(active_state_file, str) or not active_state_file.strip():
        return False
    rel_path = payload.get("activeSessionStateRelativePath")
    expected_rel = f"workspaces/{expected_repo_fingerprint}/SESSION_STATE.json"
    if rel_path is not None:
        if not isinstance(rel_path, str) or not rel_path.strip():
            return False
        if rel_path.replace("\\", "/") != expected_rel:
            return False

    active_state_file_value = active_state_file.strip()
    actual_path = Path(active_state_file_value)
    expected_path = Path(expected_session_state_file)
    if not _is_absolute_path(active_state_file_value):
        return False
    if actual_path != expected_path:
        return False
    if rel_path is not None:
        if not str(actual_path).replace("\\", "/").endswith(expected_rel):
            return False
    return True


def _session_state_payload(
    *,
    repo_fingerprint: str,
    repo_name: str,
    persistence_committed: bool,
    workspace_ready_committed: bool,
    workspace_artifacts_committed: bool,
    effective_mode: str,
    write_policy_reasons: tuple[str, ...],
    created_at: str,
    pointer_verified: bool = False,
    activation_intent_valid: bool = False,
    intent_path: str = "",
    intent_sha256: str = "",
    intent_effective_scope: str = "unknown",
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
        next_gate = "1.3"

    return {
        "SESSION_STATE": {
            "RepoFingerprint": repo_fingerprint,
            "PersistenceCommitted": persistence_committed,
            "WorkspaceReadyGateCommitted": workspace_ready_committed,
            "WorkspaceArtifactsCommitted": workspace_artifacts_committed,
            "phase_transition_evidence": False,
            "session_state_version": 1,
            "ruleset_hash": None,
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
            "ticket_intake_ready": False,
            "AddonsEvidence": {},
            "RulebookLoadEvidence": {
                "top_tier": {
                    "quality_index": "${CONTENT_HOME}/QUALITY_INDEX.md",
                    "conflict_resolution": "${CONTENT_HOME}/CONFLICT_RESOLUTION.md",
                },
                "core": "deferred",
                "profile": "deferred",
                "templates": "deferred",
                "addons": {},
            },
            "ActiveProfile": None,
            "ProfileSource": None,
            "ProfileEvidence": None,
            "Gates": {
                "P5-Architecture": "pending",
                "P5.3-TestQuality": "pending",
                "P5.4-BusinessRules": "pending",
                "P5.5-TechnicalDebt": "pending",
                "P5.6-RollbackSafety": "pending",
                "P6-ImplementationQA": "pending",
            },
            "CreatedAt": created_at,
            "ActivationIntent": {
                "FilePath": f"${{CONFIG_ROOT}}/{ACTIVATION_INTENT_FILE}",
                "Schema": "opencode-activation-intent.v1",
                "Status": "valid" if activation_intent_valid else "missing",
                "AutoSatisfied": bool(activation_intent_valid),
                "DiscoveryScope": "full" if activation_intent_valid else "unknown",
            },
            "Intent": {
                "Path": intent_path,
                "Sha256": intent_sha256,
                "EffectiveScope": intent_effective_scope,
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


@dataclass(frozen=True)
class StartPersistenceDecision:
    repo_root: Path | None
    repo_fingerprint: str
    discovery_method: str
    workspace_ready: bool
    reason_code: str
    reason: str


def decide_bootstrap_persistence(*, adapter: HostAdapter) -> StartPersistenceDecision:
    identity = evaluate_bootstrap_identity(adapter=adapter)
    repo_fp = identity.repo_fingerprint.strip()
    if identity.reason == "repo-root-not-git":
        return StartPersistenceDecision(
            repo_root=None,
            repo_fingerprint="",
            discovery_method=identity.discovery_method,
            workspace_ready=False,
            reason_code="BLOCKED-REPO-IDENTITY-RESOLUTION",
            reason="repo-root-not-git",
        )
    if not repo_fp or not identity.workspace_ready:
        return StartPersistenceDecision(
            repo_root=None,
            repo_fingerprint="",
            discovery_method=identity.discovery_method,
            workspace_ready=False,
            reason_code="BLOCKED-REPO-IDENTITY-RESOLUTION",
            reason=identity.reason if identity.reason and identity.reason != "none" else "identity-bootstrap-fingerprint-missing",
        )
    return StartPersistenceDecision(
        repo_root=identity.repo_root,
        repo_fingerprint=repo_fp,
        discovery_method=identity.discovery_method,
        workspace_ready=True,
        reason_code="none",
        reason="none",
    )
