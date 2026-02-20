"""Wave B engine selfcheck primitives.

Selfcheck remains side-effect free and deterministic. It validates a minimal set
of engine contracts required before enabling live engine mode.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_FORBIDDEN_METADATA_NAMES = {"__MACOSX", ".DS_Store", "Icon\r"}

from governance.engine import reason_codes

try:
    from diagnostics.reason_registry_selfcheck import check_reason_registry_parity
except Exception:  # pragma: no cover - optional import path in packaged contexts
    check_reason_registry_parity = None  # type: ignore


@dataclass(frozen=True)
class EngineSelfcheckResult:
    """Deterministic selfcheck result used by runtime gating."""

    ok: bool
    failed_checks: tuple[str, ...]


def _is_forbidden_metadata_entry(path: str) -> bool:
    """Return True when path points to forbidden release metadata payload."""

    parts = Path(path.replace("\\", "/")).parts
    if any(part in _FORBIDDEN_METADATA_NAMES for part in parts):
        return True
    if any(part.startswith("._") for part in parts):
        return True
    return False


def run_engine_selfcheck(*, release_hygiene_entries: tuple[str, ...] = ()) -> EngineSelfcheckResult:
    """Validate minimal invariants required for live engine activation."""

    failed: list[str] = []

    if len(reason_codes.CANONICAL_REASON_CODES) != len(set(reason_codes.CANONICAL_REASON_CODES)):
        failed.append("reason_code_registry_has_duplicates")

    if not reason_codes.is_registered_reason_code(reason_codes.BLOCKED_ENGINE_SELFCHECK, allow_none=False):
        failed.append("missing_blocked_engine_selfcheck_reason")

    if any(_is_forbidden_metadata_entry(entry) for entry in release_hygiene_entries):
        failed.append("release_metadata_hygiene_violation")

    if check_reason_registry_parity is None:
        failed.append("reason_registry_selfcheck_import_failed")
    else:
        parity_ok, parity_errors = check_reason_registry_parity()
        if not parity_ok:
            failed.append("reason_registry_parity_failed")
            if parity_errors:
                failed.append(f"reason_registry_error_count:{len(parity_errors)}")

    return EngineSelfcheckResult(ok=not failed, failed_checks=tuple(failed))
