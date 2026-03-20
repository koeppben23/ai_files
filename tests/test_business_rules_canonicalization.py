from __future__ import annotations

from governance_runtime.engine.business_rules_hydration import (
    build_business_rules_state_snapshot,
    canonicalize_business_rules_outcome,
    has_br_signal,
)


def test_happy_canonicalize_extracted_when_final_report_passes() -> None:
    outcome = canonicalize_business_rules_outcome(
        declared_outcome="extracted",
        extracted_allowed=True,
        final_report_available=True,
        br_signal=True,
    )
    assert outcome == "extracted"


def test_bad_legacy_with_execution_signal_maps_to_gap_detected() -> None:
    signal = has_br_signal(
        declared_outcome="not-applicable",
        report=None,
        persistence_result={"execution_evidence": True},
    )
    assert signal is True
    outcome = canonicalize_business_rules_outcome(
        declared_outcome="not-applicable",
        extracted_allowed=False,
        final_report_available=False,
        br_signal=signal,
    )
    assert outcome == "gap-detected"


def test_corner_legacy_without_any_signal_maps_to_unresolved() -> None:
    signal = has_br_signal(
        declared_outcome="deferred",
        report=None,
        persistence_result={},
    )
    assert signal is False
    outcome = canonicalize_business_rules_outcome(
        declared_outcome="deferred",
        extracted_allowed=False,
        final_report_available=False,
        br_signal=signal,
    )
    assert outcome == "unresolved"


def test_edge_snapshot_persists_has_signal_and_canonical_outcome() -> None:
    snapshot = build_business_rules_state_snapshot(
        report={
            "is_compliant": False,
            "valid_rule_count": 0,
            "invalid_rule_count": 0,
            "dropped_candidate_count": 0,
            "count_consistent": False,
            "has_render_mismatch": False,
            "has_invalid_rules": False,
            "has_code_extraction": False,
            "code_extraction_sufficient": False,
            "reason_codes": [],
        },
        persistence_result={
            "declared_outcome": "skipped",
            "report_finalized": False,
            "execution_evidence": True,
            "extraction_ran": False,
            "inventory_written": False,
            "inventory_file_status": "withheld",
        },
    )

    assert snapshot["Outcome"] == "gap-detected"
    assert snapshot["HasSignal"] is True
