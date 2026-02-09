#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

try:
    from error_logs import safe_log_error
except Exception:  # pragma: no cover
    def safe_log_error(**kwargs):  # type: ignore[no-redef]
        return {"status": "log-disabled"}


def default_config_root() -> Path:
    if os.name == "nt":
        user_profile = os.environ.get("USERPROFILE")
        if user_profile:
            return Path(user_profile) / ".config" / "opencode"

        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "opencode"

        return Path.home() / ".config" / "opencode"

    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else (Path.home() / ".config")
    return base / "opencode"


def _load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def resolve_config_root(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.expanduser().resolve()

    env_value = os.environ.get("OPENCODE_CONFIG_ROOT")
    if env_value:
        return Path(env_value).expanduser().resolve()

    script_path = Path(__file__).resolve()
    diagnostics_dir = script_path.parent
    if diagnostics_dir.name == "diagnostics" and diagnostics_dir.parent.name == "commands":
        candidate = diagnostics_dir.parent / "governance.paths.json"
        data = _load_json(candidate)
        if data and isinstance(data.get("paths"), dict):
            cfg = data["paths"].get("configRoot")
            if isinstance(cfg, str) and cfg.strip():
                return Path(cfg).expanduser().resolve()

    fallback = default_config_root()
    candidate = fallback / "commands" / "governance.paths.json"
    data = _load_json(candidate)
    if data and isinstance(data.get("paths"), dict):
        cfg = data["paths"].get("configRoot")
        if isinstance(cfg, str) and cfg.strip():
            return Path(cfg).expanduser().resolve()

    return fallback.resolve()


def _validate_repo_fingerprint(value: str) -> str:
    token = value.strip()
    if not token:
        raise ValueError("repo fingerprint must not be empty")
    if not re.fullmatch(r"[A-Za-z0-9._-]{6,128}", token):
        raise ValueError(
            "repo fingerprint must match [A-Za-z0-9._-]{6,128} (no slashes, spaces, or traversal)"
        )
    return token


def repo_session_state_path(config_root: Path, repo_fingerprint: str) -> Path:
    return config_root / "workspaces" / repo_fingerprint / "SESSION_STATE.json"


def session_pointer_path(config_root: Path) -> Path:
    return config_root / "SESSION_STATE.json"


def session_state_template(repo_fingerprint: str, repo_name: str | None) -> dict:
    repository = repo_name.strip() if isinstance(repo_name, str) and repo_name.strip() else repo_fingerprint
    return {
        "SESSION_STATE": {
            "Phase": "1.1-Bootstrap",
            "Mode": "BLOCKED",
            "ConfidenceLevel": 0,
            "Next": "BLOCKED-START-REQUIRED",
            "OutputMode": "ARCHITECT",
            "Bootstrap": {
                "Present": False,
                "Satisfied": False,
                "Evidence": "not-initialized",
            },
            "Scope": {
                "Repository": repository,
                "RepositoryType": "",
                "ExternalAPIs": [],
                "BusinessRules": "not-applicable",
            },
            "LoadedRulebooks": {
                "core": "",
                "profile": "",
                "templates": "",
                "addons": {},
            },
            "AddonsEvidence": {},
            "RulebookLoadEvidence": {
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
                "P5.4-BusinessRules": "not-applicable",
                "P5.5-TechnicalDebt": "pending",
                "P5.6-RollbackSafety": "pending",
                "P6-ImplementationQA": "pending",
            },
            "CreatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
    }


def pointer_payload(repo_fingerprint: str) -> dict:
    return {
        "schema": "opencode-session-pointer.v1",
        "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "activeRepoFingerprint": repo_fingerprint,
        "activeSessionStateFile": f"${{WORKSPACES_HOME}}/{repo_fingerprint}/SESSION_STATE.json",
        "activeSessionStateRelativePath": f"workspaces/{repo_fingerprint}/SESSION_STATE.json",
    }


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
    config_root = resolve_config_root(args.config_root)

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

    repo_state_file = repo_session_state_path(config_root, repo_fingerprint)
    pointer_file = session_pointer_path(config_root)

    print(f"Config root: {config_root}")
    print(f"Repo fingerprint: {repo_fingerprint}")
    print(f"Repo SESSION_STATE file: {repo_state_file}")
    print(f"Global pointer file: {pointer_file}")

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
        return 4

    should_write_repo_state = args.force or not repo_state_file.exists()

    if args.dry_run:
        repo_action = "overwrite" if (repo_state_file.exists() and args.force) else "create"
        if not should_write_repo_state:
            repo_action = "preserve"
        pointer_action = "overwrite" if pointer_file.exists() else "create"

        print(f"[DRY-RUN] Repo SESSION_STATE action: {repo_action} -> {repo_state_file}")
        print(f"[DRY-RUN] Pointer action: {pointer_action} -> {pointer_file}")
        if pointer_has_legacy_payload:
            print("[DRY-RUN] Legacy global payload migration would be applied (requires --force for live write).")
        return 0

    repo_payload: dict
    if should_write_repo_state:
        if pointer_has_legacy_payload and args.force:
            assert isinstance(pointer_existing, dict)
            repo_payload = pointer_existing
            print("Migrating legacy global SESSION_STATE payload to repo-scoped location.")
        else:
            repo_payload = session_state_template(repo_fingerprint, args.repo_name)

        repo_state_file.parent.mkdir(parents=True, exist_ok=True)
        repo_state_file.write_text(json.dumps(repo_payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        print("Repo-scoped SESSION_STATE written.")
    else:
        print("Repo-scoped SESSION_STATE already exists and was preserved (use --force to overwrite).")

    pointer = pointer_payload(repo_fingerprint)
    pointer_file.parent.mkdir(parents=True, exist_ok=True)
    pointer_file.write_text(json.dumps(pointer, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print("Global SESSION_STATE pointer written.")

    if not args.skip_artifact_backfill:
        helper = Path(__file__).resolve().parent / "persist_workspace_artifacts.py"
        if helper.exists():
            cmd = [
                sys.executable,
                str(helper),
                "--repo-fingerprint",
                repo_fingerprint,
                "--config-root",
                str(config_root),
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

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
