#!/usr/bin/env python3
"""
Local bootstrap launcher for OpenCode Governance.

This is the official entry point for repo-specific bootstrap.
Run this before working in a repository to ensure governance is active.

Usage:
    opencode-governance-bootstrap [--repo-root PATH] [--config-root PATH]

Exit codes:
    0 - success
    2 - invalid config / binding / repo missing
    7 - bootstrap failed
    8 - pointer verify failed
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


def _get_bootstrap_module():
    """Lazy import of cli.bootstrap to allow sys.path manipulation first."""
    import cli.bootstrap
    return cli.bootstrap


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="OpenCode Governance Local Bootstrap Launcher"
    )
    parser.add_argument(
        "--repo-root",
        help="Repository root path (default: auto-detect via git)",
    )
    parser.add_argument(
        "--config-root",
        help="OpenCode config root (default: ~/.config/opencode)",
    )
    return parser


def _resolve_config_root(user_provided: str | None) -> Path:
    if user_provided:
        return Path(user_provided).expanduser().resolve()
    return Path(os.path.expanduser("~/.config/opencode"))


def _resolve_repo_root(user_provided: str | None) -> Path | None:
    if user_provided:
        return Path(user_provided).resolve()

    env_repo_root = os.environ.get("OPENCODE_REPO_ROOT")
    if env_repo_root:
        return Path(env_repo_root).resolve()

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        return Path(result.stdout.strip()).resolve()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _compute_fingerprint(repo_root: Path) -> str:
    path_str = str(repo_root.resolve())
    return hashlib.sha256(path_str.encode()).hexdigest()[:24]


def _resolve_binding(config_root: Path) -> dict | None:
    binding_path = config_root / "commands" / "governance.paths.json"
    if not binding_path.exists():
        return None

    try:
        with open(binding_path) as f:
            data = json.load(f)

        if data.get("schema") != "opencode-governance.paths.v1":
            return None

        paths = data.get("paths", {})
        required = ["configRoot", "commandsHome", "workspacesHome"]
        if not all(paths.get(k) for k in required):
            return None

        return data
    except (json.JSONDecodeError, IOError):
        return None


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    # Pre-emptively add repo_root to sys.path for module imports
    # This must happen before any cli.* imports
    potential_repo_root = _resolve_repo_root(args.repo_root)
    if potential_repo_root:
        repo_root_str = str(potential_repo_root)
        if repo_root_str not in sys.path:
            sys.path.insert(0, repo_root_str)

    config_root = _resolve_config_root(args.config_root)
    repo_root = _resolve_repo_root(args.repo_root)

    print("=" * 60)
    print("OpenCode Governance Bootstrap Launcher")
    print("=" * 60)

    binding = _resolve_binding(config_root)
    if not binding:
        print("ERROR: Invalid or missing binding file.")
        print(f"  Expected: {config_root}/commands/governance.paths.json")
        print("  Run 'python install.py' to set up governance.")
        return 2

    paths = binding["paths"]
    commands_home = paths.get("commandsHome")
    workspaces_home = paths.get("workspacesHome")
    python_command = paths.get("pythonCommand", sys.executable)

    print(f"Config root: {config_root}")
    print(f"Commands home: {commands_home}")

    if not repo_root:
        print("ERROR: Repository root not found.")
        print("  Provide --repo-root or run from within a Git repository.")
        return 2

    print(f"Repo root: {repo_root}")

    if not (repo_root / ".git").exists():
        print("ERROR: Not a Git repository.")
        return 2

    repo_fingerprint = _compute_fingerprint(repo_root)
    repo_name = repo_root.name or "repo"

    print(f"Repo fingerprint: {repo_fingerprint}")
    print(f"Repo name: {repo_name}")
    print("-" * 60)

    bootstrap_args = [
        "--repo-root", str(repo_root),
        "--repo-fingerprint", repo_fingerprint,
        "--repo-name", repo_name,
        "--config-root", str(config_root),
        "--workspaces-home", workspaces_home,
        "--python-command", python_command,
    ]

    bootstrap = _get_bootstrap_module()
    return bootstrap.main(bootstrap_args)


if __name__ == "__main__":
    raise SystemExit(main())
