"""Tests for governance.infrastructure.redaction — Field-level redaction engine.

Covers: Happy / Edge / Corner / Bad paths.
"""

from __future__ import annotations

import hashlib

import pytest

from governance.domain.classification import (
    ClassificationLevel,
    RedactionStrategy,
)
from governance.infrastructure.redaction import (
    apply_redaction,
    redact_document,
    redact_archive,
)


# ===================================================================
# Happy path — apply_redaction
# ===================================================================

class TestApplyRedactionHappy:
    """Happy: each strategy transforms values correctly."""

    def test_none_strategy_passes_through(self):
        assert apply_redaction("hello", RedactionStrategy.NONE) == "hello"

    def test_hash_strategy_produces_redacted_prefix(self):
        result = apply_redaction("secret", RedactionStrategy.HASH)
        assert result.startswith("[REDACTED:sha256:")
        assert result.endswith("]")

    def test_hash_is_deterministic(self):
        r1 = apply_redaction("secret", RedactionStrategy.HASH)
        r2 = apply_redaction("secret", RedactionStrategy.HASH)
        assert r1 == r2

    def test_hash_different_inputs_produce_different_outputs(self):
        r1 = apply_redaction("secret1", RedactionStrategy.HASH)
        r2 = apply_redaction("secret2", RedactionStrategy.HASH)
        assert r1 != r2

    def test_mask_strategy_preserves_tail(self):
        result = apply_redaction("my-secret-value", RedactionStrategy.MASK)
        assert result.startswith("[REDACTED:...")
        assert result.endswith("alue]")

    def test_remove_strategy_replaces_with_marker(self):
        result = apply_redaction("anything", RedactionStrategy.REMOVE)
        assert result == "[REMOVED]"

    def test_truncate_strategy_on_long_string(self):
        long_str = "x" * 100
        result = apply_redaction(long_str, RedactionStrategy.TRUNCATE)
        assert "[TRUNCATED]" in result
        assert len(result) < len(long_str) + 20

    def test_truncate_strategy_on_short_string(self):
        result = apply_redaction("short", RedactionStrategy.TRUNCATE)
        assert result == "short"  # no truncation needed

    def test_none_value_passes_through(self):
        assert apply_redaction(None, RedactionStrategy.HASH) is None
        assert apply_redaction(None, RedactionStrategy.REMOVE) is None


# ===================================================================
# Happy path — redact_document
# ===================================================================

class TestRedactDocumentHappy:
    """Happy: document-level redaction applies correct strategies."""

    def test_public_field_kept_at_internal_level(self):
        """PUBLIC fields should pass through when max_level=INTERNAL."""
        doc = {"schema": "governance.run-manifest.v2"}
        result = redact_document("run-manifest.json", doc,
                                 max_level=ClassificationLevel.INTERNAL)
        assert result["schema"] == "governance.run-manifest.v2"

    def test_confidential_field_redacted_at_internal_level(self):
        """CONFIDENTIAL fields should be redacted when max_level=INTERNAL."""
        doc = {"ticket_digest": "sha256:abc123"}
        result = redact_document("metadata.json", doc,
                                 max_level=ClassificationLevel.INTERNAL)
        assert result["ticket_digest"] != "sha256:abc123"

    def test_restricted_field_redacted_at_internal_level(self):
        """RESTRICTED fields should be redacted when max_level=INTERNAL."""
        doc = {"PullRequestBody": "sensitive implementation details"}
        result = redact_document("SESSION_STATE.json", doc,
                                 max_level=ClassificationLevel.INTERNAL)
        assert result["PullRequestBody"] == "[REMOVED]"

    def test_override_strategy_applied(self):
        """override_strategy overrides the per-field default."""
        doc = {"ticket_digest": "sha256:abc123"}
        result = redact_document("metadata.json", doc,
                                 max_level=ClassificationLevel.INTERNAL,
                                 override_strategy=RedactionStrategy.REMOVE)
        assert result["ticket_digest"] == "[REMOVED]"

    def test_all_fields_at_public_level_redacts_everything_above(self):
        doc = {
            "schema": "test",           # PUBLIC
            "repo_fingerprint": "abc",   # INTERNAL
        }
        result = redact_document("run-manifest.json", doc,
                                 max_level=ClassificationLevel.PUBLIC)
        assert result["schema"] == "test"
        # INTERNAL > PUBLIC → redacted
        assert result["repo_fingerprint"] != "abc"

    def test_pii_session_state_fields_are_redacted_below_restricted(self):
        doc = {
            "PullRequestTitle": "Customer Account Migration",
            "PullRequestBody": "Contains customer identifiers and rollout details",
        }
        result = redact_document(
            "SESSION_STATE.json",
            doc,
            max_level=ClassificationLevel.INTERNAL,
        )
        assert result["PullRequestTitle"] != doc["PullRequestTitle"]
        assert result["PullRequestBody"] == "[REMOVED]"


