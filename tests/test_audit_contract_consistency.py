"""Audit Contract Consistency Tests — WI-3 Test Matrix Hardening.

Tests that the formalized audit contract (domain model, YAML config, JSON schema)
is consistent with the production implementation in io_verify.py and
work_run_archive.py. Ensures no drift between contract specification and runtime.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
import pytest

from governance.domain.audit_contract import (
    ALLOWED_RUN_STATUSES,
    ALLOWED_RECORD_STATUSES,
    ALLOWED_ARCHIVE_STATUSES,
    ALLOWED_RUN_TYPES,
    ALLOWED_INTEGRITY_STATUSES,
    REQUIRED_ARCHIVE_FILES,
    OPTIONAL_ARCHIVE_FILES,
    EXPECTED_SCHEMAS,
    REQUIRED_ARTIFACT_KEYS,
    BASELINE_REQUIRED_TRUE,
    REQUIRED_ARCHIVED_FILE_KEYS,
    BASELINE_ARCHIVED_TRUE,
    RUN_MANIFEST_GOVERNANCE_FIELDS,
    ALLOWED_RESOLVED_OPERATING_MODES,
    VERIFY_POLICY_VERSION_RE,
    LIFECYCLE_INVARIANTS,
    RUN_TYPE_ARTIFACT_RULES,
    CONTRACT_VERSION,
    validate_schema_identifier,
)
from governance.domain.failure_model import (
    FailureCategory,
    FailureSeverity,
    RecoveryStrategy,
    FAILURE_CLASSIFICATIONS,
    CONTRACT_VERSION as FAILURE_CONTRACT_VERSION,
)
from governance.infrastructure.run_audit_artifacts import (
    RUN_STATUSES,
    RECORD_STATUSES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ASSETS_ROOT = Path(__file__).resolve().parent.parent / "governance" / "assets"
_CONFIG_ROOT = _ASSETS_ROOT / "config"
_SCHEMA_ROOT = _ASSETS_ROOT / "schemas"


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Domain Model ↔ Production Code Consistency
# ---------------------------------------------------------------------------

class TestDomainProductionConsistency:
    """Verify domain model constants match production run_audit_artifacts."""

    def test_run_statuses_match(self) -> None:
        assert ALLOWED_RUN_STATUSES == frozenset(RUN_STATUSES)

    def test_record_statuses_match(self) -> None:
        assert ALLOWED_RECORD_STATUSES == frozenset(RECORD_STATUSES)

    def test_run_types_complete(self) -> None:
        # io_verify.py:175 defines allowed_run_types
        assert ALLOWED_RUN_TYPES == frozenset({"analysis", "plan", "pr"})

    def test_integrity_statuses_complete(self) -> None:
        assert ALLOWED_INTEGRITY_STATUSES == frozenset({"pending", "passed", "failed"})


# ---------------------------------------------------------------------------
# Domain Model ↔ YAML Config Consistency
# ---------------------------------------------------------------------------

class TestDomainYamlConsistency:
    """Verify domain model matches audit_contract.yaml."""

    @pytest.fixture()
    def config(self) -> dict:
        return _load_yaml(_CONFIG_ROOT / "audit_contract.yaml")

    def test_contract_version_matches(self, config: dict) -> None:
        assert config["policy"]["contract_version"] == CONTRACT_VERSION

    def test_required_files_match(self, config: dict) -> None:
        yaml_files = set(config["run_archive"]["required_files"])
        assert yaml_files == REQUIRED_ARCHIVE_FILES

    def test_optional_files_match(self, config: dict) -> None:
        yaml_files = set(config["run_archive"]["optional_files"])
        assert yaml_files == OPTIONAL_ARCHIVE_FILES

    def test_expected_schemas_match(self, config: dict) -> None:
        yaml_schemas = config["run_archive"]["expected_schemas"]
        assert yaml_schemas == dict(EXPECTED_SCHEMAS)

    def test_run_statuses_match(self, config: dict) -> None:
        yaml_statuses = set(config["lifecycle_rules"]["allowed_run_statuses"])
        assert yaml_statuses == ALLOWED_RUN_STATUSES

    def test_record_statuses_match(self, config: dict) -> None:
        yaml_statuses = set(config["lifecycle_rules"]["allowed_record_statuses"])
        assert yaml_statuses == ALLOWED_RECORD_STATUSES

    def test_integrity_statuses_match(self, config: dict) -> None:
        yaml_statuses = set(config["lifecycle_rules"]["allowed_integrity_statuses"])
        assert yaml_statuses == ALLOWED_INTEGRITY_STATUSES

    def test_lifecycle_invariants_match(self, config: dict) -> None:
        yaml_invariants = config["lifecycle_rules"]["invariants"]
        for status, inv in LIFECYCLE_INVARIANTS.items():
            assert status in yaml_invariants, f"Missing invariant for {status}"
            yi = yaml_invariants[status]
            assert yi["expected_record_status"] == inv.expected_record_status
            assert yi["expected_integrity_status"] == inv.expected_integrity_status
            assert yi["requires_finalized_at"] == inv.requires_finalized_at
            assert yi["forbids_finalized_at"] == inv.forbids_finalized_at
            assert yi["requires_finalization_errors"] == inv.requires_finalization_errors
            assert yi["forbids_finalization_errors"] == inv.forbids_finalization_errors

    def test_run_types_match(self, config: dict) -> None:
        yaml_types = set(config["artifact_rules"]["allowed_run_types"])
        assert yaml_types == ALLOWED_RUN_TYPES

    def test_run_type_requirements_match(self, config: dict) -> None:
        yaml_reqs = config["artifact_rules"]["run_type_requirements"]
        for rt, rule in RUN_TYPE_ARTIFACT_RULES.items():
            assert rt in yaml_reqs, f"Missing run_type_requirement for {rt}"
            yr = yaml_reqs[rt]
            assert yr["plan_record_required"] == rule.plan_record_required
            assert yr["pr_record_required"] == rule.pr_record_required

    def test_required_artifact_keys_match(self, config: dict) -> None:
        yaml_keys = set(config["artifact_rules"]["required_artifact_keys"])
        assert yaml_keys == REQUIRED_ARTIFACT_KEYS

    def test_baseline_required_true_match(self, config: dict) -> None:
        yaml_baseline = set(config["artifact_rules"]["baseline_required_true"])
        assert yaml_baseline == BASELINE_REQUIRED_TRUE

    def test_run_manifest_governance_fields_match(self, config: dict) -> None:
        governance_fields = config["consistency_rules"]["run_manifest_governance_fields"]
        assert set(governance_fields["required"]) == RUN_MANIFEST_GOVERNANCE_FIELDS
        assert set(governance_fields["resolved_operating_mode_allowed"]) == ALLOWED_RESOLVED_OPERATING_MODES
        pattern = str(governance_fields["verify_policy_version_pattern"])
        assert VERIFY_POLICY_VERSION_RE.pattern == pattern


# ---------------------------------------------------------------------------
# Domain Model ↔ JSON Schema Consistency
# ---------------------------------------------------------------------------

class TestDomainJsonSchemaConsistency:
    """Verify domain model matches audit_contract.v1.schema.json."""

    @pytest.fixture()
    def schema(self) -> dict:
        return _load_json(_SCHEMA_ROOT / "audit_contract.v1.schema.json")

    def test_schema_id(self, schema: dict) -> None:
        assert schema["$id"] == "governance/schemas/audit_contract.v1.schema.json"

    def test_contract_version_const(self, schema: dict) -> None:
        assert schema["properties"]["contract_version"]["const"] == CONTRACT_VERSION

    def test_lifecycle_invariant_fields_present(self, schema: dict) -> None:
        inv_schema = schema["$defs"]["LifecycleInvariant"]
        required = set(inv_schema["required"])
        expected = {
            "expected_record_status",
            "expected_integrity_status",
            "requires_finalized_at",
            "forbids_finalized_at",
            "requires_finalization_errors",
            "forbids_finalization_errors",
        }
        assert required == expected

    def test_expected_artifact_schemas_have_backing_schema_files(self) -> None:
        schema_file_by_id = {
            "governance.run-manifest.v1": "run_manifest.v1.schema.json",
            "governance.work-run.snapshot.v2": "work_run_snapshot.v2.schema.json",
            "governance.provenance-record.v1": "provenance_record.v1.schema.json",
            "governance.ticket-record.v1": "ticket_record.v1.schema.json",
            "governance.review-decision-record.v1": "review_decision_record.v1.schema.json",
            "governance.outcome-record.v1": "outcome_record.v1.schema.json",
            "governance.evidence-index.v1": "evidence_index.v1.schema.json",
            "governance.finalization-record.v1": "finalization_record.v1.schema.json",
            "governance.run-checksums.v1": "run_checksums.v1.schema.json",
            "governance.repository-manifest.v1": "repository_manifest.v1.schema.json",
        }
        for _, schema_id in EXPECTED_SCHEMAS.items():
            schema_file = schema_file_by_id.get(schema_id)
            assert schema_file is not None, f"No schema file mapping for {schema_id}"
            assert (_SCHEMA_ROOT / schema_file).is_file(), f"Missing schema file: {schema_file}"

    def test_run_manifest_schema_includes_governance_fields(self) -> None:
        run_manifest_schema = _load_json(_SCHEMA_ROOT / "run_manifest.v1.schema.json")
        required = set(run_manifest_schema.get("required", []))
        assert RUN_MANIFEST_GOVERNANCE_FIELDS.issubset(required)
        properties = run_manifest_schema.get("properties", {})
        assert set(properties["resolvedOperatingMode"]["enum"]) == ALLOWED_RESOLVED_OPERATING_MODES
        assert properties["verifyPolicyVersion"]["pattern"] == VERIFY_POLICY_VERSION_RE.pattern


# ---------------------------------------------------------------------------
# Failure Model ↔ JSON Schema Consistency
# ---------------------------------------------------------------------------

class TestFailureModelSchemaConsistency:
    """Verify failure model matches failure_report.v1.schema.json."""

    @pytest.fixture()
    def schema(self) -> dict:
        return _load_json(_SCHEMA_ROOT / "failure_report.v1.schema.json")

    def test_schema_version_const(self, schema: dict) -> None:
        assert schema["properties"]["schema"]["const"] == "governance.failure-report.v1"

    def test_contract_version_const(self, schema: dict) -> None:
        assert schema["properties"]["contract_version"]["const"] == FAILURE_CONTRACT_VERSION

    def test_severity_enum_matches_model(self, schema: dict) -> None:
        schema_severities = set(schema["properties"]["overall_severity"]["enum"])
        model_severities = {s.value for s in FailureSeverity}
        assert schema_severities == model_severities

    def test_category_enum_matches_model(self, schema: dict) -> None:
        detail_schema = schema["$defs"]["FailureDetail"]
        schema_categories = set(detail_schema["properties"]["category"]["enum"])
        model_categories = {c.value for c in FailureCategory}
        assert schema_categories == model_categories

    def test_strategy_enum_matches_model(self, schema: dict) -> None:
        action_schema = schema["$defs"]["RecoveryAction"]
        schema_strategies = set(action_schema["properties"]["strategy"]["enum"])
        model_strategies = {s.value for s in RecoveryStrategy}
        assert schema_strategies == model_strategies


# ---------------------------------------------------------------------------
# Schema Identifier Validation
# ---------------------------------------------------------------------------

class TestSchemaIdentifierValidation:
    """Verify schema identifier validation works for all known schemas."""

    def test_valid_manifest_schema(self) -> None:
        violations = validate_schema_identifier("run-manifest.json", "governance.run-manifest.v1")
        assert violations == []

    def test_invalid_manifest_schema(self) -> None:
        violations = validate_schema_identifier("run-manifest.json", "evil.v1")
        assert len(violations) == 1
        assert violations[0].code == "SCHEMA_MISMATCH"

    def test_unknown_artifact_passes(self) -> None:
        violations = validate_schema_identifier("unknown.json", "any.schema")
        assert violations == []

    def test_all_expected_schemas_valid(self) -> None:
        for artifact, expected_schema in EXPECTED_SCHEMAS.items():
            violations = validate_schema_identifier(artifact, expected_schema)
            assert violations == [], f"Schema validation failed for {artifact}"
