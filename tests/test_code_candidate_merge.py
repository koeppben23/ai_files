"""Tests for merge_code_candidates() — merging LLM-sourced code candidates with doc-extracted rules.

Covers: Happy (4), Bad (6), Corner (5), Edge (5) = 20 tests.
"""

from __future__ import annotations

import pytest

from governance_runtime.engine.business_rules_validation import (
    ORIGIN_CODE,
    ORIGIN_DOC,
    REASON_CODE_CANDIDATE_REJECTED,
    ProvenanceRecord,
    RejectedRule,
    RuleCandidate,
    ValidatedRule,
    merge_code_candidates,
    sanitize_rule,
    validate_candidates,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _doc_rule(rule_id: str, text: str, path: str = "docs/rules.md", line: int = 10) -> ValidatedRule:
    return ValidatedRule(rule_id=rule_id, text=text, source_path=path, line_no=line, origin=ORIGIN_DOC)


def _code_candidate(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": "BR-C001",
        "candidate_rule_text": "BR-C001: Withdrawal amount must not exceed the daily limit",
        "source_path": "src/main/java/com/bank/WithdrawalService.java",
        "line_range": "42-48",
        "pattern_type": "validation-guard",
        "confidence": "high",
        "evidence_snippet": "if (amount > MAX_DAILY) throw ...",
    }
    base.update(overrides)
    return base


# ===========================================================================
# Happy-path tests
# ===========================================================================

@pytest.mark.governance
class TestMergeCodeCandidatesHappy:

    def test_single_valid_code_candidate_merged_with_empty_doc_rules(self) -> None:
        """A valid code candidate should produce one RuleCandidate with origin=code."""
        merged, rejected, provenance = merge_code_candidates(
            code_candidates=[_code_candidate()],
            existing_doc_rules=[],
        )
        assert len(rejected) == 0
        assert len(merged) == 1
        assert merged[0].origin == ORIGIN_CODE
        assert merged[0].source_reason == "llm-code-extraction"
        assert "daily limit" in merged[0].text.lower()

    def test_code_candidate_merged_alongside_existing_doc_rules(self) -> None:
        """Code candidates should appear after doc rules in the merged list."""
        doc_rules = [
            _doc_rule("BR-001", "BR-001: All transfers must include a reference number"),
        ]
        code = [_code_candidate(
            id="BR-C001",
            candidate_rule_text="BR-C001: Withdrawal amount must not exceed the daily limit",
        )]
        merged, rejected, provenance = merge_code_candidates(
            code_candidates=code, existing_doc_rules=doc_rules,
        )
        assert len(rejected) == 0
        assert len(merged) == 2
        assert merged[0].origin == ORIGIN_DOC
        assert merged[1].origin == ORIGIN_CODE

    def test_multiple_valid_code_candidates_all_accepted(self) -> None:
        """Three distinct valid candidates should all pass through."""
        candidates = [
            _code_candidate(
                id="BR-C001",
                candidate_rule_text="BR-C001: Withdrawal amount must not exceed the daily limit",
            ),
            _code_candidate(
                id="BR-C002",
                candidate_rule_text="BR-C002: Order status must be PENDING before approval",
                pattern_type="enum-invariant",
            ),
            _code_candidate(
                id="BR-C003",
                candidate_rule_text="BR-C003: Account holder name is required for all transfers",
                pattern_type="constraint-check",
            ),
        ]
        merged, rejected, provenance = merge_code_candidates(
            code_candidates=candidates, existing_doc_rules=[],
        )
        assert len(rejected) == 0
        assert len(merged) == 3
        assert all(c.origin == ORIGIN_CODE for c in merged)

    def test_merged_candidates_pass_through_validate_candidates(self) -> None:
        """Merged RuleCandidates must be consumable by the deterministic validation pipeline."""
        candidates = [
            _code_candidate(
                id="BR-C001",
                candidate_rule_text="BR-C001: Withdrawal amount must not exceed the daily limit",
            ),
        ]
        merged, rejected, provenance = merge_code_candidates(
            code_candidates=candidates, existing_doc_rules=[],
        )
        report = validate_candidates(candidates=merged, expected_rules=False)
        assert report.valid_rule_count == 1
        assert report.is_compliant
        assert report.valid_rules[0].origin == ORIGIN_CODE


# ===========================================================================
# Bad-input tests
# ===========================================================================

@pytest.mark.governance
class TestMergeCodeCandidatesBad:

    def test_missing_modal_verb_passes_merge_but_fails_validation(self) -> None:
        """merge_code_candidates accepts structurally valid candidates;
        the deterministic pipeline rejects those without modal/declarative verb."""
        candidates = [
            _code_candidate(
                candidate_rule_text="BR-C001: The withdrawal limit",  # no modal verb
            ),
        ]
        merged, rejected, provenance = merge_code_candidates(
            code_candidates=candidates, existing_doc_rules=[],
        )
        # Structurally valid → not rejected by merge
        assert len(rejected) == 0
        assert len(merged) == 1
        # But the deterministic pipeline rejects it
        report = validate_candidates(candidates=merged, expected_rules=False)
        assert report.valid_rule_count == 0
        assert report.invalid_rule_count == 1

    def test_malformed_id_rejected(self) -> None:
        """ID not matching BR-C<NNN> pattern should be rejected."""
        candidates = [_code_candidate(id="BR-001")]  # missing C prefix
        merged, rejected, provenance = merge_code_candidates(
            code_candidates=candidates, existing_doc_rules=[],
        )
        assert len(rejected) == 1
        assert rejected[0].reason_code == REASON_CODE_CANDIDATE_REJECTED
        assert "invalid candidate id" in rejected[0].reason

    def test_empty_rule_text_rejected(self) -> None:
        """Empty candidate_rule_text should be rejected."""
        candidates = [_code_candidate(candidate_rule_text="")]
        merged, rejected, provenance = merge_code_candidates(
            code_candidates=candidates, existing_doc_rules=[],
        )
        assert len(rejected) == 1
        assert "empty" in rejected[0].reason

    def test_invalid_pattern_type_rejected(self) -> None:
        """Unknown pattern_type should be rejected."""
        candidates = [_code_candidate(pattern_type="not-real")]
        merged, rejected, provenance = merge_code_candidates(
            code_candidates=candidates, existing_doc_rules=[],
        )
        assert len(rejected) == 1
        assert "pattern_type" in rejected[0].reason

    def test_invalid_confidence_rejected(self) -> None:
        """Confidence outside enum should be rejected."""
        candidates = [_code_candidate(confidence="low")]
        merged, rejected, provenance = merge_code_candidates(
            code_candidates=candidates, existing_doc_rules=[],
        )
        assert len(rejected) == 1
        assert "confidence" in rejected[0].reason

    def test_non_dict_candidate_rejected(self) -> None:
        """Non-dict items in the candidates list should be rejected."""
        merged, rejected, provenance = merge_code_candidates(
            code_candidates=["not a dict"],  # type: ignore[list-item]
            existing_doc_rules=[],
        )
        assert len(rejected) == 1
        assert "not a dict" in rejected[0].reason


# ===========================================================================
# Corner-case tests
# ===========================================================================

@pytest.mark.governance
class TestMergeCodeCandidatesCorner:

    def test_code_candidate_duplicates_doc_rule_deduplicated(self) -> None:
        """Same rule body in doc and code → appears once, provenance shows both."""
        doc_rules = [
            _doc_rule("BR-001", "BR-001: Withdrawal amount must not exceed the daily limit"),
        ]
        code = [_code_candidate(
            id="BR-C001",
            # Same body, different ID
            candidate_rule_text="BR-C001: Withdrawal amount must not exceed the daily limit",
        )]
        merged, rejected, provenance = merge_code_candidates(
            code_candidates=code, existing_doc_rules=doc_rules,
        )
        # Only the doc rule remains in merged (code dupe removed)
        assert len(merged) == 1
        assert merged[0].origin == ORIGIN_DOC
        # Provenance records dual origin
        dual = [p for p in provenance if p.found_in_docs and p.found_in_code]
        assert len(dual) == 1
        assert "daily limit" in dual[0].rule_text.lower()

    def test_duplicate_code_candidates_deduplicated(self) -> None:
        """Two code candidates with same body → only first survives."""
        candidates = [
            _code_candidate(id="BR-C001", candidate_rule_text="BR-C001: Order must be validated"),
            _code_candidate(id="BR-C002", candidate_rule_text="BR-C002: Order must be validated"),
        ]
        merged, rejected, provenance = merge_code_candidates(
            code_candidates=candidates, existing_doc_rules=[],
        )
        assert len(merged) == 1
        assert len(rejected) == 0

    def test_empty_code_candidates_no_crash(self) -> None:
        """Empty candidates list → no crash, doc rules pass through."""
        doc_rules = [
            _doc_rule("BR-001", "BR-001: All transfers must include a reference number"),
        ]
        merged, rejected, provenance = merge_code_candidates(
            code_candidates=[], existing_doc_rules=doc_rules,
        )
        assert len(merged) == 1
        assert len(rejected) == 0
        assert merged[0].origin == ORIGIN_DOC

    def test_empty_source_path_rejected(self) -> None:
        """source_path must be a non-empty string."""
        candidates = [_code_candidate(source_path="")]
        merged, rejected, provenance = merge_code_candidates(
            code_candidates=candidates, existing_doc_rules=[],
        )
        assert len(rejected) == 1
        assert "source_path" in rejected[0].reason

    def test_provenance_counts_correct(self) -> None:
        """Verify doc_only, code_only, doc_and_code counts from provenance."""
        doc_rules = [
            _doc_rule("BR-001", "BR-001: All transfers must include a reference number"),
            _doc_rule("BR-002", "BR-002: Withdrawal amount must not exceed the daily limit"),
        ]
        code = [
            _code_candidate(
                id="BR-C001",
                # Duplicates BR-002
                candidate_rule_text="BR-C001: Withdrawal amount must not exceed the daily limit",
            ),
            _code_candidate(
                id="BR-C002",
                candidate_rule_text="BR-C002: Account must be active before any debit",
                pattern_type="guard-clause",
            ),
        ]
        merged, rejected, provenance = merge_code_candidates(
            code_candidates=code, existing_doc_rules=doc_rules,
        )
        doc_only = [p for p in provenance if p.found_in_docs and not p.found_in_code]
        code_only = [p for p in provenance if p.found_in_code and not p.found_in_docs]
        doc_and_code = [p for p in provenance if p.found_in_docs and p.found_in_code]
        assert len(doc_only) == 1   # BR-001 only in docs
        assert len(code_only) == 1  # BR-C002 only in code
        assert len(doc_and_code) == 1  # BR-002/BR-C001 in both


# ===========================================================================
# Edge-case tests
# ===========================================================================

@pytest.mark.governance
class TestMergeCodeCandidatesEdge:

    def test_fifty_code_candidates_performance(self) -> None:
        """50 candidates should be processed without issue."""
        candidates = [
            _code_candidate(
                id=f"BR-C{i:03d}",
                candidate_rule_text=f"BR-C{i:03d}: Rule number {i} must be enforced",
                source_path=f"src/Service{i}.java",
            )
            for i in range(1, 51)
        ]
        merged, rejected, provenance = merge_code_candidates(
            code_candidates=candidates, existing_doc_rules=[],
        )
        assert len(rejected) == 0
        assert len(merged) == 50

    def test_unicode_in_rule_body(self) -> None:
        """Unicode characters in rule text should be handled."""
        candidates = [_code_candidate(
            candidate_rule_text="BR-C001: Überweisungsbetrag darf das Tageslimit nicht überschreiten",
        )]
        merged, rejected, provenance = merge_code_candidates(
            code_candidates=candidates, existing_doc_rules=[],
        )
        assert len(rejected) == 0
        assert len(merged) == 1
        assert "Überweisungsbetrag" in merged[0].text

    def test_long_evidence_snippet_truncated(self) -> None:
        """Evidence snippet > 500 chars should not cause rejection (silently truncated)."""
        candidates = [_code_candidate(evidence_snippet="x" * 1000)]
        merged, rejected, provenance = merge_code_candidates(
            code_candidates=candidates, existing_doc_rules=[],
        )
        # Not rejected — snippet is just metadata
        assert len(rejected) == 0
        assert len(merged) == 1

    def test_line_range_parsed_to_line_no(self) -> None:
        """line_range '42-48' should yield line_no=42 on the RuleCandidate."""
        candidates = [_code_candidate(line_range="42-48")]
        merged, rejected, provenance = merge_code_candidates(
            code_candidates=candidates, existing_doc_rules=[],
        )
        code_candidates_in_merged = [c for c in merged if c.origin == ORIGIN_CODE]
        assert len(code_candidates_in_merged) == 1
        assert code_candidates_in_merged[0].line_no == 42

    def test_missing_line_range_defaults_to_zero(self) -> None:
        """Missing line_range should default to line_no=0."""
        c = _code_candidate()
        del c["line_range"]
        merged, rejected, provenance = merge_code_candidates(
            code_candidates=[c], existing_doc_rules=[],
        )
        code_candidates_in_merged = [c for c in merged if c.origin == ORIGIN_CODE]
        assert len(code_candidates_in_merged) == 1
        assert code_candidates_in_merged[0].line_no == 0


# ===========================================================================
# Integration: merge → validate round-trip
# ===========================================================================

@pytest.mark.governance
class TestMergeValidateRoundTrip:

    def test_mixed_doc_and_code_rules_all_validated(self) -> None:
        """Full round-trip: doc rules + code candidates → merge → validate → report."""
        doc_rules = [
            _doc_rule("BR-001", "BR-001: All transfers must include a reference number"),
        ]
        code = [
            _code_candidate(
                id="BR-C001",
                candidate_rule_text="BR-C001: Withdrawal amount must not exceed the daily limit",
            ),
        ]
        merged, rejected, provenance = merge_code_candidates(
            code_candidates=code, existing_doc_rules=doc_rules,
        )
        report = validate_candidates(candidates=merged, expected_rules=False)
        assert report.valid_rule_count == 2
        assert report.is_compliant
        # Check origins preserved
        origins = {r.origin for r in report.valid_rules}
        assert origins == {ORIGIN_DOC, ORIGIN_CODE}

    def test_code_candidate_without_modal_verb_rejected_by_pipeline(self) -> None:
        """Code candidate that passes merge but fails modal-verb check → invalid in report."""
        code = [
            _code_candidate(
                id="BR-C001",
                candidate_rule_text="BR-C001: The daily withdrawal limit",
            ),
        ]
        merged, rejected, provenance = merge_code_candidates(
            code_candidates=code, existing_doc_rules=[],
        )
        report = validate_candidates(candidates=merged, expected_rules=False)
        assert report.valid_rule_count == 0
        assert report.invalid_rule_count == 1

    def test_deduplicated_candidate_not_double_counted_in_validation(self) -> None:
        """A doc+code duplicate should result in exactly 1 validated rule, not 2."""
        doc_rules = [
            _doc_rule("BR-001", "BR-001: Withdrawal amount must not exceed the daily limit"),
        ]
        code = [
            _code_candidate(
                id="BR-C001",
                candidate_rule_text="BR-C001: Withdrawal amount must not exceed the daily limit",
            ),
        ]
        merged, rejected, provenance = merge_code_candidates(
            code_candidates=code, existing_doc_rules=doc_rules,
        )
        report = validate_candidates(candidates=merged, expected_rules=False)
        assert report.valid_rule_count == 1
        assert report.valid_rules[0].origin == ORIGIN_DOC
