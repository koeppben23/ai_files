#!/usr/bin/env python3
import sys
from pathlib import Path
from typing import Optional


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main(argv: Optional[list[str]] = None) -> int:
    try:
        from governance_runtime.entrypoints.bootstrap_executor import main as executor_main
    except Exception as exc:
        print("Bootstrap launcher error:", exc, file=sys.stderr)
        return 1
    if argv is not None:
        sys.argv = [sys.argv[0], *argv]
    try:
        return int(executor_main())
    except SystemExit as exc:
        return int(getattr(exc, "code", 1) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
