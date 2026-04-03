"""Fail-closed contract enforcement for governance gates."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from governance_runtime.contracts.registry import load_and_validate_contracts


FAIL_CLOSED_MISSING_CONTRACT = "FAIL_CLOSED: MISSING_CONTRACT"


@dataclass(frozen=True)
class EnforcementResult:
    ok: bool
    reason: str
    details: tuple[str, ...]


def require_complete_contracts(
    *,
    repo_root: Path,
    required_ids: Iterable[str] = (),
) -> EnforcementResult:
    try:
        loaded = load_and_validate_contracts(repo_root)
    except (OSError, json.JSONDecodeError, ValueError) as exc:  # Fail-closed: contracts must load
        return EnforcementResult(
            ok=False,
            reason=FAIL_CLOSED_MISSING_CONTRACT,
            details=(f"contract_load_failed:{exc}",),
        )

    if not loaded.contracts:
        return EnforcementResult(
            ok=False,
            reason=FAIL_CLOSED_MISSING_CONTRACT,
            details=("no_requirement_contracts_found",),
        )

    if not loaded.validation.ok:
        return EnforcementResult(
            ok=False,
            reason=FAIL_CLOSED_MISSING_CONTRACT,
            details=tuple(str(err) for err in loaded.validation.errors),
        )

    ids = {str(item.get("id") or "").strip() for item in loaded.contracts if isinstance(item, dict)}
    missing = [req_id for req_id in required_ids if str(req_id).strip() and str(req_id).strip() not in ids]
    if missing:
        return EnforcementResult(
            ok=False,
            reason=FAIL_CLOSED_MISSING_CONTRACT,
            details=tuple(f"missing_required_contract:{entry}" for entry in missing),
        )

    return EnforcementResult(ok=True, reason="ready", details=())
