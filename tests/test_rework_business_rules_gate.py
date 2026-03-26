from __future__ import annotations

from governance_runtime.entrypoints.session_reader import _normalize_phase6_p5_state


def test_rework_e2e_changes_requested_still_blocks_on_invalid_business_rules() -> None:
    state_doc = {
        "SESSION_STATE": {
            "phase": "6-PostFlight",
            "next": "6",
            "phase6_state": "6.rework",
            "active_gate": "Rework Clarification Gate",
            "BusinessRules": {
                "Outcome": "extracted",
                "ExecutionEvidence": True,
                "InventoryLoaded": True,
                "ExtractedCount": 2,
                "InvalidRuleCount": 1,
                "DroppedCandidateCount": 1,
                "ValidationReasonCodes": [
                    "BUSINESS_RULES_INVALID_CONTENT",
                    "BUSINESS_RULES_RENDER_MISMATCH",
                ],
                "ValidationReport": {
                    "is_compliant": False,
                    "has_invalid_rules": True,
                    "has_render_mismatch": True,
                    "has_source_violation": False,
                    "has_missing_required_rules": False,
                    "has_segmentation_failure": False,
                    "invalid_rule_count": 1,
                    "dropped_candidate_count": 1,
                    "count_consistent": False,
                },
            },
            "Gates": {
                "P5-Architecture": "approved",
                "P5.3-TestQuality": "pass",
                "P5.4-BusinessRules": "compliant",
                "P5.5-TechnicalDebt": "approved",
            },
        }
    }

    _normalize_phase6_p5_state(state_doc=state_doc)

    ss = state_doc["SESSION_STATE"]
    assert ss["phase"] == "5.4-BusinessRules"
    assert ss["next"] == "5.4"
    assert ss["phase6_state"] in ("", "6.none", "phase5_in_progress")
    assert "BLOCKED-P5-4-BUSINESS-RULES-GATE" in ss["next_gate_condition"]


def test_rework_e2e_changes_requested_blocks_on_code_coverage_gap() -> None:
    state_doc = {
        "SESSION_STATE": {
            "phase": "6-PostFlight",
            "next": "6",
            "phase6_state": "6.rework",
            "active_gate": "Rework Clarification Gate",
            "BusinessRules": {
                "Outcome": "extracted",
                "ExecutionEvidence": True,
                "InventoryLoaded": True,
                "ExtractedCount": 2,
                "ValidationReasonCodes": ["BUSINESS_RULES_CODE_COVERAGE_INSUFFICIENT"],
                "CodeSurfaceCount": 6,
                "MissingCodeSurfaces": ["validator", "workflow"],
                "ValidationReport": {
                    "is_compliant": False,
                    "has_invalid_rules": False,
                    "has_render_mismatch": False,
                    "has_source_violation": False,
                    "has_missing_required_rules": False,
                    "has_segmentation_failure": False,
                    "has_code_extraction": True,
                    "code_extraction_sufficient": False,
                    "has_code_coverage_gap": True,
                    "has_code_doc_conflict": False,
                    "code_surface_count": 6,
                    "missing_code_surfaces": ["validator", "workflow"],
                },
            },
            "Gates": {
                "P5-Architecture": "approved",
                "P5.3-TestQuality": "pass",
                "P5.4-BusinessRules": "compliant",
                "P5.5-TechnicalDebt": "approved",
            },
        }
    }

    _normalize_phase6_p5_state(state_doc=state_doc)

    ss = state_doc["SESSION_STATE"]
    assert ss["phase"] == "5.4-BusinessRules"
    assert ss["phase6_state"] in ("", "6.none", "phase5_in_progress")
    assert "BLOCKED-P5-4-BUSINESS-RULES-GATE" in ss["next_gate_condition"]
