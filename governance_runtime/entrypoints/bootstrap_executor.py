#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone
from governance_runtime.application.use_cases.repo_policy_setup import (
    write_governance_mode_config,
    write_repo_operating_mode_policy,
)

try:
    from governance_runtime.infrastructure.path_contract import normalize_absolute_path
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
    parser.add_argument(
        "--compliance-framework",
        default="DEFAULT",
        help="Compliance framework for regulated mode (default: DEFAULT)",
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
        now_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        try:
            policy_path = write_repo_operating_mode_policy(
                repo_root=repo_root,
                profile=selected_profile,
                now_utc=now_utc,
            )
        except Exception as exc:
            print(f"failed to set repo operating mode: {exc}", file=sys.stderr)
            return 2
        print(f"repoOperatingMode = {selected_profile}")
        print(f"resolvedOperatingMode default = {selected_profile}")
        print(f"policyPath = {policy_path}")

        if selected_profile == "regulated":
            try:
                mode_path = write_governance_mode_config(
                    repo_root=repo_root,
                    profile=selected_profile,
                    now_utc=now_utc,
                    compliance_framework=args.compliance_framework,
                )
                if mode_path:
                    print(f"governanceModeState = active")
                    print(f"governanceModePath = {mode_path}")
            except Exception as exc:
                print(f"failed to set regulated mode: {exc}", file=sys.stderr)
                return 2

    ret = subprocess.run(
        [sys.executable, "-m", "governance_runtime.entrypoints.bootstrap_preflight_readonly"],
        env=env,
        cwd=str(repo_root),
    )
    return ret.returncode


if __name__ == "__main__":
    raise SystemExit(main())
