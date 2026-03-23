#!/usr/bin/env python3
"""Thin CLI wrapper for new governance work-run initialization.

Usage:
  python scripts/governance_session_new.py --trigger-source pipeline --reason "nightly"
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).absolute().parents[1]))

from governance_runtime.entrypoints.new_work_session import main as new_work_session_main


def main() -> int:
    return new_work_session_main(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
