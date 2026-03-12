"""Completion matrix engine (PASS/FAIL/UNVERIFIED fail-closed policy)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

_VALID = {"PASS", "FAIL", "UNVERIFIED"}


@dataclass(frozen=True)
class CompletionMatrixResult:
    completion_matrix: tuple[dict[str, str], ...]
    overall_status: str
    release_blocking_requirements_failed: tuple[str, ...]
    release_blocking_requirements_unverified: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "completion_matrix": [dict(item) for item in self.completion_matrix],
            "overall_status": self.overall_status,
            "release_blocking_requirements_failed": list(self.release_blocking_requirements_failed),
            "release_blocking_requirements_unverified": list(self.release_blocking_requirements_unverified),
        }


def _normalize_status(value: object) -> str:
    token = str(value or "UNVERIFIED").strip().upper()
    return token if token in _VALID else "UNVERIFIED"


def build_completion_matrix(
    *,
    requirements: tuple[Mapping[str, object], ...],
    verification_results: Mapping[str, Mapping[str, object]],
) -> CompletionMatrixResult:
    rows: list[dict[str, str]] = []
    release_failed: list[str] = []
    release_unverified: list[str] = []

    for contract in requirements:
        req_id = str(contract.get("id") or "").strip()
        criticality = str(contract.get("criticality") or "normal").strip()
        result = verification_results.get(req_id, {})

        static = _normalize_status(result.get("static_verification"))
        behavioral = _normalize_status(result.get("behavioral_verification"))
        user_surface = _normalize_status(result.get("user_surface_verification"))
        live_flow = _normalize_status(result.get("live_flow_verification"))
        receipts = _normalize_status(result.get("receipts_verification"))

        statuses = (static, behavioral, user_surface, live_flow, receipts)
        if "FAIL" in statuses:
            overall = "FAIL"
        elif "UNVERIFIED" in statuses:
            overall = "UNVERIFIED"
        else:
            overall = "PASS"

        row = {
            "id": req_id,
            "static_verification": static,
            "behavioral_verification": behavioral,
            "user_surface_verification": user_surface,
            "live_flow_verification": live_flow,
            "receipts_verification": receipts,
            "overall": overall,
        }
        rows.append(row)

        if criticality == "release_blocking" and overall == "FAIL":
            release_failed.append(req_id)
        if criticality == "release_blocking" and overall == "UNVERIFIED":
            release_unverified.append(req_id)

    if any(row["overall"] != "PASS" for row in rows):
        overall_status = "FAIL"
    else:
        overall_status = "PASS"

    return CompletionMatrixResult(
        completion_matrix=tuple(rows),
        overall_status=overall_status,
        release_blocking_requirements_failed=tuple(release_failed),
        release_blocking_requirements_unverified=tuple(release_unverified),
    )


def is_merge_allowed(matrix: Mapping[str, object]) -> tuple[bool, str]:
    """Fail-closed merge policy for contract verification state."""
    overall = _normalize_status(matrix.get("overall_status"))
    if overall != "PASS":
        return False, f"overall_status={overall}"

    unverified = matrix.get("release_blocking_requirements_unverified")
    if isinstance(unverified, list) and unverified:
        return False, "release_blocking_requirements_unverified"
    failed = matrix.get("release_blocking_requirements_failed")
    if isinstance(failed, list) and failed:
        return False, "release_blocking_requirements_failed"

    rows = matrix.get("completion_matrix")
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, Mapping):
                if _normalize_status(row.get("overall")) in {"FAIL", "UNVERIFIED"}:
                    return False, f"requirement_not_pass:{row.get('id') or 'unknown'}"
    return True, "merge_allowed"
