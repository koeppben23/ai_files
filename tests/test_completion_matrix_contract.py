from __future__ import annotations

from governance_runtime.verification.completion_matrix import build_completion_matrix, is_merge_allowed


def _requirements() -> tuple[dict[str, object], ...]:
    return (
        {"id": "R1", "criticality": "release_blocking"},
        {"id": "R2", "criticality": "important"},
    )


def test_matrix_happy_all_pass() -> None:
    matrix = build_completion_matrix(
        requirements=_requirements(),
        verification_results={
            "R1": {
                "static_verification": "PASS",
                "behavioral_verification": "PASS",
                "user_surface_verification": "PASS",
                "live_flow_verification": "PASS",
                "receipts_verification": "PASS",
            },
            "R2": {
                "static_verification": "PASS",
                "behavioral_verification": "PASS",
                "user_surface_verification": "PASS",
                "live_flow_verification": "PASS",
                "receipts_verification": "PASS",
            },
        },
    )
    assert matrix.overall_status == "PASS"
    ok, reason = is_merge_allowed(matrix.to_dict())
    assert ok is True
    assert reason == "merge_allowed"


def test_matrix_is_unverified_when_any_requirement_is_unverified() -> None:
    matrix = build_completion_matrix(
        requirements=_requirements(),
        verification_results={
            "R1": {
                "static_verification": "PASS",
                "behavioral_verification": "PASS",
                "user_surface_verification": "PASS",
                "live_flow_verification": "UNVERIFIED",
                "receipts_verification": "PASS",
            }
        },
    )
    assert matrix.overall_status == "UNVERIFIED"
    assert "R1" in matrix.release_blocking_requirements_unverified


def test_merge_policy_blocks_when_overall_unverified() -> None:
    ok, reason = is_merge_allowed(
        {
            "overall_status": "UNVERIFIED",
            "completion_matrix": [],
            "release_blocking_requirements_failed": [],
            "release_blocking_requirements_unverified": [],
        }
    )
    assert ok is False
    assert reason == "overall_status=UNVERIFIED"


def test_matrix_edge_missing_statuses_default_to_unverified() -> None:
    matrix = build_completion_matrix(requirements=_requirements(), verification_results={})
    assert matrix.overall_status == "UNVERIFIED"
    assert matrix.completion_matrix[0]["overall"] == "UNVERIFIED"


def test_overall_status_unverified_when_any_requirement_unverified_and_no_failures() -> None:
    matrix = build_completion_matrix(
        requirements=_requirements(),
        verification_results={
            "R1": {
                "static_verification": "PASS",
                "behavioral_verification": "PASS",
                "user_surface_verification": "PASS",
                "live_flow_verification": "PASS",
                "receipts_verification": "UNVERIFIED",
            },
            "R2": {
                "static_verification": "PASS",
                "behavioral_verification": "PASS",
                "user_surface_verification": "PASS",
                "live_flow_verification": "PASS",
                "receipts_verification": "PASS",
            },
        },
    )
    assert matrix.overall_status == "UNVERIFIED"