# ===================================================================
# Happy path — redact_archive
# ===================================================================

class TestRedactArchiveHappy:
    """Happy: archive-level redaction processes multiple documents."""

    def test_redacts_multiple_documents(self):
        archive = {
            "run-manifest.json": {"schema": "v2", "repo_fingerprint": "abc"},
            "metadata.json": {"ticket_digest": "secret"},
        }
        result = redact_archive(archive, max_level=ClassificationLevel.INTERNAL)
        assert "run-manifest.json" in result
        assert "metadata.json" in result
        # Confidential field redacted
        assert result["metadata.json"]["ticket_digest"] != "secret"
        # Public field kept
        assert result["run-manifest.json"]["schema"] == "v2"

    def test_returns_new_dict(self):
        archive = {"run-manifest.json": {"schema": "v2"}}
        result = redact_archive(archive)
        assert result is not archive


# ===================================================================
# Edge cases
# ===================================================================

class TestApplyRedactionEdge:
    """Edge: boundary values for redaction."""

    def test_empty_string_hash(self):
        result = apply_redaction("", RedactionStrategy.HASH)
        assert result.startswith("[REDACTED:sha256:")

    def test_empty_string_mask(self):
        result = apply_redaction("", RedactionStrategy.MASK)
        assert result == "[REDACTED]"

    def test_exactly_4_chars_mask(self):
        result = apply_redaction("abcd", RedactionStrategy.MASK)
        assert result == "[REDACTED]"

    def test_5_chars_mask_preserves_last_4(self):
        result = apply_redaction("abcde", RedactionStrategy.MASK)
        assert "bcde" in result

    def test_integer_value_converted_to_string(self):
        result = apply_redaction(42, RedactionStrategy.HASH)
        assert result.startswith("[REDACTED:sha256:")

    def test_boolean_value_converted(self):
        result = apply_redaction(True, RedactionStrategy.MASK)
        assert "[REDACTED" in result

    def test_exactly_32_chars_not_truncated(self):
        value = "x" * 32
        result = apply_redaction(value, RedactionStrategy.TRUNCATE)
        assert result == value

    def test_33_chars_truncated(self):
        value = "x" * 33
        result = apply_redaction(value, RedactionStrategy.TRUNCATE)
        assert "[TRUNCATED]" in result


