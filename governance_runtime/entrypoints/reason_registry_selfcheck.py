"""Compatibility wrapper for reason registry selfcheck."""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).absolute().parents[2]))


from pathlib import Path

from governance_runtime.infrastructure.reason_registry_selfcheck import (
    check_reason_registry_parity,
    run_reason_registry_selfcheck,
)

__all__ = ["check_reason_registry_parity", "run_reason_registry_selfcheck", "Path"]


if __name__ == "__main__":
    run_reason_registry_selfcheck()
