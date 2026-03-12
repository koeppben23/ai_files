"""Verifier pipeline coordinator (D1-D4 + receipts verification)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from governance.verification.completion_matrix import CompletionMatrixResult, build_completion_matrix


@dataclass(frozen=True)
class VerifierRunResult:
    matrix: CompletionMatrixResult
    status: str


def run_verifier_pipeline(
    *,
    requirements: tuple[Mapping[str, object], ...],
    static_results: Mapping[str, str],
    behavioral_results: Mapping[str, str],
    user_surface_results: Mapping[str, str],
    live_flow_results: Mapping[str, str],
    receipts_results: Mapping[str, str],
) -> VerifierRunResult:
    merged: dict[str, dict[str, str]] = {}

    for req in requirements:
        req_id = str(req.get("id") or "").strip()
        merged[req_id] = {
            "static_verification": static_results.get(req_id, "UNVERIFIED"),
            "behavioral_verification": behavioral_results.get(req_id, "UNVERIFIED"),
            "user_surface_verification": user_surface_results.get(req_id, "UNVERIFIED"),
            "live_flow_verification": live_flow_results.get(req_id, "UNVERIFIED"),
            "receipts_verification": receipts_results.get(req_id, "UNVERIFIED"),
        }

    matrix = build_completion_matrix(requirements=requirements, verification_results=merged)
    overall = str(matrix.overall_status or "FAIL").upper()
    if overall in {"PASS", "FAIL", "UNVERIFIED"}:
        status = overall
    else:
        status = "FAIL"
    return VerifierRunResult(matrix=matrix, status=status)
