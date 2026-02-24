"""Compatibility wrapper for reason registry selfcheck."""

from __future__ import annotations

from pathlib import Path

from governance.infrastructure.reason_registry_selfcheck import (
    check_reason_registry_parity,
    run_reason_registry_selfcheck,
)

__all__ = ["check_reason_registry_parity", "run_reason_registry_selfcheck", "Path"]


if __name__ == "__main__":
    run_reason_registry_selfcheck()
