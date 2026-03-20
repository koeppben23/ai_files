#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


SKIP_COPY_DIRS = {".git", ".venv", "venv", "dist", "build", "__pycache__", ".pytest_cache", "node_modules"}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Delete governance/ and run smoke gates")
    parser.add_argument("--repo-root", default=".", help="Repository root")
    parser.add_argument("--python", default=sys.executable, help="Python executable")
    return parser.parse_args(argv)


def _copy_repo(src: Path, dst: Path) -> None:
    def _ignore(_dir: str, names: list[str]) -> set[str]:
        return {name for name in names if name in SKIP_COPY_DIRS}

    shutil.copytree(src, dst, ignore=_ignore)


def _run(cmd: list[str], cwd: Path) -> tuple[int, str, str]:
    result = subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True)
    return result.returncode, result.stdout, result.stderr


def run_delete_barrier(repo_root: Path, python_cmd: str) -> list[str]:
    issues: list[str] = []
    with tempfile.TemporaryDirectory(prefix="delete-barrier-") as tmp:
        tmp_root = Path(tmp)
        cloned = tmp_root / "repo"
        config_root = tmp_root / "cfg"
        local_root = tmp_root / "local"
        _copy_repo(repo_root, cloned)

        git_dir = cloned / ".git"
        if not git_dir.exists():
            init = subprocess.run(["git", "init", "-q"], cwd=str(cloned), text=True, capture_output=True)
            if init.returncode != 0:
                git_dir.mkdir(parents=True, exist_ok=True)

        legacy_dir = cloned / "governance"
        if legacy_dir.exists():
            shutil.rmtree(legacy_dir)

        commands = [
            ([python_cmd, "-X", "utf8", "-c", "import governance_runtime.entrypoints.bootstrap_executor"], "import-smoke"),
            ([python_cmd, "-X", "utf8", "scripts/build.py"], "build-smoke"),
            (
                [
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
                ],
                "install-smoke",
            ),
            (
                [
                    python_cmd,
                    "-X",
                    "utf8",
                    "cli/bootstrap.py",
                    "init",
                    "--profile",
                    "solo",
                    "--repo-root",
                    str(cloned),
                    "--config-root",
                    str(config_root),
                ],
                "bootstrap-smoke",
            ),
            (
                [
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
                ],
                "uninstall-smoke",
            ),
        ]

        for cmd, label in commands:
            code, out, err = _run(cmd, cwd=cloned)
            if code != 0:
                issues.append(
                    f"{label} failed (code={code})\ncmd={' '.join(cmd)}\nstdout:\n{out}\nstderr:\n{err}"
                )
    return issues


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    issues = run_delete_barrier(repo_root, args.python)
    if issues:
        print("❌ Delete barrier failed")
        for issue in issues:
            print(f" - {issue}")
        return 1
    print("✅ Delete barrier passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
