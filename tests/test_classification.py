"""Tests for governance.domain.classification — Data classification domain model.

Covers: Happy / Edge / Corner / Bad paths.

Contract version under test: DATA_CLASSIFICATION.v1
"""

from __future__ import annotations

import pytest

from governance.domain.classification import (
    CONTRACT_VERSION,
    ClassificationLevel,
    RedactionStrategy,
    FieldClassification,
    FIELD_CLASSIFICATIONS,
    DEFAULT_CLASSIFICATION,
    classify_field,
    get_fields_by_level,
    get_fields_requiring_redaction,
    get_pii_fields,
    get_classification_summary,
)


# ===================================================================
# Happy path
# ===================================================================

class TestClassifyFieldHappy:
    """Happy: known fields return their expected classification."""

    def test_public_field_returns_public(self):
        fc = classify_field("run-manifest.json", "schema")
        assert fc.level == ClassificationLevel.PUBLIC

    def test_internal_field_returns_internal(self):
        fc = classify_field("run-manifest.json", "repo_fingerprint")
        assert fc.level == ClassificationLevel.INTERNAL

    def test_confidential_field_returns_confidential(self):
        fc = classify_field("metadata.json", "ticket_digest")
        assert fc.level == ClassificationLevel.CONFIDENTIAL

    def test_restricted_field_returns_restricted(self):
        fc = classify_field("SESSION_STATE.json", "PullRequestBody")
        assert fc.level == ClassificationLevel.RESTRICTED

    def test_redaction_strategy_matches_catalog(self):
        fc = classify_field("metadata.json", "failure_reason")
        assert fc.redaction == RedactionStrategy.MASK

    def test_field_path_and_artifact_populated(self):
        fc = classify_field("run-manifest.json", "run_id")
        assert fc.field_path == "run_id"
        assert fc.artifact == "run-manifest.json"


class TestGetFieldsByLevelHappy:
    """Happy: filtering by level returns correct subsets."""

    def test_public_fields_non_empty(self):
        public = get_fields_by_level(ClassificationLevel.PUBLIC)
        assert len(public) > 0
        assert all(f.level == ClassificationLevel.PUBLIC for f in public)

    def test_restricted_fields_non_empty(self):
        restricted = get_fields_by_level(ClassificationLevel.RESTRICTED)
        assert len(restricted) > 0
        assert all(f.level == ClassificationLevel.RESTRICTED for f in restricted)


class TestRedactionFieldsHappy:
    """Happy: get_fields_requiring_redaction returns only fields with strategy != NONE."""

    def test_all_returned_fields_require_redaction(self):
        fields = get_fields_requiring_redaction()
        assert len(fields) > 0
        for f in fields:
            assert f.redaction != RedactionStrategy.NONE

    def test_public_none_fields_excluded(self):
        fields = get_fields_requiring_redaction()
        for f in fields:
            # PUBLIC + NONE should not appear
            assert not (f.level == ClassificationLevel.PUBLIC
                        and f.redaction == RedactionStrategy.NONE)


class TestClassificationSummaryHappy:
    """Happy: get_classification_summary returns well-formed summary dict."""

    def test_summary_has_expected_keys(self):
        summary = get_classification_summary()
        assert summary["contract_version"] == CONTRACT_VERSION
        assert isinstance(summary["total_classified_fields"], int)
        assert isinstance(summary["fields_by_level"], dict)
        assert isinstance(summary["fields_by_redaction"], dict)
        assert "pii_fields_count" in summary
        assert "redaction_required_count" in summary

    def test_total_matches_catalog_size(self):
        summary = get_classification_summary()
        assert summary["total_classified_fields"] == len(FIELD_CLASSIFICATIONS)

    def test_level_counts_sum_to_total(self):
        summary = get_classification_summary()
        level_sum = sum(summary["fields_by_level"].values())
        assert level_sum == summary["total_classified_fields"]


# ===================================================================
# Edge cases
# ===================================================================

class TestClassifyFieldEdge:
    """Edge: boundary conditions on field classification."""

    def test_empty_artifact_returns_default(self):
        fc = classify_field("", "schema")
        assert fc.level == DEFAULT_CLASSIFICATION.level

    def test_empty_field_path_returns_default(self):
        fc = classify_field("run-manifest.json", "")
        assert fc.level == DEFAULT_CLASSIFICATION.level

    def test_case_sensitive_lookup(self):
        """Catalog keys are case-sensitive — uppercase should miss."""
        fc = classify_field("RUN-MANIFEST.JSON", "schema")
        assert fc == DEFAULT_CLASSIFICATION

    def test_whitespace_in_field_path_returns_default(self):
        fc = classify_field("run-manifest.json", " schema ")
        assert fc == DEFAULT_CLASSIFICATION

    def test_every_catalog_entry_is_frozen(self):
        """All FieldClassification entries should be frozen (immutable)."""
        for key, fc in FIELD_CLASSIFICATIONS.items():
            with pytest.raises(AttributeError):
                fc.level = ClassificationLevel.PUBLIC  # type: ignore[misc]


