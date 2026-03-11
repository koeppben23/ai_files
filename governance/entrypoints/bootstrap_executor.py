#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

from governance.application.repo_identity_service import derive_repo_identity

try:
    from governance.infrastructure.path_contract import normalize_absolute_path
except Exception:  # pragma: no cover
    normalize_absolute_path = None  # type: ignore


def _normalize_path(raw: str, *, purpose: str) -> Path:
    token = str(raw or "").strip()
    if not token:
        raise ValueError(f"{purpose}: empty path")
    if callable(normalize_absolute_path):
        return normalize_absolute_path(token, purpose=purpose)
    candidate = Path(token).expanduser()
    if not candidate.is_absolute():
        raise ValueError(f"{purpose}: path must be absolute")
    return Path(os.path.normpath(os.path.abspath(str(candidate))))


def _validate_repo_root(raw: str) -> Path:
    repo_root = _normalize_path(raw, purpose="repo_root")
    if not repo_root.exists() or not repo_root.is_dir():
        raise ValueError("repo_root: path does not exist or is not a directory")
    git_marker = repo_root / ".git"
    if git_marker.exists():
        return repo_root
    for parent in repo_root.parents:
        if (parent / ".git").exists():
            return parent
    raise ValueError("repo_root: missing .git")


def _validate_config_root(raw: str) -> Path:
    config_root = _normalize_path(raw, purpose="config_root")
    if not config_root.exists() or not config_root.is_dir():
        raise ValueError("config_root: path does not exist or is not a directory")
    return config_root


def _write_repo_operating_mode_policy(*, repo_root: Path, profile: str) -> Path:
    profile_token = str(profile or "").strip().lower()
    if profile_token not in {"solo", "team", "regulated"}:
        raise ValueError("profile must be one of: solo, team, regulated")

    policy_path = repo_root / ".opencode" / "governance-repo-policy.json"
    policy_path.parent.mkdir(parents=True, exist_ok=True)

    existing_created_at = ""
    if policy_path.exists() and policy_path.is_file():
        try:
            existing_payload = json.loads(policy_path.read_text(encoding="utf-8"))
        except Exception as exc:  # pragma: no cover - defensive parse guard
            raise ValueError(f"existing repo policy is invalid JSON: {exc}") from exc
        if isinstance(existing_payload, dict):
            existing_created_at = str(existing_payload.get("createdAt") or "").strip()

    identity = derive_repo_identity(repo_root, canonical_remote=None, git_dir=None)
    created_at = existing_created_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    payload = {
        "schema": "opencode-governance-repo-policy.v1",
        "repoFingerprint": str(identity.fingerprint or ""),
        "operatingMode": profile_token,
        "source": "bootstrap-cli-init",
        "createdAt": created_at,
    }
    policy_path.write_text(json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return policy_path


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="opencode-governance-bootstrap",
        description="Execute bootstrap preflight until ready for Phase 4",
    )
    parser.add_argument("command", nargs="?", choices=("init",), help="Bootstrap command (recommended: init)")
    parser.add_argument("--config-root", help="Path to OpenCode config root", required=False)
    parser.add_argument("--repo-root", help="Path to repository root", required=True)
    parser.add_argument("--profile", choices=("solo", "team", "regulated"), help="Operating mode profile for init")
    parser.add_argument(
        "--set-operating-mode",
        choices=("solo", "team", "regulated"),
        help="Alias for setting repo operating mode (admin alternative)",
    )
    args = parser.parse_args()

    if args.profile and args.command != "init":
        parser.error("--profile is supported with 'init' (recommended canonical setup path)")

    selected_profile = str(args.profile or args.set_operating_mode or "").strip().lower() or None
    if args.command == "init" and selected_profile is None:
        parser.error("init requires --profile {solo,team,regulated}")

    try:
        repo_root = _validate_repo_root(args.repo_root)
    except Exception as exc:
        print(f"invalid --repo-root: {exc}", file=sys.stderr)
        return 2

    env = os.environ.copy()
    if args.config_root:
        try:
            config_root = _validate_config_root(args.config_root)
        except Exception as exc:
            print(f"invalid --config-root: {exc}", file=sys.stderr)
            return 2
        env["OPENCODE_CONFIG_ROOT"] = str(config_root)
        env["COMMANDS_HOME"] = str(config_root / "commands")

    env["OPENCODE_REPO_ROOT"] = str(repo_root)

    if selected_profile is not None:
        try:
            policy_path = _write_repo_operating_mode_policy(repo_root=repo_root, profile=selected_profile)
        except Exception as exc:
            print(f"failed to set repo operating mode: {exc}", file=sys.stderr)
            return 2
        print(f"repoOperatingMode = {selected_profile}")
        print(f"resolvedOperatingMode default = {selected_profile}")
        print(f"policyPath = {policy_path}")

    ret = subprocess.run(
        [sys.executable, "-m", "governance.entrypoints.bootstrap_preflight_readonly"],
        env=env,
        cwd=str(repo_root),
    )
    return ret.returncode


if __name__ == "__main__":
    raise SystemExit(main())
