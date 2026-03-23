from __future__ import annotations

from governance_runtime.verification.completion_matrix import is_merge_allowed


def test_merge_blocked_when_any_requirement_unverified() -> None:
    ok, reason = is_merge_allowed(
        {
            "overall_status": "FAIL",
            "completion_matrix": [
                {
                    "id": "R-NEXT-ACTION-001",
                    "static_verification": "PASS",
                    "behavioral_verification": "PASS",
                    "user_surface_verification": "PASS",
                    "live_flow_verification": "UNVERIFIED",
                    "receipts_verification": "PASS",
                    "overall": "UNVERIFIED",
                }
            ],
            "release_blocking_requirements_failed": [],
            "release_blocking_requirements_unverified": ["R-NEXT-ACTION-001"],
        }
    )
    assert ok is False
    assert reason == "overall_status=FAIL"