class TestGetFieldsByLevelEdge:
    """Edge: levels with no fields return empty list."""

    def test_all_four_levels_callable(self):
        for level in ClassificationLevel:
            result = get_fields_by_level(level)
            assert isinstance(result, list)


# ===================================================================
# Corner cases
# ===================================================================

class TestClassifyFieldCorner:
    """Corner: unusual but valid inputs."""

    def test_very_long_artifact_name(self):
        fc = classify_field("a" * 10000, "schema")
        assert fc == DEFAULT_CLASSIFICATION

    def test_very_long_field_path(self):
        fc = classify_field("run-manifest.json", "x" * 10000)
        assert fc == DEFAULT_CLASSIFICATION

    def test_unicode_artifact_name(self):
        fc = classify_field("日本語.json", "field")
        assert fc == DEFAULT_CLASSIFICATION

    def test_special_chars_in_field_path(self):
        fc = classify_field("run-manifest.json", "field/../../../etc/passwd")
        assert fc == DEFAULT_CLASSIFICATION

    def test_double_colon_in_field_path(self):
        """The key format uses '::' — a field containing '::' should not collide."""
        fc = classify_field("metadata.json", "a::b")
        assert fc == DEFAULT_CLASSIFICATION


class TestFieldClassificationDataclass:
    """Corner: dataclass behavior under unusual conditions."""

    def test_default_pii_is_false(self):
        fc = FieldClassification(
            field_path="test", artifact="test.json",
            level=ClassificationLevel.PUBLIC, redaction=RedactionStrategy.NONE,
            description="test",
        )
        assert fc.pii is False

    def test_default_audit_relevant_is_true(self):
        fc = FieldClassification(
            field_path="test", artifact="test.json",
            level=ClassificationLevel.PUBLIC, redaction=RedactionStrategy.NONE,
            description="test",
        )
        assert fc.audit_relevant is True


# ===================================================================
# Bad paths
# ===================================================================

class TestClassifyFieldBad:
    """Bad: unknown inputs fall back to fail-closed defaults."""

    def test_unknown_artifact_returns_default(self):
        fc = classify_field("totally-fake-artifact.json", "schema")
        assert fc == DEFAULT_CLASSIFICATION

    def test_unknown_field_returns_default(self):
        fc = classify_field("run-manifest.json", "nonexistent_field")
        assert fc == DEFAULT_CLASSIFICATION

    def test_default_classification_is_internal(self):
        """Fail-closed: unknown fields default to INTERNAL."""
        assert DEFAULT_CLASSIFICATION.level == ClassificationLevel.INTERNAL

    def test_default_redaction_is_hash(self):
        """Fail-closed: unknown fields redacted with HASH."""
        assert DEFAULT_CLASSIFICATION.redaction == RedactionStrategy.HASH

    def test_null_like_inputs(self):
        """None-like strings don't crash."""
        fc = classify_field("None", "None")
        assert fc == DEFAULT_CLASSIFICATION


class TestGetPiiFieldsBad:
    """Bad: PII filter returns empty if none marked."""

    def test_returns_list(self):
        result = get_pii_fields()
        assert isinstance(result, list)
        # All returned fields must have pii=True
        for f in result:
            assert f.pii is True


# ===================================================================
# Contract invariants
# ===================================================================

class TestClassificationContractInvariants:
    """Invariants that must hold across the entire catalog."""

    def test_contract_version_format(self):
        assert CONTRACT_VERSION == "DATA_CLASSIFICATION.v1"

    def test_all_catalog_keys_follow_format(self):
        """Every key must be 'artifact::field_path'."""
        for key in FIELD_CLASSIFICATIONS:
            assert "::" in key, f"Key {key} does not contain '::'"
            parts = key.split("::")
            assert len(parts) == 2, f"Key {key} has {len(parts)} parts, expected 2"

    def test_catalog_key_matches_record_fields(self):
        """The key 'artifact::field_path' must match the record's artifact and field_path."""
        for key, fc in FIELD_CLASSIFICATIONS.items():
            expected_key = f"{fc.artifact}::{fc.field_path}"
            assert key == expected_key, (
                f"Key mismatch: catalog key={key}, record={expected_key}"
            )

    def test_all_levels_represented(self):
        """Every ClassificationLevel should appear at least once in the catalog."""
        seen = {fc.level for fc in FIELD_CLASSIFICATIONS.values()}
        for level in ClassificationLevel:
            assert level in seen, f"Level {level} not represented in catalog"

    def test_all_redaction_strategies_in_enum(self):
        """Every redaction strategy used in the catalog must be a valid enum member."""
        for fc in FIELD_CLASSIFICATIONS.values():
            assert isinstance(fc.redaction, RedactionStrategy)

    def test_enum_values_are_lowercase_strings(self):
        for level in ClassificationLevel:
            assert level.value == level.value.lower()
        for strategy in RedactionStrategy:
            assert strategy.value == strategy.value.lower()
