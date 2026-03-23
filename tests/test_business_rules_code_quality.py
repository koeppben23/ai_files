from __future__ import annotations

from governance_runtime.engine.business_rules_validation import (
    ORIGIN_CODE,
    REASON_CODE_TEMPLATE_OVERFIT,
    REASON_CODE_TOKEN_ARTIFACT,
    RuleCandidate,
    validate_candidates,
)


def _candidate(text: str) -> RuleCandidate:
    return RuleCandidate(
        text=text,
        source_path="src/policy.py",
        line_no=10,
        source_allowed=True,
        source_reason="deterministic-code-extraction",
        section_signal=True,
        origin=ORIGIN_CODE,
        enforcement_anchor_type="validator",
        semantic_type="permission",
    )


def test_code_token_artifacts_rejected() -> None:
    report = validate_candidates(
        candidates=[
            _candidate("BR-C001: Permission checks must be enforced for from dataclasses import dataclass"),
            _candidate("BR-C002: Required field checks must be enforced for not helper exists"),
            _candidate("BR-C003: Invariants must be enforced for dataclass frozen true"),
            _candidate("BR-C004: Metadata segments must avoid __macosx __pycache__ _backup"),
            _candidate("BR-C005: Permission checks must be enforced for src/policy.py"),
            _candidate("BR-C006: Required field checks must be enforced for archived_files"),
        ],
        expected_rules=False,
        has_code_extraction=True,
        code_extraction_sufficient=True,
        code_candidate_count=4,
        enforce_code_requirements=True,
    )

    assert report.valid_rule_count == 0
    assert report.has_code_token_artifacts is True
    # Some rules may be caught by NON_BUSINESS_SUBJECT (e.g., "field", "metadata")
    # others by TEMPLATE_OVERFIT or CODE_TOKEN_ARTIFACT
    assert report.template_overfit_count >= 1 or report.code_token_artifact_count >= 1
