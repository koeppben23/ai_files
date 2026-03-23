"""Engine invariants used by Wave A boundary contracts.

These helpers are intentionally small and side-effect free so they can be used
by future engine wiring without changing current runtime behavior.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RecoveryContractCheck:
    """Validation result for fail-closed recovery contract fields."""

    valid: bool
    reason: str


def check_single_recovery_action(primary_action: str, command: str) -> RecoveryContractCheck:
    """Validate the one-action/one-command fail-closed recovery contract."""

    action = primary_action.strip()
    cmd = command.strip()
    if not action:
        return RecoveryContractCheck(valid=False, reason="primary action must be non-empty")
    if not cmd:
        return RecoveryContractCheck(valid=False, reason="command must be non-empty")
    return RecoveryContractCheck(valid=True, reason="ok")
