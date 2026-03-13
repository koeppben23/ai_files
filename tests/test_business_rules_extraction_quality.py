from __future__ import annotations

from pathlib import Path

from governance.engine.business_rules_validation import (
    RuleCandidate,
    extract_validated_business_rules_from_repo,
    validate_candidates,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_happy_source_aware_extraction_keeps_business_rules(tmp_path: Path) -> None:
    _write(
        tmp_path / "docs" / "business-rules.md",
        "# Business Rules\n"
        "- BR-001: Access must be authenticated before data access\n"
        "- BR-002: Audit entries must not be modified after write\n",
    )

    report, ok = extract_validated_business_rules_from_repo(tmp_path)

    assert ok is True
    assert report.is_compliant is True
    assert report.valid_rule_count == 2
    assert report.invalid_rule_count == 0


def test_bad_source_filtering_rejects_test_files(tmp_path: Path) -> None:
    _write(
        tmp_path / "tests" / "test_rules.md",
        "# tests\n- BR-777: This must never be used as a business rule\n",
    )

    report, ok = extract_validated_business_rules_from_repo(tmp_path)

    assert ok is True
    assert report.is_compliant is False
    assert report.valid_rule_count == 0
    assert report.has_source_violation is True


def test_corner_segmentation_splits_glued_rules_deterministically() -> None:
    candidates = [
        RuleCandidate(
            text='BR-001: Access must be checked\\n- BR-002: Audit is mandatory',
            source_path="docs/policy.md",
            line_no=4,
            source_allowed=True,
            source_reason="allowed",
            section_signal=True,
        )
    ]

    report = validate_candidates(candidates=candidates)

    assert report.valid_rule_count == 2
    assert report.invalid_rule_count == 0
    assert report.has_segmentation_failure is False


def test_edge_unsegmentable_candidate_is_reported() -> None:
    candidates = [
        RuleCandidate(
            text='BR-010 Access must be checked\\n")',
            source_path="docs/policy.md",
            line_no=9,
            source_allowed=True,
            source_reason="allowed",
            section_signal=True,
        )
    ]

    report = validate_candidates(candidates=candidates)

    assert report.is_compliant is False
    assert report.valid_rule_count == 0
    assert report.has_segmentation_failure is True
