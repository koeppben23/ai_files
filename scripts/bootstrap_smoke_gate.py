#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap smoke gate with isolated roots")
    parser.add_argument("--repo-root", default=".", help="Repository root")
    parser.add_argument("--python", default=sys.executable, help="Python executable")
    return parser.parse_args(argv)


def _run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> tuple[int, str, str]:
    result = subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True, env=env)
    return result.returncode, result.stdout, result.stderr


def _ensure_phase_api_projection(*, repo_root: Path, config_root: Path) -> None:
    """Project phase_api.yaml into commands home for bootstrap compatibility."""
    candidates = [
        repo_root / "governance_spec" / "phase_api.yaml",
        repo_root / "phase_api.yaml",
    ]
    src = next((path for path in candidates if path.exists()), None)
    dst = config_root / "commands" / "phase_api.yaml"
    if dst.exists() or src is None:
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")


def run_bootstrap_smoke(repo_root: Path, python_cmd: str) -> list[str]:
    issues: list[str] = []
    with tempfile.TemporaryDirectory(prefix="bootstrap-smoke-") as tmp:
        tmp_root = Path(tmp)
        config_root = tmp_root / "config"
        local_root = tmp_root / "local"

        install_cmd = [
            python_cmd,
            "-X",
            "utf8",
            "install.py",
            "--force",
            "--no-backup",
            "--config-root",
            str(config_root),
            "--local-root",
            str(local_root),
        ]
        code, out, err = _run(install_cmd, repo_root)
        if code != 0:
            issues.append(f"install phase failed (code={code})\nstdout:\n{out}\nstderr:\n{err}")
            return issues

        _ensure_phase_api_projection(repo_root=repo_root, config_root=config_root)

        bootstrap_cmd = [
            python_cmd,
            "-X",
            "utf8",
            "cli/bootstrap.py",
            "init",
            "--profile",
            "solo",
            "--repo-root",
            str(repo_root),
            "--config-root",
            str(config_root),
        ]
        env = dict(os.environ)
        env["COMMANDS_HOME"] = str(config_root / "commands")
        code, out, err = _run(bootstrap_cmd, repo_root, env=env)
        if code != 0:
            issues.append(f"bootstrap phase failed (code={code})\nstdout:\n{out}\nstderr:\n{err}")

        uninstall_cmd = [
            python_cmd,
            "-X",
            "utf8",
            "install.py",
            "--uninstall",
            "--force",
            "--config-root",
            str(config_root),
            "--local-root",
            str(local_root),
        ]
        _run(uninstall_cmd, repo_root)

    return issues


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    issues = run_bootstrap_smoke(repo_root, args.python)
    if issues:
        print("❌ Bootstrap smoke gate failed")
        for issue in issues:
            print(f" - {issue}")
        return 1
    print("✅ Bootstrap smoke gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
