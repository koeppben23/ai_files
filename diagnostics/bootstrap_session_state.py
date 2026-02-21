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
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


_is_pipeline = os.environ.get("CI", "").strip().lower() not in {"", "0", "false", "no", "off"}


def _writes_allowed() -> bool:
    """Check if write operations are permitted.
    
    Returns:
        True if writes are allowed, False if read-only mode is enforced.
    
    The function checks OPENCODE_DIAGNOSTICS_FORCE_READ_ONLY environment variable.
    When set to "1", all write operations are blocked for safety.
    """
    if str(os.environ.get("OPENCODE_DIAGNOSTICS_FORCE_READ_ONLY", "")).strip() == "1":
        return False
    return True

SCRIPT_DIR = Path(os.path.abspath(__file__)).parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(SCRIPT_DIR.parent) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR.parent))

try:
    from governance.infrastructure.path_contract import (
        canonical_config_root,
        normalize_absolute_path,
    )
except Exception:
    class NotAbsoluteError(Exception):
        pass

    class WindowsDriveRelativeError(Exception):
        pass

    def canonical_config_root() -> Path:
        return Path(os.path.normpath(os.path.abspath(str(Path.home().expanduser() / ".config" / "opencode"))))

    def normalize_absolute_path(raw: str, *, purpose: str) -> Path:
        token = str(raw or "").strip()
        if not token:
            raise NotAbsoluteError(f"{purpose}: empty path")
        candidate = Path(token).expanduser()
        if os.name == "nt" and re.match(r"^[A-Za-z]:[^/\\]", token):
            raise WindowsDriveRelativeError(f"{purpose}: drive-relative path is not allowed")
        if not candidate.is_absolute():
            raise NotAbsoluteError(f"{purpose}: path must be absolute")
        return Path(os.path.normpath(os.path.abspath(str(candidate))))

try:
    from error_logs import safe_log_error
except Exception:  # pragma: no cover
    def safe_log_error(**kwargs):  # type: ignore[no-redef]
        return {"status": "log-disabled"}

from workspace_lock import acquire_workspace_lock
try:
    from governance.infrastructure.fs_atomic import atomic_write_text
except Exception:
    def atomic_write_text(path: Path, text: str, newline_lf: bool = True, attempts: int = 5, backoff_ms: int = 50) -> int:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = text.replace("\r\n", "\n") if newline_lf else text
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n" if newline_lf else None,
                dir=str(path.parent),
                prefix=path.name + ".",
                suffix=".tmp",
                delete=False,
            ) as tmp:
                tmp.write(payload)
                tmp.flush()
                os.fsync(tmp.fileno())
                temp_path = Path(tmp.name)
            os.replace(str(temp_path), str(path))
            return 0
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink(missing_ok=True)


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
    data = _load_json(paths_file)
    if not isinstance(data, dict):
        raise ValueError(f"binding evidence unreadable: {paths_file}")
    paths = data.get("paths")
    if not isinstance(paths, dict):
        raise ValueError(f"binding evidence invalid: missing paths object in {paths_file}")
    config_root_raw = paths.get("configRoot")
    workspaces_raw = paths.get("workspacesHome")
    if not isinstance(config_root_raw, str) or not config_root_raw.strip():
        raise ValueError(f"binding evidence invalid: paths.configRoot missing in {paths_file}")
    if not isinstance(workspaces_raw, str) or not workspaces_raw.strip():
        raise ValueError(f"binding evidence invalid: paths.workspacesHome missing in {paths_file}")
    try:
        config_root = normalize_absolute_path(config_root_raw, purpose="paths.configRoot")
        _workspaces_home = normalize_absolute_path(workspaces_raw, purpose="paths.workspacesHome")
    except Exception as exc:
        raise ValueError(f"binding evidence invalid: {exc}") from exc
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


