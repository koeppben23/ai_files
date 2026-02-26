#!/usr/bin/env python3
"""
Persistence hook for bootstrap.

This module is called by bootstrap_preflight_readonly.py when writes are enabled.
It is intentionally separate to maintain SoC and keep preflight truly read-only
by default.

Environment:
    OPENCODE_MODE=user|pipeline|agents_strict - explicit mode
    OPENCODE_FORCE_READ_ONLY=1 - If set, blocks all writes (safety gate)
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).absolute().parents[2]))


import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

from governance.entrypoints.write_policy import EFFECTIVE_MODE, writes_allowed


def _writes_allowed() -> bool:
    """Check if write operations are permitted.
    
    Returns:
        True if writes are allowed, False if read-only mode is enforced.
    
    The function checks OPENCODE_FORCE_READ_ONLY (and legacy alias) environment variable.
    When set to "1", all write operations are blocked for safety.
    """
    return writes_allowed()

SCRIPT_DIR = Path(os.path.abspath(__file__)).parent
_FALLBACK_COMMANDS_HOME = SCRIPT_DIR.parent.parent  # grandparent = commands root (parent of governance)

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(SCRIPT_DIR.parent) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR.parent))

try:
    from governance.infrastructure.logging.error_logs import safe_log_error
except ImportError:
    def safe_log_error(**kwargs):
        return {"status": "log-disabled"}

from governance.entrypoints.error_handler_bridge import (
    ErrorContext,
    emit_gate_failure,
    install_global_handlers,
    set_error_context,
)

try:
    from governance.application.use_cases.bootstrap_session import evaluate_bootstrap_identity
    from governance.engine.adapters import LocalHostAdapter
    from governance.infrastructure.path_contract import normalize_absolute_path
    from governance.infrastructure.wiring import configure_gateway_registry
    from governance.infrastructure.binding_evidence_resolver import BindingEvidenceResolver
    from governance.infrastructure.logging.global_error_handler import resolve_log_path
except ImportError as exc:
    print(json.dumps({
        "persistence_hook": "failed",
        "reason": "import-error",
        "error": str(exc),
        "writes_allowed": _writes_allowed(),
    }, ensure_ascii=True))
    sys.exit(1)

_run_bootstrap_dispatch = cast(Any, None)
_derive_fingerprint_ssot = cast(Any, None)
_resolve_repo_root_from_bootstrap = cast(Any, None)
try:
    from bootstrap.dispatch import run_bootstrap_dispatch as _bootstrap_dispatch
    _run_bootstrap_dispatch = cast(Any, _bootstrap_dispatch)
except ImportError:
    def _fallback_bootstrap_dispatch(*, command, cwd):  # type: ignore
        proc = subprocess.run(
            list(command),
            text=True,
            capture_output=True,
            check=False,
            cwd=str(cwd),
        )

        class _FallbackDispatchResult:
            def __init__(self, returncode: int, stdout: str, stderr: str):
                self.returncode = returncode
                self.stdout = stdout
                self.stderr = stderr

        return _FallbackDispatchResult(
            returncode=proc.returncode,
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
        )

    _run_bootstrap_dispatch = cast(Any, _fallback_bootstrap_dispatch)

try:
    from bootstrap.repo_identity import (
        derive_fingerprint as _bootstrap_derive_fingerprint,
        resolve_repo_root_ssot as _bootstrap_resolve_repo_root_ssot,
    )
    _derive_fingerprint_ssot = cast(Any, _bootstrap_derive_fingerprint)
    _resolve_repo_root_from_bootstrap = cast(Any, _bootstrap_resolve_repo_root_ssot)
except ImportError:
    pass


def _resolve_bindings(*, mode: str) -> tuple[Path | None, Path | None, bool, Path | None, str]:
    """Resolve binding evidence paths for the current mode.
    
    Args:
        mode: The effective mode ('pipeline' or 'user').
    
    Returns:
        Tuple of (commands_home, workspaces_home, binding_ok, paths_file, python_command).
    """
    resolver = BindingEvidenceResolver()
    evidence = resolver.resolve(mode=mode)
    python_command = evidence.python_command.strip() if evidence.python_command else ""
    if not python_command:
        # Use sys.executable instead of "python3" for Windows compatibility
        python_command = sys.executable
    
    # If binding evidence is missing or invalid, use fallback derived from script location
    if evidence.commands_home is None or not str(evidence.commands_home).strip():
        return (
            _FALLBACK_COMMANDS_HOME,
            None,
            False,
            None,
            python_command,
        )
    
    return (
        evidence.commands_home,
        evidence.workspaces_home,
        evidence.binding_ok,
        evidence.governance_paths_json,
        python_command,
    )


COMMANDS_HOME, WORKSPACES_HOME, BINDING_OK, BINDING_EVIDENCE_PATH, PYTHON_COMMAND = _resolve_bindings(mode=EFFECTIVE_MODE)

# Final safety check - should rarely trigger since we have fallback
if COMMANDS_HOME is None or str(COMMANDS_HOME).strip() == "" or not COMMANDS_HOME.is_absolute():
    print(json.dumps({
        "persistence_hook": "failed",
        "reason": "commands_home-empty-or-missing",
        "commands_home_received": str(COMMANDS_HOME) if COMMANDS_HOME else "None",
        "binding_ok": BINDING_OK,
    }, ensure_ascii=True))
    sys.exit(1)


class _RepoIdentityAdapter(LocalHostAdapter):
    """Adapter to provide repo-specific identity for fingerprint derivation.
    
    This adapter overrides the cwd and environment to point to a specific
    repository root, allowing evaluate_bootstrap_identity to derive the fingerprint
    from the correct location.
    """
    
    def __init__(self, repo_root: Path):
        """Initialize the adapter for a specific repo root.
        
        Args:
            repo_root: The absolute path to the repository root.
        """
        super().__init__()
        resolved = normalize_absolute_path(str(repo_root), purpose="repo_root")
        self._repo_root = resolved
        env = dict(os.environ)
        env["OPENCODE_REPO_ROOT"] = str(resolved)
        self._env = env

    def environment(self):
        """Get the environment for this adapter.
        
        Returns:
            Dictionary of environment variables including OPENCODE_REPO_ROOT.
        """
        return self._env

    def cwd(self) -> Path:
        """Get the current working directory for this adapter.
        
        Returns:
            The repository root path.
        """
        return self._repo_root


def derive_repo_fingerprint(repo_root: Path) -> str | None:
    """Derive the canonical 24-hex fingerprint for a repository.
    
    The fingerprint is derived in the following order:
        1. From evaluate_bootstrap_identity (git remote → SHA256[:24])
        2. Fallback: local path → SHA256[:24]
    
    Args:
        repo_root: The path to the repository root.
    
    Returns:
        A 24-character hex string fingerprint, or None if derivation fails.
    """
    try:
        normalized_repo_root = normalize_absolute_path(str(repo_root), purpose="repo_root")
    except Exception:
        return None

    if _derive_fingerprint_ssot is not None:
        try:
            fp = str(_derive_fingerprint_ssot(normalized_repo_root) or "").strip()
            if fp and _is_canonical_fingerprint(fp):
                return fp
        except Exception:
            pass

    fp = None
    try:
        configure_gateway_registry()
        identity = evaluate_bootstrap_identity(adapter=cast(Any, _RepoIdentityAdapter(normalized_repo_root)))
        fp = (identity.repo_fingerprint or "").strip()
    except Exception:
        pass

    if fp and _is_canonical_fingerprint(fp):
        return fp

    import hashlib
    from governance.infrastructure.path_contract import normalize_for_fingerprint
    normalized_root = normalize_for_fingerprint(normalized_repo_root)
    material = f"repo:local:{normalized_root}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def _is_canonical_fingerprint(value: str) -> bool:
    """Check if value is a canonical 24-hex fingerprint.
    
    Args:
        value: The string to check.
    
    Returns:
        True if value matches ^[0-9a-f]{24}$, False otherwise.
    """
    import re
    token = value.strip()
    return bool(re.fullmatch(r"[0-9a-f]{24}", token))


def _resolve_git_repo_root(start_dir: Path) -> Path | None:
    """Resolve git repository root from a starting directory.
    
    Uses git rev-parse --show-toplevel to find the actual repository root,
    which handles worktrees and submodules correctly.
    
    Args:
        start_dir: Starting directory for git resolution.
    
    Returns:
        Path to the git repository root, or None if not in a git repo.
    """
    import subprocess
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=str(start_dir),
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if result.returncode == 0:
            root = result.stdout.strip()
            if root:
                return Path(root).absolute()
    except Exception:
        pass
    return None


def _resolve_repo_root_ssot(explicit_root: Path | None = None) -> tuple[Path | None, str]:
    """Resolve repository root using SSOT approach.
    
    Priority:
        1. Explicit repo_root argument (from OPENCODE_REPO_ROOT or caller)
        2. Git metadata (git rev-parse --show-toplevel)
        3. None (failsafe - should be handled by caller)
    
    NEVER uses Path.cwd() directly as repo root - only as starting point for git resolution.
    
    Args:
        explicit_root: Optional explicit repo root path.
    
    Returns:
        Tuple of (resolved_path, source). Path may be None if resolution fails.
    """
    if _resolve_repo_root_from_bootstrap is not None:
        try:
            result = _resolve_repo_root_from_bootstrap(explicit_root)
            if isinstance(result, tuple) and len(result) == 2:
                path, source = result
                if path is None:
                    return None, str(source)
                return normalize_absolute_path(str(path), purpose="repo_root"), str(source)
        except Exception:
            pass

    if explicit_root is not None:
        try:
            return normalize_absolute_path(str(explicit_root), purpose="explicit_repo_root"), "explicit"
        except Exception:
            return None, "invalid-explicit"
    
    env_root = os.environ.get("OPENCODE_REPO_ROOT", "").strip()
    if env_root:
        try:
            return normalize_absolute_path(env_root, purpose="OPENCODE_REPO_ROOT"), "env"
        except Exception:
            pass
    
    cwd = Path.cwd()
    git_root = _resolve_git_repo_root(cwd)
    if git_root:
        return git_root, "git-metadata"
    
    return None, "not-a-git-repo"


def _verify_pointer_exists(opencode_home: Path, repo_fingerprint: str) -> tuple[bool, str]:
    """Verify that the global pointer exists and references the correct fingerprint.
    
    Args:
        opencode_home: The OpenCode home directory.
        repo_fingerprint: The expected canonical 24-hex fingerprint.
    
    Returns:
        Tuple of (success, reason). Success is True if pointer exists and
        references the correct fingerprint. Reason describes any failure.
    """
    pointer_path = opencode_home / "SESSION_STATE.json"
    if not pointer_path.is_file():
        return False, "pointer-file-not-found"
    try:
        payload = json.loads(pointer_path.read_text(encoding="utf-8"))
    except Exception:
        return False, "pointer-file-unreadable"
    if not isinstance(payload, dict):
        return False, "pointer-invalid-shape"
    if payload.get("schema") != "opencode-session-pointer.v1":
        return False, f"pointer-invalid-schema:{payload.get('schema')}"
    active_fp = payload.get("activeRepoFingerprint")
    if active_fp != repo_fingerprint:
        return False, f"pointer-fingerprint-mismatch:expected={repo_fingerprint},got={active_fp}"
    active_state_file = payload.get("activeSessionStateFile")
    if not isinstance(active_state_file, str) or not active_state_file.strip():
        return False, "pointer-missing-activeSessionStateFile"
    active_state_path = Path(active_state_file.strip())
    if not active_state_path.is_absolute():
        return False, "pointer-activeSessionStateFile-not-absolute"
    if not active_state_path.is_file():
        return False, "pointer-activeSessionStateFile-missing"
    try:
        state_payload = json.loads(active_state_path.read_text(encoding="utf-8"))
    except Exception:
        return False, "pointer-activeSessionStateFile-unreadable"
    if not isinstance(state_payload, dict):
        return False, "pointer-activeSessionStateFile-invalid-shape"
    state = state_payload.get("SESSION_STATE")
    if not isinstance(state, dict):
        return False, "pointer-activeSessionStateFile-missing-SESSION_STATE"
    state_fp = state.get("RepoFingerprint") or state.get("repo_fingerprint")
    if state_fp != repo_fingerprint:
        return False, "pointer-activeSessionStateFile-fingerprint-mismatch"
    return True, "ok"


def _verify_workspace_session_exists(workspaces_home: Path, repo_fingerprint: str) -> tuple[bool, str]:
    session_path = workspaces_home / repo_fingerprint / "SESSION_STATE.json"
    if not session_path.is_file():
        return False, "workspace-session-file-not-found"
    try:
        payload = json.loads(session_path.read_text(encoding="utf-8"))
    except Exception:
        return False, "workspace-session-file-unreadable"
    if not isinstance(payload, dict):
        return False, "workspace-session-invalid-shape"
    session_state = payload.get("SESSION_STATE")
    if not isinstance(session_state, dict):
        return False, "workspace-session-missing-SESSION_STATE-key"
    if not session_state.get("PersistenceCommitted"):
        return False, "workspace-session-PersistenceCommitted-not-true"
    return True, "ok"


def run_persistence_hook(*, repo_root: Path | None = None) -> dict[str, object]:
    install_global_handlers()
    commands_home = COMMANDS_HOME
    
    if commands_home is None or str(commands_home).strip() == "" or not commands_home.is_absolute():
        emit_gate_failure(
            gate="PERSISTENCE",
            code="BLOCKED-MISSING-COMMANDS-HOME",
            message="commands_home is missing, empty, or not absolute.",
            expected="valid absolute path in commands_home",
            observed={"commands_home": str(commands_home) if commands_home else "None"},
            remediation="Ensure governance.paths.json contains valid commandsHome path.",
        )
        return {
            "workspacePersistenceHook": "failed",
            "reason_code": "BLOCKED-MISSING-COMMANDS-HOME",
            "reason": "commands_home-missing-or-empty",
            "commands_home_received": str(commands_home) if commands_home else "None",
            "impact": "cannot run persistence hook without valid commands_home",
            "writes_allowed": True,
        }
    
    workspaces_home = WORKSPACES_HOME if WORKSPACES_HOME is not None else (
        commands_home.parent / "workspaces" if commands_home is not None else None
    )

    def _with_log_path(payload: dict[str, object], repo_fingerprint: str | None = None) -> dict[str, object]:
        if "repo_fingerprint" not in payload:
            payload["repo_fingerprint"] = repo_fingerprint or ""
        if "log_path" not in payload:
            try:
                payload["log_path"] = str(
                    resolve_log_path(
                        config_root=commands_home.parent if commands_home is not None else None,
                        commands_home=commands_home,
                        workspaces_home=workspaces_home,
                        repo_fingerprint=repo_fingerprint,
                    )
                )
            except Exception:
                payload["log_path"] = ""
        return payload

    if not _writes_allowed():
        emit_gate_failure(
            gate="PERSISTENCE",
            code="PERSISTENCE_READ_ONLY",
            message="Persistence hook blocked by write policy.",
            expected="writes allowed",
            observed={"mode": EFFECTIVE_MODE, "writes_allowed": False},
            remediation="Unset OPENCODE_FORCE_READ_ONLY or switch to an allowed mode.",
        )
        return _with_log_path({
            "workspacePersistenceHook": "blocked",
            "reason_code": "BLOCKED-WORKSPACE-PERSISTENCE",
            "reason": "writes-not-allowed",
            "mode": EFFECTIVE_MODE,
            "writes_allowed": False,
        })

    resolved_root, root_source = _resolve_repo_root_ssot(repo_root)
    
    if resolved_root is None:
        emit_gate_failure(
            gate="PERSISTENCE",
            code="BLOCKED-REPO-ROOT-NOT-DETECTABLE",
            message="Could not resolve git repository root.",
            expected="valid repository root",
            observed={"root_source": root_source, "cwd": str(Path.cwd())},
            remediation="Run from within a git repository or set OPENCODE_REPO_ROOT.",
        )
        result = {
            "workspacePersistenceHook": "failed",
            "reason_code": "BLOCKED-REPO-ROOT-NOT-DETECTABLE",
            "reason": f"repo-root-resolution-failed:{root_source}",
            "impact": "cannot create workspace without valid git repository root",
            "writes_allowed": True,
            "root_source": root_source,
            "cwd": str(Path.cwd()),
            "repo_root_detected": "",
            "python_executable": sys.executable,
            "bootstrap_hook_command": f"{sys.executable} -m governance.entrypoints.bootstrap_persistence_hook",
        }
        safe_log_error(
            reason_key="ERR-PERSISTENCE-REPO-ROOT-RESOLUTION-FAILED",
            message=f"Could not resolve git repository root (source: {root_source}).",
            config_root=commands_home.parent if commands_home is not None else None,
            phase="1.1-Bootstrap",
            gate="PERSISTENCE",
            mode=EFFECTIVE_MODE,
            repo_fingerprint=None,
            command="bootstrap_persistence_hook.py",
            component="persistence-hook",
            observed_value={"root_source": root_source, "cwd": str(Path.cwd())},
            expected_constraint="must be in a git repository or provide explicit repo_root",
            remediation="Run from within a git repository or set OPENCODE_REPO_ROOT environment variable.",
        )
        return _with_log_path(result)

    repo_fp = derive_repo_fingerprint(resolved_root)

    set_error_context(ErrorContext(
        repo_fingerprint=repo_fp,
        config_root=(str(commands_home.parent) if commands_home is not None else None),
        workspaces_home=(str(workspaces_home) if workspaces_home is not None else None),
        repo_root=str(resolved_root),
        phase="1.1-Bootstrap",
        command="bootstrap_persistence_hook.py",
    ))

    if not repo_fp:
        emit_gate_failure(
            gate="PERSISTENCE",
            code="REPO_FINGERPRINT_DERIVATION_FAILED",
            message="Could not derive repository fingerprint.",
            expected="non-empty repo fingerprint",
            observed={"repo_root": str(resolved_root)},
            remediation="Ensure git metadata is present and repository root is valid.",
        )
        result = {
            "workspacePersistenceHook": "failed",
            "reason": "repo-fingerprint-derivation-failed",
            "impact": "cannot create workspace without repo fingerprint",
            "writes_allowed": True,
        }
        safe_log_error(
            reason_key="ERR-PERSISTENCE-FINGERPRINT-DERIVATION-FAILED",
            message="Could not derive repo fingerprint from git metadata during persistence hook.",
            config_root=commands_home.parent if commands_home is not None else None,
            phase="1.1-Bootstrap",
            gate="PERSISTENCE",
            mode=EFFECTIVE_MODE,
            repo_fingerprint=None,
            command="bootstrap_persistence_hook.py",
            component="persistence-hook",
            observed_value={"repo_root": str(resolved_root)},
            expected_constraint="git repository with valid origin or local path",
            remediation="Ensure cwd is a git repository with valid .git metadata.",
        )
        return _with_log_path(result)

    if commands_home is None or not str(commands_home).strip():
        return _with_log_path(
            {
                "workspacePersistenceHook": "blocked",
                "reason_code": "BLOCKED-MISSING-BINDING-FILE",
                "reason": "binding-evidence-missing-or-invalid",
                "impact": "cannot run persistence hook without valid commands/workspaces binding",
                "writes_allowed": True,
            },
            repo_fingerprint=repo_fp,
        )
    if workspaces_home is None:
        workspaces_home = commands_home.parent / "workspaces"

    bootstrap_script = commands_home / "governance" / "entrypoints" / "bootstrap_session_state.py"
    if not bootstrap_script.exists():
        emit_gate_failure(
            gate="PERSISTENCE",
            code="BOOTSTRAP_SCRIPT_MISSING",
            message="bootstrap_session_state.py not found at expected location.",
            expected="bootstrap script exists under governance entrypoints",
            observed={"expected_path": str(bootstrap_script)},
            remediation="Reinstall governance commands or fix commands home binding.",
        )
        result = {
            "workspacePersistenceHook": "failed",
            "reason": "bootstrap-script-not-found",
            "impact": f"bootstrap_session_state.py not found at {bootstrap_script}",
            "writes_allowed": True,
        }
        safe_log_error(
            reason_key="ERR-PERSISTENCE-BOOTSTRAP-SCRIPT-MISSING",
            message="bootstrap_session_state.py not found at expected location.",
            config_root=commands_home.parent,
            phase="1.1-Bootstrap",
            gate="PERSISTENCE",
            mode="user",
            repo_fingerprint=repo_fp,
            command="bootstrap_persistence_hook.py",
            component="persistence-hook",
            observed_value={"expected_path": str(bootstrap_script)},
            expected_constraint="bootstrap_session_state.py exists in ${COMMANDS_HOME}/governance/entrypoints/",
            remediation="Reinstall governance or verify commands home configuration.",
        )
        return _with_log_path(result, repo_fingerprint=repo_fp)

    repo_name = resolved_root.name
    cmd = [
        PYTHON_COMMAND,
        str(bootstrap_script),
        "--repo-fingerprint", repo_fp,
        "--repo-name", repo_name,
        "--repo-root", str(resolved_root),
        "--config-root", str(commands_home.parent),
    ]

    try:
        proc = _run_bootstrap_dispatch(command=cmd, cwd=resolved_root)
        if proc.returncode == 0:
            pointer_ok, pointer_reason = _verify_pointer_exists(commands_home.parent, repo_fp)
            if not pointer_ok:
                emit_gate_failure(
                    gate="PERSISTENCE",
                    code="POINTER_VERIFICATION_FAILED",
                    message="Pointer verification failed after bootstrap.",
                    expected="pointer exists and references current fingerprint",
                    observed={"pointer_reason": pointer_reason, "repo_fingerprint": repo_fp},
                    remediation="Inspect pointer file and rerun the local bootstrap launcher.",
                )
                result = {
                    "workspacePersistenceHook": "failed",
                    "reason": f"pointer-verification-failed:{pointer_reason}",
                    "returncode": proc.returncode,
                    "repo_fingerprint": repo_fp,
                    "repo_name": repo_name,
                    "writes_allowed": True,
                }
                safe_log_error(
                    reason_key="ERR-PERSISTENCE-POINTER-VERIFICATION-FAILED",
                    message=f"Pointer verification failed after bootstrap: {pointer_reason}",
                    config_root=commands_home.parent,
                    phase="1.1-Bootstrap",
                    gate="PERSISTENCE",
                    mode="user",
                    repo_fingerprint=repo_fp,
                    command="bootstrap_persistence_hook.py",
                    component="persistence-hook",
                    observed_value={"pointer_reason": pointer_reason},
                    expected_constraint="Global SESSION_STATE pointer must exist and reference correct fingerprint",
                    remediation="Check filesystem permissions and re-run the bootstrap launcher.",
                )
                return _with_log_path(result, repo_fingerprint=repo_fp)

            workspace_ok, workspace_reason = _verify_workspace_session_exists(workspaces_home, repo_fp)
            if not workspace_ok:
                emit_gate_failure(
                    gate="PERSISTENCE",
                    code="WORKSPACE_SESSION_VERIFICATION_FAILED",
                    message="Workspace SESSION_STATE verification failed after bootstrap.",
                    expected="workspace session exists with PersistenceCommitted=True",
                    observed={"workspace_reason": workspace_reason, "repo_fingerprint": repo_fp},
                    remediation="Inspect workspace SESSION_STATE and rerun the local bootstrap launcher.",
                )
                result = {
                    "workspacePersistenceHook": "failed",
                    "reason": f"workspace-session-verification-failed:{workspace_reason}",
                    "returncode": proc.returncode,
                    "repo_fingerprint": repo_fp,
                    "repo_name": repo_name,
                    "writes_allowed": True,
                }
                safe_log_error(
                    reason_key="ERR-PERSISTENCE-WORKSPACE-SESSION-VERIFICATION-FAILED",
                    message=f"Workspace session verification failed after bootstrap: {workspace_reason}",
                    config_root=commands_home.parent,
                    phase="1.1-Bootstrap",
                    gate="PERSISTENCE",
                    mode="user",
                    repo_fingerprint=repo_fp,
                    command="bootstrap_persistence_hook.py",
                    component="persistence-hook",
                    observed_value={"workspace_reason": workspace_reason},
                    expected_constraint="Workspace SESSION_STATE must exist with PersistenceCommitted=True",
                    remediation="Check filesystem permissions and re-run the bootstrap launcher.",
                )
                return _with_log_path(result, repo_fingerprint=repo_fp)

            result = {
                "workspacePersistenceHook": "ok",
                "reason": "bootstrap-completed",
                "repo_fingerprint": repo_fp,
                "repo_name": repo_name,
                "writes_allowed": True,
                "pointer_verified": True,
                "workspace_session_verified": True,
            }
        else:
            emit_gate_failure(
                gate="PERSISTENCE",
                code="BOOTSTRAP_NON_ZERO_EXIT",
                message="bootstrap_session_state.py returned non-zero exit code.",
                expected="bootstrap return code 0",
                observed={
                    "returncode": proc.returncode,
                    "stdout": (proc.stdout or "").strip()[:500],
                    "stderr": (proc.stderr or "").strip()[:500],
                },
                remediation="Inspect bootstrap stderr/stdout and resolve blocking condition.",
            )
            result = {
                "workspacePersistenceHook": "failed",
                "reason_code": "BLOCKED-WORKSPACE-PERSISTENCE",
                "reason": "bootstrap-returncode-nonzero",
                "returncode": proc.returncode,
                "stdout": proc.stdout.strip()[:500] if proc.stdout else "",
                "stderr": proc.stderr.strip()[:500] if proc.stderr else "",
                "writes_allowed": True,
            }
            safe_log_error(
                reason_key="ERR-PERSISTENCE-BOOTSTRAP-NONZERO-EXIT",
                message="bootstrap_session_state.py returned non-zero exit code.",
                config_root=commands_home.parent,
                phase="1.1-Bootstrap",
                gate="PERSISTENCE",
                mode="user",
                repo_fingerprint=repo_fp,
                command="bootstrap_persistence_hook.py",
                component="persistence-hook",
                observed_value={
                    "returncode": proc.returncode,
                    "stdout": (proc.stdout or "").strip()[:500],
                    "stderr": (proc.stderr or "").strip()[:500],
                },
                expected_constraint="bootstrap_session_state.py must exit with code 0",
                remediation="Inspect stdout/stderr and fix bootstrap issues.",
            )
    except Exception as exc:
        emit_gate_failure(
            gate="PERSISTENCE",
            code="BOOTSTRAP_EXCEPTION",
            message="Exception while running bootstrap_session_state.py.",
            expected="bootstrap executes without exception",
            observed={"exception": str(exc)[:500]},
            remediation="Validate Python/runtime environment and bootstrap dependencies.",
        )
        result = {
            "workspacePersistenceHook": "failed",
            "reason_code": "BLOCKED-WORKSPACE-PERSISTENCE",
            "reason": "bootstrap-exception",
            "error": str(exc)[:500],
            "writes_allowed": True,
        }
        safe_log_error(
            reason_key="ERR-PERSISTENCE-BOOTSTRAP-EXCEPTION",
            message=f"Exception while running bootstrap_session_state.py: {exc}",
            config_root=commands_home.parent,
            phase="1.1-Bootstrap",
            gate="PERSISTENCE",
            mode="user",
            repo_fingerprint=repo_fp,
            command="bootstrap_persistence_hook.py",
            component="persistence-hook",
            observed_value={"exception": str(exc)[:500]},
            expected_constraint="bootstrap_session_state.py executes without exception",
            remediation="Check Python environment and bootstrap script integrity.",
        )

    if result.get("workspacePersistenceHook") == "ok":
        return result
    return _with_log_path(result, repo_fingerprint=repo_fp if isinstance(locals().get("repo_fp"), str) else None)


def main() -> int:
    result = run_persistence_hook()
    print(json.dumps(result, ensure_ascii=True))
    
    if result.get("workspacePersistenceHook") == "failed":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
