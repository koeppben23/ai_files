from __future__ import annotations

import json
from pathlib import Path

import pytest

try:
    import jsonschema
except ImportError:
    jsonschema = None  # type: ignore[assignment]

from governance_runtime.infrastructure.workspace_paths import run_dir
from governance_runtime.infrastructure.workspace_paths import repository_manifest_path
from governance_runtime.infrastructure.work_run_archive import archive_active_run


_FINGERPRINT = "abc123def456abc123def456"
_OBSERVED_AT = "2026-03-11T12:00:00Z"

_SCHEMA_PATHS = {
    "run-manifest.json": Path("governance_runtime/assets/schemas/run_manifest.v1.schema.json"),
    "metadata.json": Path("governance_runtime/assets/schemas/work_run_snapshot.v2.schema.json"),
    "checksums.json": Path("governance_runtime/assets/schemas/run_checksums.v1.schema.json"),
    "ticket-record.json": Path("governance_runtime/assets/schemas/ticket_record.v1.schema.json"),
    "review-decision-record.json": Path("governance_runtime/assets/schemas/review_decision_record.v1.schema.json"),
    "outcome-record.json": Path("governance_runtime/assets/schemas/outcome_record.v1.schema.json"),
    "evidence-index.json": Path("governance_runtime/assets/schemas/evidence_index.v1.schema.json"),
    "finalization-record.json": Path("governance_runtime/assets/schemas/finalization_record.v1.schema.json"),
    "pr-record.json": Path("governance_runtime/assets/schemas/pr_record.v1.schema.json"),
    "provenance-record.json": Path("governance_runtime/assets/schemas/provenance_record.v1.schema.json"),
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_schema(relative_path: Path) -> dict:
    return json.loads((_repo_root() / relative_path).read_text(encoding="utf-8"))


def _materialize_run(tmp_path: Path) -> Path:
    workspaces_home = tmp_path / "workspaces"
    state = {
        "session_run_id": "run-schema-artifacts",
        "Phase": "6-PostFlight",
        "active_gate": "Evidence Presentation Gate",
        "Next": "6",
        "ticket_ref": "T-123",
        "ticket_title": "Ticket title",
        "review_decision": "approve",
        "review_decision_note": "looks good",
        "result": "success",
        "evidence_refs": ["docs/spec.md:10"],
        "PullRequestTitle": "feat: schema coverage",
        "PullRequestBody": "Adds artifact schemas",
        "model_context": {"provider": "openai", "model": "gpt-5.3-codex"},
        "approval_context": {"status": "approved", "approver_role": "approver"},
    }
    archive_active_run(
        workspaces_home=workspaces_home,
        repo_fingerprint=_FINGERPRINT,
        run_id="run-schema-artifacts",
        observed_at=_OBSERVED_AT,
        session_state_document={"SESSION_STATE": state},
        state_view=state,
    )
    return run_dir(workspaces_home, _FINGERPRINT, "run-schema-artifacts")


@pytest.mark.governance
class TestAuditRecordSchemaFiles:
    def test_schema_files_exist_and_valid_json(self) -> None:
        for schema_path in _SCHEMA_PATHS.values():
            full = _repo_root() / schema_path
            assert full.is_file()
            payload = _load_schema(schema_path)
            assert payload.get("$schema") == "https://json-schema.org/draft/2020-12/schema"


@pytest.mark.governance
@pytest.mark.skipif(jsonschema is None, reason="jsonschema not installed")
class TestAuditRecordSchemaValidation:
    def test_materialized_records_validate_against_schemas(self, tmp_path: Path) -> None:
        assert jsonschema is not None
        run_root = _materialize_run(tmp_path)
        for record_name, schema_path in _SCHEMA_PATHS.items():
            schema = _load_schema(schema_path)
            jsonschema.Draft202012Validator.check_schema(schema)
            payload = json.loads((run_root / record_name).read_text(encoding="utf-8"))
            jsonschema.validate(payload, schema)

    def test_missing_required_field_is_rejected(self, tmp_path: Path) -> None:
        assert jsonschema is not None
        run_root = _materialize_run(tmp_path)
        payload = json.loads((run_root / "ticket-record.json").read_text(encoding="utf-8"))
        schema = _load_schema(_SCHEMA_PATHS["ticket-record.json"])
        del payload["artifact_id"]

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(payload, schema)

    def test_repository_manifest_validates_against_schema(self, tmp_path: Path) -> None:
        assert jsonschema is not None
        workspaces_home = tmp_path / "workspaces"
        _materialize_run(tmp_path)
        payload = json.loads(
            repository_manifest_path(workspaces_home, _FINGERPRINT).read_text(encoding="utf-8")
        )
        schema = _load_schema(Path("governance_runtime/assets/schemas/repository_manifest.v1.schema.json"))
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.validate(payload, schema)
