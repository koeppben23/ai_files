"""Wave B engine selfcheck primitives.

Selfcheck remains side-effect free and deterministic. It validates a minimal set
of engine contracts required before enabling live engine mode.
"""

from __future__ import annotations

from dataclasses import dataclass

from governance.engine import reason_codes


@dataclass(frozen=True)
class EngineSelfcheckResult:
    """Deterministic selfcheck result used by runtime gating."""

    ok: bool
    failed_checks: tuple[str, ...]


def run_engine_selfcheck() -> EngineSelfcheckResult:
    """Validate minimal invariants required for live engine activation."""

    failed: list[str] = []

    if len(reason_codes.CANONICAL_REASON_CODES) != len(set(reason_codes.CANONICAL_REASON_CODES)):
        failed.append("reason_code_registry_has_duplicates")

    if not reason_codes.is_registered_reason_code(reason_codes.BLOCKED_ENGINE_SELFCHECK, allow_none=False):
        failed.append("missing_blocked_engine_selfcheck_reason")

    return EngineSelfcheckResult(ok=not failed, failed_checks=tuple(failed))
