from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str], *, env: dict[str, str] | None = None, cwd: Path | None = None) -> subprocess.CompletedProcess:
    e = os.environ.copy()
    if env:
        e.update(env)
    return subprocess.run(
        cmd,
        cwd=str(cwd or REPO_ROOT),
        env=e,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def run_install(args: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    # Always use the current interpreter (matrix python-version).
    return run([sys.executable, "-X", "utf8", "install.py", *args], env=env)


def run_build(args: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    # Build artifacts deterministically via scripts/build.py
    return run([sys.executable, "scripts/build.py", *args], env=env)


def git_ls_files(*patterns: str) -> list[str]:
    cmd = ["git", "ls-files"]
    if patterns:
        cmd += list(patterns)
    r = run(cmd)
    if r.returncode != 0:
        raise RuntimeError(f"git ls-files failed: {r.stderr}\n{r.stdout}")
    return [l for l in r.stdout.splitlines() if l.strip()]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def sha256_file(p: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def is_flag_supported(flag: str) -> bool:
    r = run_install(["--help"])
    return flag in (r.stdout or "")
