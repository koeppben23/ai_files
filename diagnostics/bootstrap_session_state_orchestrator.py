#!/usr/bin/env python3
"""Bootstrap session state for repository workspaces.

This module creates and manages the initial SESSION_STATE.json files for
repository workspaces, establishing the SSOT (Single Source of Truth) for
persistence state management.

Key Responsibilities:
    - Create repo-scoped SESSION_STATE.json with initial template
    - Write global SESSION_STATE pointer (opencode-session-pointer.v1)
    - Derive canonical 24-hex fingerprint from git metadata
    - Enforce fail-closed persistence ordering:
        1. Write workspace SESSION_STATE (PersistenceCommitted=False)
        2. Write repo-identity-map.yaml
        3. Run artifact backfill hook
        4. Write global pointer
        5. Verify pointer exists and is valid
        6. Set PersistenceCommitted=True (only after verify)

Exit Codes:
    0: Success
    2: Invalid arguments or blocked (writes not allowed)
    4: Legacy pointer migration required (use --force)
    5: Config root inside repository
    6: Workspace lock timeout
    7: Artifact backfill failed
    8: Pointer verification failed (file not found)
    9: Pointer verification failed (invalid schema)

Environment Variables:
    OPENCODE_DIAGNOSTICS_FORCE_READ_ONLY: Set to "1" to block all writes
    OPENCODE_CONFIG_ROOT: Override config root location
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(os.path.abspath(__file__)).parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(SCRIPT_DIR.parent) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR.parent))

from governance.entrypoints.write_policy import EFFECTIVE_MODE, is_write_allowed, write_policy_reasons, writes_allowed

try:
    from bootstrap.repo_identity import resolve_repo_root_ssot
except Exception:
    def resolve_repo_root_ssot(explicit_root: Path | None = None) -> tuple[Path | None, str]:
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

        try:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            if result.returncode == 0:
                git_root = result.stdout.strip()
                if git_root:
                    return normalize_absolute_path(git_root, purpose="repo_root"), "git-metadata"
        except Exception:
            pass

        return None, "not-a-git-repo"

try:
    from bootstrap.session_state_contract import (
        _is_canonical_fingerprint,
        _validate_canonical_fingerprint,
        _validate_repo_fingerprint,
        pointer_payload,
        repo_identity_map_path,
        repo_session_state_path,
        session_pointer_path,
        session_state_template,
    )
except Exception:
    from session_state_contract import (  # type: ignore
        _is_canonical_fingerprint,
        _validate_canonical_fingerprint,
        _validate_repo_fingerprint,
        pointer_payload,
        repo_identity_map_path,
        repo_session_state_path,
        session_pointer_path,
        session_state_template,
    )

from governance.infrastructure.logging.global_error_handler import (
    ErrorContext,
    emit_gate_failure,
    install_global_handlers,
    set_error_context,
)


def _writes_allowed() -> bool:
    """Legacy wrapper - use writes_allowed() from write_policy instead."""
    return writes_allowed()

from governance.infrastructure.path_contract import canonical_config_root, normalize_absolute_path

from governance.infrastructure.logging.error_logs import safe_log_error

from workspace_lock import acquire_workspace_lock
try:
    from governance.application.use_cases.bootstrap_persistence import (
        BootstrapInput,
        BootstrapPersistenceService,
    )
    from governance.domain.errors.events import ErrorEvent as GovernanceErrorEvent
except Exception:
    BootstrapPersistenceService = None  # type: ignore
from governance.infrastructure.fs_atomic import atomic_write_text


def default_config_root() -> Path:
    return canonical_config_root()


def _load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _atomic_write_text(path: Path, content: str) -> None:
    if not _writes_allowed():
        return
    atomic_write_text(path, content, newline_lf=True, attempts=5, backoff_ms=50)


def _load_binding_paths(paths_file: Path, *, expected_config_root: Path | None = None) -> tuple[Path, dict]:
    """Load binding paths with SSOT validation.
    
    This function validates binding paths consistently with the SSOT loader
    but works both in-repo (with governance module) and in-release (standalone).
    
    Validates:
    - commandsHome must be configRoot/commands
    - workspacesHome must be configRoot/workspaces
    
    Args:
        paths_file: Path to governance.paths.json
        expected_config_root: Optional expected config root for additional validation
    
    Returns:
        Tuple of (config_root, paths_dict)
    
    Raises:
        ValueError: If binding file is invalid or paths don't match constraints.
    """
    data = _load_json(paths_file)
    if not isinstance(data, dict):
        raise ValueError(f"binding evidence unreadable: {paths_file}")
    
    paths = data.get("paths")
    if not isinstance(paths, dict):
        raise ValueError(f"binding evidence invalid: missing paths object in {paths_file}")
    
    config_root_raw = paths.get("configRoot")
    commands_raw = paths.get("commandsHome")
    workspaces_raw = paths.get("workspacesHome")
    
    if not isinstance(config_root_raw, str) or not config_root_raw.strip():
        raise ValueError(f"binding evidence invalid: paths.configRoot missing in {paths_file}")
    if not isinstance(commands_raw, str) or not commands_raw.strip():
        raise ValueError(f"binding evidence invalid: paths.commandsHome missing in {paths_file}")
    if not isinstance(workspaces_raw, str) or not workspaces_raw.strip():
        raise ValueError(f"binding evidence invalid: paths.workspacesHome missing in {paths_file}")
    
    try:
        config_root = normalize_absolute_path(config_root_raw, purpose="paths.configRoot")
        commands_home = normalize_absolute_path(commands_raw, purpose="paths.commandsHome")
        workspaces_home = normalize_absolute_path(workspaces_raw, purpose="paths.workspacesHome")
    except Exception as exc:
        raise ValueError(f"binding evidence invalid: {exc}") from exc
    
    if commands_home != config_root / "commands":
        raise ValueError(
            f"binding evidence invalid: commandsHome must be configRoot/commands: "
            f"got {commands_home}, expected {config_root / 'commands'}"
        )
    
    if workspaces_home != config_root / "workspaces":
        raise ValueError(
            f"binding evidence invalid: workspacesHome must be configRoot/workspaces: "
            f"got {workspaces_home}, expected {config_root / 'workspaces'}"
        )
    
    if expected_config_root is not None:
        expected = normalize_absolute_path(str(expected_config_root), purpose="expected_config_root")
        if config_root != expected:
            raise ValueError("binding evidence mismatch: config root does not match explicit input")
    
    return config_root, paths


def resolve_binding_config(explicit: Path | None) -> tuple[Path, dict, Path]:
    """Resolve the binding configuration paths.
    
    Searches for governance.paths.json in the following order:
        1. Explicit --config-root argument
        2. OPENCODE_CONFIG_ROOT environment variable
        3. Default ~/.config/opencode location
    
    Args:
        explicit: Optional explicit config root path from --config-root.
    
    Returns:
        Tuple of (config_root, paths_dict, binding_file_path).
    
    Raises:
        ValueError: If binding file not found or invalid.
    """
    if explicit is not None:
        root = normalize_absolute_path(str(explicit), purpose="explicit_config_root")
        candidate = root / "commands" / "governance.paths.json"
        config_root, paths = _load_binding_paths(candidate, expected_config_root=root)
        return config_root, paths, candidate

    env_value = os.environ.get("OPENCODE_CONFIG_ROOT")
    if env_value:
        root = normalize_absolute_path(env_value, purpose="env:OPENCODE_CONFIG_ROOT")
        candidate = root / "commands" / "governance.paths.json"
        config_root, paths = _load_binding_paths(candidate, expected_config_root=root)
        return config_root, paths, candidate

    fallback = default_config_root()
    candidate = fallback / "commands" / "governance.paths.json"
    config_root, paths = _load_binding_paths(candidate, expected_config_root=fallback)
    return config_root, paths, candidate


def _is_within(path: Path, parent: Path) -> bool:
    """Check if a path is within a parent directory.
    
    Args:
        path: The path to check.
        parent: The potential parent directory.
    
    Returns:
        True if path is a descendant of parent, False otherwise.
    """
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _upsert_repo_identity_map(workspaces_home: Path, repo_fingerprint: str, repo_name: str) -> str:
    if not _writes_allowed():
        return "writes-not-allowed"
    path = workspaces_home / repo_fingerprint / "repo-identity-map.yaml"
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    existing = _load_json(path)
    if not isinstance(existing, dict) or existing.get("schema") != "opencode-repo-identity-map.v1":
        existing = {
            "schema": "opencode-repo-identity-map.v1",
            "updatedAt": now,
            "repositories": {},
        }

    repos = existing.get("repositories")
    if not isinstance(repos, dict):
        repos = {}
        existing["repositories"] = repos

    before = repos.get(repo_fingerprint)
    repos[repo_fingerprint] = {
        "repoName": repo_name,
        "source": "bootstrap-session-state",
        "updatedAt": now,
    }
    existing["updatedAt"] = now

    _atomic_write_text(path, json.dumps(existing, indent=2, ensure_ascii=True) + "\n")
    if before is None:
        return "created"
    return "updated"


class _GovernanceFSAdapter:
    def read_text(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def write_text_atomic(self, path: Path, content: str) -> None:
        _atomic_write_text(path, content)

    def exists(self, path: Path) -> bool:
        return path.exists()


class _GovernanceRunnerAdapter:
    class _Result:
        def __init__(self, returncode: int, stdout: str, stderr: str):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def run(self, argv: list[str], env: dict[str, str] | None = None):
        run = subprocess.run(argv, text=True, capture_output=True, check=False, env=env)
        return self._Result(returncode=run.returncode, stdout=run.stdout, stderr=run.stderr)


class _GovernanceLoggerAdapter:
    def __init__(self, *, config_root: Path, workspaces_home: Path, repo_fingerprint: str):
        self._config_root = config_root
        self._workspaces_home = workspaces_home
        self._repo_fingerprint = repo_fingerprint

    def write(self, event: "GovernanceErrorEvent") -> None:
        emit_gate_failure(
            gate="BOOTSTRAP",
            code=event.code,
            message=event.message,
            expected=event.expected,
            observed=event.observed,
            remediation=event.remediation,
            config_root=str(self._config_root),
            workspaces_home=str(self._workspaces_home),
            repo_fingerprint=self._repo_fingerprint,
            phase="1.1-Bootstrap",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create repo-scoped SESSION_STATE bootstrap and update global SESSION_STATE pointer file."
        )
    )
    parser.add_argument("--repo-fingerprint", required=True, help="Repo workspace key (e.g. 3a76fdae74e6ec7b).")
    parser.add_argument("--repo-name", default="", help="Optional repository display name for SESSION_STATE.Scope.Repository.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Absolute git top-level path for this repo (SSOT). If omitted, OPENCODE_REPO_ROOT must be set.",
    )
    parser.add_argument("--config-root", type=Path, default=None, help="Override OpenCode config root.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing repo SESSION_STATE file and migrate legacy global payload if needed.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned actions without writing files.")
    parser.add_argument(
        "--skip-artifact-backfill",
        action="store_true",
        help="Skip invoking governance/entrypoints/persist_workspace_artifacts.py after bootstrap.",
    )
    parser.add_argument(
        "--no-commit",
        action="store_true",
        help="Initialize workspace session state without pointer write or commit flags.",
    )
    return parser.parse_args()


def main() -> int:
    install_global_handlers()
    args = parse_args()
    allow_internal_skip = (
        os.environ.get("OPENCODE_INTERNAL_ALLOW_SKIP_ARTIFACT_BACKFILL", "0") == "1"
        or args.no_commit
    )
    
    # P0: Block --skip-artifact-backfill in live runs
    if args.skip_artifact_backfill and not args.dry_run and not allow_internal_skip:
        emit_gate_failure(
            gate="BOOTSTRAP",
            code="ARTIFACT_BACKFILL_SKIPPED_IN_LIVE_RUN",
            message="--skip-artifact-backfill is not allowed in live runs.",
            expected="Remove --skip-artifact-backfill or use --dry-run (internal calls may set OPENCODE_INTERNAL_ALLOW_SKIP_ARTIFACT_BACKFILL=1)",
            observed={"skip_artifact_backfill": True, "dry_run": False},
            remediation="Remove --skip-artifact-backfill or add --dry-run for inspection only.",
        )
        print("ERROR: --skip-artifact-backfill is not allowed for live bootstrap.")
        return 2
    
    try:
        config_root, binding_paths, _binding_file = resolve_binding_config(args.config_root)
    except ValueError as exc:
        emit_gate_failure(
            gate="BOOTSTRAP",
            code="MISSING_BINDING_FILE",
            message=str(exc),
            expected="installer-owned commands/governance.paths.json exists",
            observed={"config_root_arg": str(args.config_root) if args.config_root else ""},
            remediation="Restore governance.paths.json via installer or provide valid --config-root.",
        )
        print(f"ERROR: {exc}")
        print("Restore installer-owned commands/governance.paths.json and rerun.")
        return 2

    workspaces_home = normalize_absolute_path(
        str(binding_paths.get("workspacesHome", "")),
        purpose="paths.workspacesHome",
    )

    repo_root, _repo_root_source = resolve_repo_root_ssot(args.repo_root)
    if repo_root is None:
        emit_gate_failure(
            gate="BOOTSTRAP",
            code="REPO_ROOT_STRICT_REQUIRED",
            message="Repo root could not be determined (strict mode - no CWD fallback).",
            expected="Provide --repo-root, set OPENCODE_REPO_ROOT, or run from within a git repository",
            observed={"cwd": str(Path.cwd())},
            remediation="Run from within a git repository or provide --repo-root explicitly.",
        )
        print("ERROR: repo root not determined (strict mode - no CWD fallback).")
        return 2
    if (repo_root / ".git").exists() and _is_within(config_root, repo_root):
        emit_gate_failure(
            gate="BOOTSTRAP",
            code="CONFIG_ROOT_INSIDE_REPO",
            message="Config root resolves inside repository root (blocked).",
            expected="configRoot must be outside repoRoot",
            observed={"configRoot": str(config_root), "repoRoot": str(repo_root)},
            remediation="Set OPENCODE_CONFIG_ROOT to a location outside the repository and rerun.",
        )
        print("ERROR: config root resolves inside repository root")
        print("Set OPENCODE_CONFIG_ROOT to a location outside the repository and rerun.")
        return 5

    try:
        repo_fingerprint = _validate_repo_fingerprint(args.repo_fingerprint)
    except ValueError as exc:
        emit_gate_failure(
            gate="BOOTSTRAP",
            code="REPO_FINGERPRINT_INVALID",
            message=str(exc),
            expected="repo fingerprint matches [A-Za-z0-9._-]{6,128}",
            observed={"repoFingerprintArg": args.repo_fingerprint},
            remediation="Provide a valid --repo-fingerprint value.",
        )
        safe_log_error(
            reason_key="ERR-REPO-FINGERPRINT-INVALID",
            message=str(exc),
            config_root=config_root,
            phase="1.1-Bootstrap",
            gate="BOOTSTRAP",
            mode="repo-aware",
            repo_fingerprint=None,
            command="bootstrap_session_state.py",
            component="session-bootstrap",
            observed_value={"repoFingerprintArg": args.repo_fingerprint},
            expected_constraint="repo fingerprint must match [A-Za-z0-9._-]{6,128}",
            remediation="Provide a valid --repo-fingerprint value.",
        )
        print(f"ERROR: {exc}")
        return 2

    if not _writes_allowed():
        emit_gate_failure(
            gate="BOOTSTRAP",
            code="PERSISTENCE_READ_ONLY",
            message="Bootstrap blocked by write policy.",
            expected="writes allowed",
            observed={"repoFingerprint": repo_fingerprint, "mode": EFFECTIVE_MODE},
            remediation="Unset OPENCODE_DIAGNOSTICS_FORCE_READ_ONLY or switch to writable mode.",
        )
        print(json.dumps({
            "status": "blocked",
            "bootstrapSessionState": "blocked",
            "reason_code": "BLOCKED-WORKSPACE-PERSISTENCE",
            "reason": "writes-not-allowed",
            "impact": "fingerprint + persistence are required before any phase >= 2.1",
            "repoFingerprint": repo_fingerprint,
            "writes_allowed": False,
        }, ensure_ascii=True))
        return 2

    repo_state_file = repo_session_state_path(workspaces_home, repo_fingerprint)
    pointer_file = session_pointer_path(config_root)
    identity_map_file = repo_identity_map_path(workspaces_home, repo_fingerprint)

    if (repo_root / ".git").exists() and _is_within(pointer_file, repo_root):
        emit_gate_failure(
            gate="BOOTSTRAP",
            code="POINTER_PATH_INSIDE_REPO",
            message="Global pointer path resolves inside repository root (blocked).",
            expected="Pointer must live under configRoot (outside repoRoot)",
            observed={"pointerFile": str(pointer_file), "repoRoot": str(repo_root)},
            remediation="Fix binding so OPENCODE_HOME/configRoot is outside the repo; do not derive configRoot from CWD.",
        )
        print("ERROR: pointer file resolves inside repository root")
        return 5

    set_error_context(ErrorContext(
        repo_fingerprint=repo_fingerprint,
        config_root=str(config_root),
        workspaces_home=str(workspaces_home),
        repo_root=str(repo_root),
        phase="1.1-Bootstrap",
        command="bootstrap_session_state.py",
    ))

    try:
        workspace_lock = acquire_workspace_lock(
            workspaces_home=workspaces_home,
            repo_fingerprint=repo_fingerprint,
        )
    except TimeoutError:
        emit_gate_failure(
            gate="BOOTSTRAP",
            code="WORKSPACE_LOCK_TIMEOUT",
            message="Workspace lock acquisition timed out during bootstrap.",
            expected="exclusive workspace lock acquired",
            observed={"repoFingerprint": repo_fingerprint, "workspacesHome": str(workspaces_home)},
            remediation="Wait for active run to finish or clear stale lock after verification, then rerun.",
        )
        print("ERROR: workspace lock timeout")
        print("Wait for active run to complete or clear stale lock after verification.")
        return 6

    print(f"Config root: {config_root}")
    print(f"Repo fingerprint: {repo_fingerprint}")
    print(f"Repo SESSION_STATE file: {repo_state_file}")
    print(f"Global pointer file: {pointer_file}")
    print(f"Repo identity map file: {identity_map_file}")

    if BootstrapPersistenceService is None:
        emit_gate_failure(
            gate="BOOTSTRAP",
            code="BOOTSTRAP_SSOT_UNAVAILABLE",
            message="Governance bootstrap SSOT service import failed.",
            expected="governance.application.use_cases.bootstrap_persistence importable",
            observed={"service_available": False},
            remediation="Restore governance bootstrap use-case module and rerun bootstrap.",
        )
        print("ERROR: governance bootstrap SSOT service unavailable")
        workspace_lock.release()
        return 2

    from governance.application.use_cases.bootstrap_persistence import BootstrapInput
    from governance.domain.models.binding import Binding
    from governance.domain.models.layouts import WorkspaceLayout
    from governance.domain.models.repo_identity import RepoIdentity

    backfill_command: tuple[str, ...] = (
        sys.executable,
        str(SCRIPT_DIR / "persist_workspace_artifacts.py"),
        "--repo-fingerprint",
        repo_fingerprint,
        "--config-root",
        str(config_root),
        "--repo-root",
        str(repo_root),
        "--require-phase2",
        "--skip-lock",
        "--quiet",
    )
    payload = BootstrapInput(
        repo_identity=RepoIdentity(
            repo_root=str(repo_root),
            fingerprint=repo_fingerprint,
            repo_name=(args.repo_name or repo_root.name or repo_fingerprint),
            source="diagnostics.bootstrap",
        ),
        binding=Binding(
            config_root=str(config_root),
            commands_home=str(config_root / "commands"),
            workspaces_home=str(workspaces_home),
            python_command=sys.executable,
        ),
        layout=WorkspaceLayout(
            repo_home=str(workspaces_home / repo_fingerprint),
            session_state_file=str(repo_state_file),
            identity_map_file=str(identity_map_file),
            pointer_file=str(pointer_file),
        ),
        required_artifacts=(
            str(workspaces_home / repo_fingerprint / "repo-cache.yaml"),
            str(workspaces_home / repo_fingerprint / "repo-map-digest.md"),
            str(workspaces_home / repo_fingerprint / "workspace-memory.yaml"),
            str(workspaces_home / repo_fingerprint / "decision-pack.md"),
        ),
        force_read_only=not _writes_allowed(),
        skip_artifact_backfill=args.skip_artifact_backfill,
        backfill_command=backfill_command,
        effective_mode=EFFECTIVE_MODE,
        write_policy_reasons=write_policy_reasons(),
        no_commit=args.no_commit,
    )

    if args.dry_run:
        print(f"[DRY-RUN] Repo SESSION_STATE action: create -> {repo_state_file}")
        print(f"[DRY-RUN] Repo identity map action: create -> {identity_map_file}")
        print(f"[DRY-RUN] Pointer action: create -> {pointer_file}")
        print(f"[DRY-RUN] Backfill command: {' '.join(payload.backfill_command)}")
        workspace_lock.release()
        return 0

    service = BootstrapPersistenceService(
        fs=_GovernanceFSAdapter(),
        runner=_GovernanceRunnerAdapter(),  # type: ignore[arg-type]
        logger=_GovernanceLoggerAdapter(
            config_root=config_root,
            workspaces_home=workspaces_home,
            repo_fingerprint=repo_fingerprint,
        ),
    )
    result = service.run(payload)
    workspace_lock.release()
    if result.ok:
        return 0
    if result.gate_code in {"CONFIG_ROOT_INSIDE_REPO", "POINTER_PATH_INSIDE_REPO"}:
        return 5
    if result.gate_code in {"BACKFILL_NON_ZERO_EXIT", "PHASE2_ARTIFACTS_MISSING"}:
        return 7
    if result.gate_code == "POINTER_VERIFY_FAILED":
        return 9
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
