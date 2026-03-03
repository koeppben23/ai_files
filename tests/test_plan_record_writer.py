"""Tests for plan-record writer (render + hash) functions.

Covers compute_content_hash, render_plan_record, new_plan_record_document,
and stamp_version from artifacts.writers.plan_record.
"""

from __future__ import annotations

import json

import pytest

from artifacts.writers.plan_record import (
    compute_content_hash,
    new_plan_record_document,
    render_plan_record,
    stamp_version,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _sample_version_data() -> dict:
    return {
        "version": 1,
        "timestamp": "2026-03-01T12:00:00+00:00",
        "phase": "4",
        "session_run_id": "sess-001",
        "supersedes": None,
        "trigger": "initial",
        "feature_complexity": {
            "class": "COMPLEX",
            "reason": "test",
            "planning_depth": "full",
        },
        "ticket_record": {
            "context": "ctx",
            "decision": "dec",
            "rationale": "rat",
            "consequences": "con",
            "rollback": "rb",
        },
        "nfr_checklist": {
            "security_privacy": {"status": "N/A", "detail": "n/a"},
            "observability": {"status": "OK", "detail": "ok"},
            "performance": {"status": "OK", "detail": "ok"},
            "migration_compatibility": {"status": "N/A", "detail": "n/a"},
            "rollback_release_safety": {"status": "OK", "detail": "ok"},
        },
        "test_strategy": ["Unit tests"],
    }


# ---------------------------------------------------------------------------
# compute_content_hash
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestComputeContentHash:

    def test_returns_sha256_prefixed_string(self) -> None:
        h = compute_content_hash(_sample_version_data())
        assert h.startswith("sha256:")
        assert len(h) == len("sha256:") + 64

    def test_hash_is_deterministic(self) -> None:
        data = _sample_version_data()
        h1 = compute_content_hash(data)
        h2 = compute_content_hash(data)
        assert h1 == h2

    def test_hash_excludes_content_hash_field(self) -> None:
        data = _sample_version_data()
        data_with_hash = dict(data)
        data_with_hash["content_hash"] = "sha256:" + "x" * 64
        assert compute_content_hash(data) == compute_content_hash(data_with_hash)

    def test_hash_changes_with_different_data(self) -> None:
        data1 = _sample_version_data()
        data2 = _sample_version_data()
        data2["trigger"] = "backfill"
        assert compute_content_hash(data1) != compute_content_hash(data2)

    def test_hash_hex_chars_only(self) -> None:
        h = compute_content_hash(_sample_version_data())
        hex_part = h.split(":", 1)[1]
        assert all(c in "0123456789abcdef" for c in hex_part)


# ---------------------------------------------------------------------------
# render_plan_record
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestRenderPlanRecord:

    def test_returns_valid_json(self) -> None:
        doc = new_plan_record_document("a" * 24)
        result = render_plan_record(doc)
        parsed = json.loads(result)
        assert parsed == doc

    def test_trailing_newline(self) -> None:
        doc = new_plan_record_document("b" * 24)
        result = render_plan_record(doc)
        assert result.endswith("\n")

    def test_custom_indent(self) -> None:
        doc = new_plan_record_document("c" * 24)
        result = render_plan_record(doc, indent=4)
        # 4-space indent means top-level keys are indented by 4 spaces
        assert '    "schema_version"' in result


# ---------------------------------------------------------------------------
# new_plan_record_document
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestNewPlanRecordDocument:

    def test_has_required_keys(self) -> None:
        doc = new_plan_record_document("d" * 24)
        assert doc["schema_version"] == "1.0.0"
        assert doc["repo_fingerprint"] == "d" * 24
        assert doc["status"] == "active"
        assert doc["versions"] == []

    def test_finalization_fields_null(self) -> None:
        doc = new_plan_record_document("e" * 24)
        assert doc["finalized_at"] is None
        assert doc["finalized_by_session"] is None
        assert doc["finalized_phase"] is None
        assert doc["outcome"] is None


# ---------------------------------------------------------------------------
# stamp_version
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestStampVersion:

    def test_adds_content_hash(self) -> None:
        data = _sample_version_data()
        assert "content_hash" not in data
        stamped = stamp_version(data)
        assert "content_hash" in stamped
        assert stamped["content_hash"].startswith("sha256:")

    def test_returns_new_dict(self) -> None:
        data = _sample_version_data()
        stamped = stamp_version(data)
        assert stamped is not data

    def test_preserves_original_data(self) -> None:
        data = _sample_version_data()
        original_keys = set(data.keys())
        stamp_version(data)
        assert set(data.keys()) == original_keys
        assert "content_hash" not in data

    def test_recomputes_stale_hash(self) -> None:
        data = _sample_version_data()
        data["content_hash"] = "sha256:" + "0" * 64  # stale
        stamped = stamp_version(data)
        assert stamped["content_hash"] != "sha256:" + "0" * 64

    def test_stamped_hash_matches_compute(self) -> None:
        data = _sample_version_data()
        stamped = stamp_version(data)
        expected = compute_content_hash(stamped)
        assert stamped["content_hash"] == expected
