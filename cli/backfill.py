from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from typing import Optional


REPO_ROOT = Path(__file__).resolve().parents[1]


def main(argv: Optional[list[str]] = None) -> int:
    forward_args = argv if argv is not None else sys.argv[1:]
    env = os.environ.copy()
    run = subprocess.run(
        [sys.executable, "-m", "governance_runtime.cli.backfill", *forward_args],
        cwd=str(REPO_ROOT),
        env=env,
        text=True,
        capture_output=True,
    )
    if run.stdout:
        print(run.stdout, end="")
    if run.stderr:
        print(run.stderr, end="", file=sys.stderr)
    return int(run.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