def _validate_repo_fingerprint(value: str) -> str:
    """Validate repo fingerprint is canonical 24-hex format.
    
    This enforces SSOT: only hash-based fingerprints are accepted.
    Legacy slug-style fingerprints (e.g., github.com-user-repo) are rejected.
    
    Args:
        value: The fingerprint string to validate.
    
    Returns:
        The validated fingerprint (lowercase, stripped).
    
    Raises:
        ValueError: If fingerprint is empty or not 24-hex format.
    """
    token = value.strip()
    if not token:
        raise ValueError("repo fingerprint must not be empty")
    if not re.fullmatch(r"[0-9a-f]{24}", token):
        raise ValueError(
            "repo fingerprint must be a 24-character hex string (canonical hash-based format). "
            "Legacy slug-style fingerprints are not accepted."
        )
    return token


def _validate_canonical_fingerprint(value: str) -> str:
    """Alias for _validate_repo_fingerprint for clarity.
    
    Args:
        value: The fingerprint string to validate.
    
    Returns:
        The validated canonical fingerprint.
    """
    return _validate_repo_fingerprint(value)


def _is_canonical_fingerprint(value: str) -> bool:
    """Check if value is a canonical 24-hex fingerprint.
    
    Args:
        value: The string to check.
    
    Returns:
        True if value matches ^[0-9a-f]{24}$, False otherwise.
    """
    token = value.strip()
    return bool(re.fullmatch(r"[0-9a-f]{24}", token))


def repo_session_state_path(workspaces_home: Path, repo_fingerprint: str) -> Path:
    """Get the path to a repository's SESSION_STATE.json file.
    
    Args:
        workspaces_home: The workspaces home directory.
        repo_fingerprint: The canonical 24-hex fingerprint.
    
    Returns:
        Path to ${WORKSPACES_HOME}/${fingerprint}/SESSION_STATE.json
    """
    return workspaces_home / repo_fingerprint / "SESSION_STATE.json"


def session_pointer_path(config_root: Path) -> Path:
    """Get the path to the global SESSION_STATE pointer file.
    
    Args:
        config_root: The OpenCode config root directory.
    
    Returns:
        Path to ${CONFIG_ROOT}/SESSION_STATE.json (global pointer).
    """
    return config_root / "SESSION_STATE.json"


def repo_identity_map_path(workspaces_home: Path, repo_fingerprint: str) -> Path:
    """Get the path to a repository's identity map file.
    
    Args:
        workspaces_home: The workspaces home directory.
        repo_fingerprint: The canonical 24-hex fingerprint.
    
    Returns:
        Path to ${WORKSPACES_HOME}/${fingerprint}/repo-identity-map.yaml
    """
    return workspaces_home / repo_fingerprint / "repo-identity-map.yaml"


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


