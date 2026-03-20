from __future__ import annotations

from pathlib import Path

from governance_runtime.engine.business_rules_validation import (
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


def test_golden_extraction_matches_expected_rules_exactly(tmp_path: Path) -> None:
    _write(
        tmp_path / "docs" / "business-policy.md",
        "# Policy\n"
        "## Business Rules\n"
        "- BR-100: Access must be authenticated for all write operations\n"
        "- BR-101: Audit entries must not be changed after persistence\n"
        "- BR-102: A release must require a four-eyes approval\n",
    )

    report, ok = extract_validated_business_rules_from_repo(tmp_path)

    assert ok is True
    assert report.is_compliant is True
    extracted = [row.text for row in report.valid_rules]
    assert extracted == [
        "BR-100: Access must be authenticated for all write operations",
        "BR-101: Audit entries must not be changed after persistence",
        "BR-102: A release must require a four-eyes approval",
    ]


def test_source_allowlist_requires_section_context_signal(tmp_path: Path) -> None:
    _write(
        tmp_path / "docs" / "random.md",
        "# Changelog\n"
        "- BR-050: This must not be accepted without rule context\n",
    )

    report, ok = extract_validated_business_rules_from_repo(tmp_path)

    assert ok is True
    assert report.valid_rule_count == 0
    assert report.has_source_violation is True


def test_render_consistency_mismatch_is_fail_closed() -> None:
    candidates = [
        RuleCandidate(
            text="BR-201: Access must be checked before processing payments",
            source_path="docs/policy.md",
            line_no=11,
            source_allowed=True,
            source_reason="allowed",
            section_signal=True,
        )
    ]

    report = validate_candidates(
        candidates=candidates,
        rendered_rules=["BR-999: Audit entries must be immutable"],
    )

    assert report.is_compliant is False
    assert report.has_render_mismatch is True
    assert report.count_consistent is True


def test_edge_missing_required_rule_ids_blocks() -> None:
    candidates = [
        RuleCandidate(
            text="BR-301: Access must be authenticated",
            source_path="docs/policy.md",
            line_no=3,
            source_allowed=True,
            source_reason="allowed",
            section_signal=True,
        )
    ]

    report = validate_candidates(
        candidates=candidates,
        required_rule_ids={"BR-301", "BR-302"},
    )

    assert report.is_compliant is False
    assert report.has_missing_required_rules is True
