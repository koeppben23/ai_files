"""Tests for plan-record.v1 JSON schema validation.

Validates that the schema correctly accepts valid plan-record documents
and rejects structurally invalid ones.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

try:
    import jsonschema
except ImportError:
    jsonschema = None  # type: ignore[assignment]

from tests.util import REPO_ROOT

_SCHEMA_PATH = REPO_ROOT / "governance_runtime" / "assets" / "schemas" / "plan_record.v1.schema.json"


def _load_schema() -> dict:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def _minimal_version(*, version: int = 1) -> dict:
    """Build a minimal valid PlanVersion entry."""
    return {
        "version": version,
        "timestamp": "2026-03-01T12:00:00+00:00",
        "phase": "4",
        "session_run_id": "sess-001",
        "content_hash": "sha256:" + "a" * 64,
        "supersedes": None,
        "trigger": "initial",
        "feature_complexity": {
            "class": "COMPLEX",
            "reason": "Multi-layer changes across persistence + governance engine",
            "planning_depth": "full",
        },
        "ticket_record": {
            "context": "Adding plan record persistence",
            "decision": "JSON file with versioned entries",
            "rationale": "Machine-readable, schema-validated",
            "consequences": "New file in workspace directory",
            "rollback": "Delete plan-record.json",
        },
        "nfr_checklist": {
            "security_privacy": {"status": "N/A", "detail": "No user data involved"},
            "observability": {"status": "OK", "detail": "Logged via session reader"},
            "performance": {"status": "OK", "detail": "Single JSON file write"},
            "migration_compatibility": {"status": "N/A", "detail": "New artifact"},
            "rollback_release_safety": {"status": "OK", "detail": "File deletion suffices"},
        },
        "test_strategy": ["Unit tests for repository", "Schema validation tests"],
    }


def _minimal_document(*, versions: list[dict] | None = None) -> dict:
    """Build a minimal valid plan-record document."""
    return {
        "schema_version": "1.0.0",
        "repo_fingerprint": "a" * 24,
        "status": "active",
        "finalized_at": None,
        "finalized_by_session": None,
        "finalized_phase": None,
        "outcome": None,
        "versions": versions if versions is not None else [_minimal_version()],
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate(doc: dict) -> None:
    """Validate doc against the schema, raising on error."""
    if jsonschema is None:
        pytest.skip("jsonschema not installed")
    schema = _load_schema()
    jsonschema.validate(doc, schema)


def _is_valid(doc: dict) -> bool:
    """Return True if doc passes schema validation."""
    if jsonschema is None:
        pytest.skip("jsonschema not installed")
    schema = _load_schema()
    try:
        jsonschema.validate(doc, schema)
        return True
    except jsonschema.ValidationError:
        return False


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.governance
class TestPlanRecordSchemaFile:
    """Verify the schema file itself is valid JSON."""

    def test_schema_file_exists(self) -> None:
        assert _SCHEMA_PATH.is_file(), f"Schema file not found: {_SCHEMA_PATH}"

    def test_schema_is_valid_json(self) -> None:
        schema = _load_schema()
        assert isinstance(schema, dict)
        assert schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema"

    def test_schema_has_required_top_level_properties(self) -> None:
        schema = _load_schema()
        required = schema.get("required", [])
        assert "schema_version" in required
        assert "repo_fingerprint" in required
        assert "status" in required
        assert "versions" in required

    def test_schema_defines_plan_version(self) -> None:
        schema = _load_schema()
        defs = schema.get("$defs", {})
        assert "PlanVersion" in defs

    def test_schema_defines_all_sub_types(self) -> None:
        schema = _load_schema()
        defs = schema.get("$defs", {})
        for expected in (
            "PlanVersion",
            "FeatureComplexity",
            "TicketRecord",
            "NFRChecklist",
            "NFRItem",
            "TouchedSurface",
            "RollbackStrategy",
            "ArchitectureOption",
            "ReviewFeedbackRef",
        ):
            assert expected in defs, f"Missing $defs/{expected}"


@pytest.mark.governance
@pytest.mark.skipif(jsonschema is None, reason="jsonschema not installed")
class TestPlanRecordSchemaValidation:
    """Test schema validation with valid and invalid documents."""

    def test_minimal_document_valid(self) -> None:
        _validate(_minimal_document())

    def test_empty_versions_valid(self) -> None:
        _validate(_minimal_document(versions=[]))

    def test_finalized_document_valid(self) -> None:
        doc = _minimal_document()
        doc["status"] = "finalized"
        doc["finalized_at"] = "2026-03-01T14:00:00+00:00"
        doc["finalized_by_session"] = "sess-002"
        doc["finalized_phase"] = "6"
        doc["outcome"] = "completed"
        _validate(doc)

    def test_archived_status_valid(self) -> None:
        doc = _minimal_document()
        doc["status"] = "archived"
        _validate(doc)

    def test_version_with_all_optional_fields(self) -> None:
        ver = _minimal_version()
        ver["touched_surface"] = {
            "files_planned": ["src/foo.py", "src/bar.py"],
            "contracts_planned": ["api/v1/users"],
            "schema_planned": [],
        }
        ver["rollback_strategy"] = {
            "type": "feature-flag",
            "steps": ["Disable flag", "Deploy previous"],
            "data_migration_reversible": True,
            "risk": "Low",
        }
        ver["architecture_options"] = [
            {
                "id": "A",
                "description": "Single file approach",
                "tradeoffs": "Simple but limited",
                "test_impact": None,
                "recommended": True,
            },
            {
                "id": "B",
                "description": "Multi-file approach",
                "tradeoffs": "Complex but flexible",
                "test_impact": "Additional integration tests needed",
                "recommended": False,
            },
        ]
        ver["mandatory_review_matrix"] = {"peer_review": True}
        ver["codebase_context_applied"] = {"prior_patterns": "repository pattern"}
        ver["review_feedback_ref"] = {
            "iteration": 1,
            "issues": ["Missing error handling"],
            "suggestions": ["Add logging"],
            "status": "approved",
        }
        _validate(_minimal_document(versions=[ver]))

    def test_all_trigger_values(self) -> None:
        for trigger in ("initial", "self_review_revision", "p5_feedback_revision", "manual_revision", "backfill"):
            ver = _minimal_version()
            ver["trigger"] = trigger
            _validate(_minimal_document(versions=[ver]))

    def test_all_complexity_classes(self) -> None:
        for cls in ("SIMPLE-CRUD", "REFACTORING", "MODIFICATION", "COMPLEX", "STANDARD"):
            ver = _minimal_version()
            ver["feature_complexity"]["class"] = cls
            _validate(_minimal_document(versions=[ver]))

    def test_all_nfr_statuses(self) -> None:
        for status in ("OK", "N/A", "Risk", "Needs decision"):
            ver = _minimal_version()
            ver["nfr_checklist"]["security_privacy"] = {"status": status, "detail": "test"}
            _validate(_minimal_document(versions=[ver]))

    def test_all_outcome_values(self) -> None:
        for outcome in ("completed", "abandoned", "superseded", None):
            doc = _minimal_document()
            doc["outcome"] = outcome
            _validate(doc)

    # -- Invalid documents --

    def test_missing_schema_version_rejected(self) -> None:
        doc = _minimal_document()
        del doc["schema_version"]
        assert not _is_valid(doc)

    def test_wrong_schema_version_rejected(self) -> None:
        doc = _minimal_document()
        doc["schema_version"] = "2.0.0"
        assert not _is_valid(doc)

    def test_invalid_status_rejected(self) -> None:
        doc = _minimal_document()
        doc["status"] = "draft"
        assert not _is_valid(doc)

    def test_invalid_repo_fingerprint_rejected(self) -> None:
        doc = _minimal_document()
        doc["repo_fingerprint"] = "too-short"
        assert not _is_valid(doc)

    def test_invalid_content_hash_pattern_rejected(self) -> None:
        ver = _minimal_version()
        ver["content_hash"] = "md5:abc"
        assert not _is_valid(_minimal_document(versions=[ver]))

    def test_invalid_trigger_rejected(self) -> None:
        ver = _minimal_version()
        ver["trigger"] = "unknown-trigger"
        assert not _is_valid(_minimal_document(versions=[ver]))

    def test_invalid_complexity_class_rejected(self) -> None:
        ver = _minimal_version()
        ver["feature_complexity"]["class"] = "UNKNOWN"
        assert not _is_valid(_minimal_document(versions=[ver]))

    def test_version_zero_rejected(self) -> None:
        ver = _minimal_version()
        ver["version"] = 0
        assert not _is_valid(_minimal_document(versions=[ver]))

    def test_additional_top_level_properties_rejected(self) -> None:
        doc = _minimal_document()
        doc["extra_field"] = "not allowed"
        assert not _is_valid(doc)

    def test_additional_version_properties_rejected(self) -> None:
        ver = _minimal_version()
        ver["extra_field"] = "not allowed"
        assert not _is_valid(_minimal_document(versions=[ver]))

    def test_missing_nfr_key_rejected(self) -> None:
        ver = _minimal_version()
        del ver["nfr_checklist"]["performance"]
        assert not _is_valid(_minimal_document(versions=[ver]))

    def test_invalid_nfr_status_rejected(self) -> None:
        ver = _minimal_version()
        ver["nfr_checklist"]["security_privacy"]["status"] = "Invalid"
        assert not _is_valid(_minimal_document(versions=[ver]))