class TestRedactDocumentEdge:
    """Edge: document-level edge cases."""

    def test_empty_document(self):
        result = redact_document("run-manifest.json", {})
        assert result == {}

    def test_unknown_field_defaults_to_internal_hash(self):
        """Unknown fields are classified as INTERNAL with HASH redaction."""
        doc = {"unknown_field": "value"}
        # At PUBLIC level, INTERNAL fields are above threshold
        result = redact_document("run-manifest.json", doc,
                                 max_level=ClassificationLevel.PUBLIC)
        assert result["unknown_field"] != "value"

    def test_max_level_restricted_keeps_everything(self):
        """At RESTRICTED level, nothing is above threshold."""
        doc = {"PullRequestBody": "sensitive", "ticket_digest": "sha256:abc"}
        result = redact_document("SESSION_STATE.json", doc,
                                 max_level=ClassificationLevel.RESTRICTED)
        assert result["PullRequestBody"] == "sensitive"

    def test_nested_dict_redacted_when_above_level(self):
        """Nested dicts above max_level are redacted as atomic values."""
        doc = {"outer": {"inner_key": "inner_value"}}
        # Unknown field → INTERNAL → above PUBLIC level → redacted atomically
        result = redact_document("run-manifest.json", doc,
                                 max_level=ClassificationLevel.PUBLIC)
        # The entire dict value is converted to string and hashed
        assert isinstance(result["outer"], str)
        assert "[REDACTED:" in result["outer"]


# ===================================================================
# Corner cases
# ===================================================================

class TestRedactDocumentCorner:
    """Corner: unusual document structures."""

    def test_deeply_nested_dict(self):
        doc = {"a": {"b": {"c": {"d": "deep"}}}}
        result = redact_document("run-manifest.json", doc,
                                 max_level=ClassificationLevel.PUBLIC)
        assert isinstance(result, dict)

    def test_list_values_not_recursed_into(self):
        """Lists should be treated as leaf values, not recursed into."""
        doc = {"items": ["a", "b", "c"]}
        # At PUBLIC max_level, unknown field (INTERNAL) → redacted
        result = redact_document("run-manifest.json", doc,
                                 max_level=ClassificationLevel.PUBLIC)
        # The list should be redacted as a single value (not element-by-element)
        assert isinstance(result["items"], str)

    def test_very_large_document(self):
        doc = {f"field_{i}": f"value_{i}" for i in range(1000)}
        result = redact_document("run-manifest.json", doc,
                                 max_level=ClassificationLevel.PUBLIC)
        assert len(result) == 1000

    def test_document_with_none_values(self):
        doc = {"schema": None}
        result = redact_document("run-manifest.json", doc,
                                 max_level=ClassificationLevel.PUBLIC)
        # PUBLIC field → passes through; None is the value
        assert result["schema"] is None


class TestRedactArchiveCorner:
    """Corner: archive-level edge cases."""

    def test_empty_archive(self):
        result = redact_archive({})
        assert result == {}

    def test_single_document_archive(self):
        archive = {"run-manifest.json": {"schema": "v2"}}
        result = redact_archive(archive, max_level=ClassificationLevel.INTERNAL)
        assert len(result) == 1

    def test_unknown_artifact_name(self):
        archive = {"unknown.json": {"field": "value"}}
        result = redact_archive(archive, max_level=ClassificationLevel.PUBLIC)
        # Unknown artifact → INTERNAL defaults → redacted at PUBLIC level
        assert result["unknown.json"]["field"] != "value"


# ===================================================================
# Bad paths
# ===================================================================

class TestApplyRedactionBad:
    """Bad: redaction handles bad inputs gracefully."""

    def test_hash_of_non_string_does_not_crash(self):
        result = apply_redaction({"key": "val"}, RedactionStrategy.HASH)
        assert "[REDACTED:sha256:" in result

    def test_mask_of_non_string_does_not_crash(self):
        result = apply_redaction([1, 2, 3], RedactionStrategy.MASK)
        assert "[REDACTED" in result

    def test_none_always_passes_through_regardless_of_strategy(self):
        for strategy in RedactionStrategy:
            assert apply_redaction(None, strategy) is None


class TestRedactDocumentBad:
    """Bad: document redaction with malformed inputs."""

    def test_input_document_not_mutated(self):
        original = {"ticket_digest": "sha256:abc"}
        doc_copy = dict(original)
        redact_document("metadata.json", original,
                        max_level=ClassificationLevel.PUBLIC)
        assert original == doc_copy
