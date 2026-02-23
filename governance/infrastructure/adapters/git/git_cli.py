from __future__ import annotations

import subprocess
from pathlib import Path


def resolve_repo_root(cwd: Path | None = None) -> Path | None:
    run = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        text=True,
        capture_output=True,
        check=False,
        cwd=str(cwd) if cwd is not None else None,
    )
    if run.returncode != 0:
        return None
    value = run.stdout.strip()
    return Path(value) if value else None