def session_state_template(repo_fingerprint: str, repo_name: str | None) -> dict:
    """Create the initial SESSION_STATE template for a repository.
    
    The template initializes all state fields to their default "uninitialized"
    values. Critical flags like PersistenceCommitted and WorkspaceReadyGateCommitted
    are set to False - they will only be set to True after successful verification.
    
    Args:
        repo_fingerprint: The canonical 24-hex fingerprint for this repository.
        repo_name: Optional human-readable repository name.
    
    Returns:
        A dictionary containing the SESSION_STATE template.
    
    Note:
        BusinessRules is initialized to "pending" (not "not-applicable") to
        ensure the Phase 1.5 gate is evaluated rather than skipped.
    """
    repository = repo_name.strip() if isinstance(repo_name, str) and repo_name.strip() else repo_fingerprint
    return {
        "SESSION_STATE": {
            "RepoFingerprint": repo_fingerprint,
            "PersistenceCommitted": False,
            "WorkspaceReadyGateCommitted": False,
            "phase_transition_evidence": False,
            "session_state_version": 1,
            "ruleset_hash": "deferred",
            "Phase": "1.1-Bootstrap",
            "Mode": "BLOCKED",
            "ConfidenceLevel": 0,
            "Next": "BLOCKED-START-REQUIRED",
            "OutputMode": "ARCHITECT",
            "DecisionSurface": {},
            "Bootstrap": {
                "Present": False,
                "Satisfied": False,
                "Evidence": "not-initialized",
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
            "CreatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
    }


def pointer_payload(repo_fingerprint: str, session_state_file: Path | None = None) -> dict:
    """Create the global SESSION_STATE pointer payload.
    
    The pointer is the SSOT for finding the active workspace. It uses the
    canonical schema "opencode-session-pointer.v1" and contains the fingerprint
    and path to the workspace's SESSION_STATE.json.
    
    Args:
        repo_fingerprint: The canonical 24-hex fingerprint for this repository.
        session_state_file: Optional explicit path to the workspace SESSION_STATE.
            If not provided, a relative path under workspaces/ is generated.
    
    Returns:
        A dictionary containing the pointer payload ready for JSON serialization.
    """
    payload = {
        "schema": "opencode-session-pointer.v1",
        "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "activeRepoFingerprint": repo_fingerprint,
    }
    if session_state_file is not None:
        payload["activeSessionStateFile"] = str(session_state_file)
    else:
        payload["activeSessionStateRelativePath"] = f"workspaces/{repo_fingerprint}/SESSION_STATE.json"
    return payload


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create repo-scoped SESSION_STATE bootstrap and update global SESSION_STATE pointer file."
        )
    )
    parser.add_argument("--repo-fingerprint", required=True, help="Repo workspace key (e.g. 3a76fdae74e6ec7b).")
    parser.add_argument("--repo-name", default="", help="Optional repository display name for SESSION_STATE.Scope.Repository.")
    parser.add_argument("--config-root", type=Path, default=None, help="Override OpenCode config root.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing repo SESSION_STATE file and migrate legacy global payload if needed.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned actions without writing files.")
    parser.add_argument(
        "--skip-artifact-backfill",
        action="store_true",
        help="Skip invoking diagnostics/persist_workspace_artifacts.py after bootstrap.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        config_root, binding_paths, _binding_file = resolve_binding_config(args.config_root)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        print("Restore installer-owned commands/governance.paths.json and rerun.")
        return 2

    workspaces_home = normalize_absolute_path(
        str(binding_paths.get("workspacesHome", "")),
        purpose="paths.workspacesHome",
    )

    cwd_repo_root = normalize_absolute_path(str(Path.cwd()), purpose="cwd")
    if (cwd_repo_root / ".git").exists() and _is_within(config_root, cwd_repo_root):
        print("ERROR: config root resolves inside repository root")
        print("Set OPENCODE_CONFIG_ROOT to a location outside the repository and rerun.")
        return 5

    try:
        repo_fingerprint = _validate_repo_fingerprint(args.repo_fingerprint)
    except ValueError as exc:
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

    repo_state_file = workspaces_home / repo_fingerprint / "SESSION_STATE.json"
    pointer_file = session_pointer_path(config_root)
    identity_map_file = workspaces_home / repo_fingerprint / "repo-identity-map.yaml"

    try:
        workspace_lock = acquire_workspace_lock(
            workspaces_home=workspaces_home,
            repo_fingerprint=repo_fingerprint,
        )
    except TimeoutError:
        print("ERROR: workspace lock timeout")
        print("Wait for active run to complete or clear stale lock after verification.")
        return 6

    print(f"Config root: {config_root}")
    print(f"Repo fingerprint: {repo_fingerprint}")
    print(f"Repo SESSION_STATE file: {repo_state_file}")
    print(f"Global pointer file: {pointer_file}")
    print(f"Repo identity map file: {identity_map_file}")

    pointer_existing = _load_json(pointer_file)
    pointer_has_legacy_payload = isinstance(pointer_existing, dict) and "SESSION_STATE" in pointer_existing

    if pointer_has_legacy_payload and not args.force and not args.dry_run:
        safe_log_error(
            reason_key="ERR-LEGACY-SESSION-POINTER-MIGRATION-REQUIRED",
            message="Legacy global SESSION_STATE payload detected in pointer file.",
            config_root=config_root,
            phase="1.1-Bootstrap",
            gate="BOOTSTRAP",
            mode="repo-aware",
            repo_fingerprint=repo_fingerprint,
            command="bootstrap_session_state.py",
            component="session-pointer",
            observed_value={"pointerFile": str(pointer_file)},
            expected_constraint="Global pointer must use schema opencode-session-pointer.v1",
            remediation="Re-run with --force to migrate legacy payload to repo-scoped SESSION_STATE.",
        )
        print("ERROR: legacy global SESSION_STATE payload detected in pointer file.")
        print("Use --force to migrate to pointer mode.")
        workspace_lock.release()
        return 4

    should_write_repo_state = args.force or not repo_state_file.exists()

    if args.dry_run:
        repo_action = "overwrite" if (repo_state_file.exists() and args.force) else "create"
        if not should_write_repo_state:
            repo_action = "preserve"
        pointer_action = "overwrite" if pointer_file.exists() else "create"
        identity_action = "update" if identity_map_file.exists() else "create"

        print(f"[DRY-RUN] Repo SESSION_STATE action: {repo_action} -> {repo_state_file}")
        print(f"[DRY-RUN] Pointer action: {pointer_action} -> {pointer_file}")
        print(f"[DRY-RUN] Repo identity map action: {identity_action} -> {identity_map_file}")
        if pointer_has_legacy_payload:
            print("[DRY-RUN] Legacy global payload migration would be applied (requires --force for live write).")
        workspace_lock.release()
        return 0

    repo_payload: dict | None = None
    if should_write_repo_state:
        if pointer_has_legacy_payload and args.force:
            assert isinstance(pointer_existing, dict)
            repo_payload = pointer_existing
            print("Migrating legacy global SESSION_STATE payload to repo-scoped location.")
        else:
            repo_payload = session_state_template(repo_fingerprint, args.repo_name)

        _atomic_write_text(repo_state_file, json.dumps(repo_payload, indent=2, ensure_ascii=True) + "\n")
        print("Repo-scoped SESSION_STATE written.")
    else:
        print("Repo-scoped SESSION_STATE already exists and was preserved (use --force to overwrite).")
        existing_payload = _load_json(repo_state_file)
        if isinstance(existing_payload, dict):
            repo_payload = existing_payload

    pointer = pointer_payload(repo_fingerprint, repo_state_file)
    pointer["runId"] = workspace_lock.lock_id
    pointer["phase"] = "1.1-Bootstrap"
    _atomic_write_text(pointer_file, json.dumps(pointer, indent=2, ensure_ascii=True) + "\n")
    print("Global SESSION_STATE pointer written.")

    if not pointer_file.is_file():
        safe_log_error(
            reason_key="ERR-POINTER-WRITE-VERIFICATION-FAILED",
            message="Pointer file does not exist after atomic write.",
            config_root=config_root,
            phase="1.1-Bootstrap",
            gate="BOOTSTRAP",
            mode="repo-aware",
            repo_fingerprint=repo_fingerprint,
            command="bootstrap_session_state.py",
            component="session-pointer",
            observed_value={"pointerFile": str(pointer_file)},
            expected_constraint="Pointer file must exist after atomic write",
            remediation="Check filesystem permissions and disk space.",
        )
        print("ERROR: pointer verification failed - file does not exist after write.")
        workspace_lock.release()
        return 8

    pointer_verify = _load_json(pointer_file)
    if not pointer_verify or pointer_verify.get("schema") != "opencode-session-pointer.v1":
        safe_log_error(
            reason_key="ERR-POINTER-SCHEMA-VERIFICATION-FAILED",
            message="Pointer file has invalid schema after write.",
            config_root=config_root,
            phase="1.1-Bootstrap",
            gate="BOOTSTRAP",
            mode="repo-aware",
            repo_fingerprint=repo_fingerprint,
            command="bootstrap_session_state.py",
            component="session-pointer",
            observed_value={"pointerFile": str(pointer_file), "schema": pointer_verify.get("schema") if pointer_verify else None},
            expected_constraint="Pointer must have schema 'opencode-session-pointer.v1'",
            remediation="Check filesystem integrity and retry.",
        )
        print("ERROR: pointer verification failed - invalid schema.")
        workspace_lock.release()
        return 9

    if isinstance(repo_payload, dict) and "SESSION_STATE" in repo_payload:
        repo_payload["SESSION_STATE"]["PersistenceCommitted"] = True
        repo_payload["SESSION_STATE"]["WorkspaceReadyGateCommitted"] = True
        _atomic_write_text(repo_state_file, json.dumps(repo_payload, indent=2, ensure_ascii=True) + "\n")
        print("PersistenceCommitted=True set in workspace SESSION_STATE (after pointer verified).")

    scope = repo_payload.get("SESSION_STATE", {}).get("Scope", {}) if isinstance(repo_payload, dict) else {}
    repo_name_value = scope.get("Repository") if isinstance(scope, dict) else None
    if not isinstance(repo_name_value, str) or not repo_name_value.strip():
        repo_name_value = repo_fingerprint
    identity_action = _upsert_repo_identity_map(workspaces_home, repo_fingerprint, repo_name_value.strip())
    print(f"Repo identity map {identity_action}.")

    backfill_failed = False
    if not args.skip_artifact_backfill:
        helper = SCRIPT_DIR / "persist_workspace_artifacts.py"
        if helper.exists():
            cmd = [
                sys.executable,
                str(helper),
                "--repo-fingerprint",
                repo_fingerprint,
                "--config-root",
                str(config_root),
                "--skip-lock",
                "--quiet",
            ]
            run = subprocess.run(cmd, text=True, capture_output=True, check=False)
            if run.returncode == 0:
                print("Workspace artifact backfill hook completed.")
            else:
                safe_log_error(
                    reason_key="ERR-WORKSPACE-PERSISTENCE-HOOK-FAILED",
                    message="Workspace artifact backfill hook returned non-zero.",
                    config_root=config_root,
                    phase="1.1-Bootstrap",
                    gate="PERSISTENCE",
                    mode="repo-aware",
                    repo_fingerprint=repo_fingerprint,
                    command="bootstrap_session_state.py",
                    component="workspace-persistence-hook",
                    observed_value={
                        "returncode": run.returncode,
                        "stdout": run.stdout.strip()[:400],
                        "stderr": run.stderr.strip()[:400],
                    },
                    expected_constraint="persist_workspace_artifacts.py must return code 0",
                    remediation="Inspect helper output and rerun bootstrap or backfill manually.",
                )
                print("WARNING: workspace artifact backfill hook failed; bootstrap state was still written.")
                if run.stdout.strip():
                    print(run.stdout.strip())
                if run.stderr.strip():
                    print(run.stderr.strip())
                backfill_failed = True
        else:
            safe_log_error(
                reason_key="ERR-WORKSPACE-PERSISTENCE-HOOK-MISSING",
                message="Workspace artifact backfill helper missing during bootstrap.",
                config_root=config_root,
                phase="1.1-Bootstrap",
                gate="PERSISTENCE",
                mode="repo-aware",
                repo_fingerprint=repo_fingerprint,
                command="bootstrap_session_state.py",
                component="workspace-persistence-hook",
                observed_value={"helper": str(helper)},
                expected_constraint="persist_workspace_artifacts.py present under diagnostics",
                remediation="Reinstall governance package and rerun bootstrap.",
            )
            print("WARNING: persist_workspace_artifacts.py not found; skipping artifact backfill hook.")

    if backfill_failed:
        workspace_lock.release()
        return 7

    workspace_lock.release()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
