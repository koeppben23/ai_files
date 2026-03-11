"""Governance Orchestrator — Integration layer wiring all audit modules.

Ties together the 6 domain modules and 2 infrastructure adapters into a
single coherent pipeline that can be called after archive_active_run()
completes. This is the integration seam that turns the domain modules
from standalone code into a production-ready governance chain.

Design:
    - Additive only: no modifications to existing production code
    - Wraps archive_active_run() output with governance enrichment
    - Pure functions where possible; I/O only in explicitly named functions
    - Fail-closed: any governance check failure produces a report, never silently passes
    - Zero external dependencies (stdlib only + governance modules)

Usage:
    # After archive_active_run() produces a finalized archive:
    result = run_governance_pipeline(
        archive_path=...,
        repo_fingerprint=...,
        run_id=...,
        observed_at=...,
        regulated_mode_config=...,
        role=Role.OPERATOR,
    )
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from governance.domain.access_control import (
    AccessDecision,
    AccessEvaluation,
    Action,
    Role,
    evaluate_access,
)
from governance.domain.audit_contract import (
    AuditContractViolation,
    validate_cross_document_consistency,
    validate_run_lifecycle_invariants,
    validate_run_type_artifacts,
    validate_schema_identifier,
)
from governance.domain.classification import (
    ClassificationLevel,
    get_classification_summary,
)
from governance.domain.failure_model import (
    FailureReport,
    build_failure_report,
    failure_report_to_dict,
)
from governance.domain.regulated_mode import (
    DEFAULT_CONFIG,
    RegulatedModeConfig,
    RegulatedModeEvaluation,
    evaluate_mode,
    regulated_mode_summary,
)
from governance.domain.retention import (
    DeletionDecision,
    DeletionEvaluation,
    LegalHold,
    RetentionPolicy,
    build_retention_policy,
    evaluate_deletion,
    get_effective_retention_days,
    get_retention_summary,
)
from governance.infrastructure.archive_export import (
    export_finalized_bundle,
    load_legal_holds,
    validate_archive_for_export,
    ArchiveExportManifest,
)
from governance.infrastructure.redaction import redact_archive


# ---------------------------------------------------------------------------
# Pipeline result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GovernancePipelineResult:
    """Complete result of running the governance pipeline on a finalized archive."""
    run_id: str
    repo_fingerprint: str
    observed_at: str

    # Archive validation
    archive_valid: bool
    archive_errors: tuple[str, ...]

    # Contract validation
    contract_violations: tuple[AuditContractViolation, ...]
    contract_valid: bool

    # Access evaluation
    access_evaluation: AccessEvaluation

    # Regulated mode
    regulated_mode: RegulatedModeEvaluation

    # Classification summary
    classification_summary: dict[str, Any]

    # Retention
    retention_policy: RetentionPolicy
    deletion_evaluation: Optional[DeletionEvaluation]

    # Failure report (if any violations found)
    failure_report: Optional[FailureReport]

    # Overall pass/fail
    governance_passed: bool


# ---------------------------------------------------------------------------
# Contract validation (pure)
# ---------------------------------------------------------------------------

def validate_archive_contract(
    archive_path: Path,
) -> list[AuditContractViolation]:
    """Validate all audit contract invariants on a finalized archive.

    Reads the archive JSON files and checks:
    - Run lifecycle invariants (status/record/integrity consistency)
    - Cross-document consistency (run_id, repo_fingerprint, timestamps match)
    - Run type artifact rules (plan/pr records present when required)
    - Schema identifiers

    Returns:
        List of contract violations (empty = all checks passed)
    """
    violations: list[AuditContractViolation] = []

    manifest_path = archive_path / "run-manifest.json"
    metadata_path = archive_path / "metadata.json"
    provenance_path = archive_path / "provenance-record.json"

    # Load documents
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        violations.append(AuditContractViolation(
            code="MANIFEST_UNREADABLE",
            message="Cannot read run-manifest.json",
            path=str(manifest_path),
        ))
        return violations

    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        violations.append(AuditContractViolation(
            code="METADATA_UNREADABLE",
            message="Cannot read metadata.json",
            path=str(metadata_path),
        ))
        return violations

    try:
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        violations.append(AuditContractViolation(
            code="PROVENANCE_UNREADABLE",
            message="Cannot read provenance-record.json",
            path=str(provenance_path),
        ))
        return violations

    # Schema checks
    for artifact_name, doc in [
        ("run-manifest.json", manifest),
        ("metadata.json", metadata),
        ("provenance-record.json", provenance),
    ]:
        schema = str(doc.get("schema", ""))
        violations.extend(validate_schema_identifier(artifact_name, schema))

    # Lifecycle invariants
    violations.extend(validate_run_lifecycle_invariants(
        run_status=str(manifest.get("run_status", "")),
        record_status=str(manifest.get("record_status", "")),
        integrity_status=str(manifest.get("integrity_status", "")),
        finalized_at=manifest.get("finalized_at"),
        finalization_errors=manifest.get("finalization_errors"),
    ))

    # Cross-document consistency
    directory_run_id = archive_path.name
    violations.extend(validate_cross_document_consistency(
        manifest_run_id=str(manifest.get("run_id", "")),
        metadata_run_id=str(metadata.get("run_id", "")),
        provenance_run_id=str(provenance.get("run_id", "")),
        directory_run_id=directory_run_id,
        manifest_repo=str(manifest.get("repo_fingerprint", "")),
        metadata_repo=str(metadata.get("repo_fingerprint", "")),
        provenance_repo=str(provenance.get("repo_fingerprint", "")),
        manifest_materialized_at=str(manifest.get("materialized_at", "")),
        metadata_archived_at=str(metadata.get("archived_at", "")),
        provenance_materialized_at=str(
            provenance.get("timestamps", {}).get("materialized_at", "")
            if isinstance(provenance.get("timestamps"), dict)
            else ""
        ),
    ))

    # Run type artifact rules
    required = manifest.get("required_artifacts", {})
    required_map = required if isinstance(required, dict) else {}
    plan_path = archive_path / "plan-record.json"
    pr_path = archive_path / "pr-record.json"
    violations.extend(validate_run_type_artifacts(
        run_type=str(manifest.get("run_type", "")),
        plan_record_required=bool(required_map.get("plan_record")),
        pr_record_required=bool(required_map.get("pr_record")),
        plan_record_archived=plan_path.is_file(),
        pr_record_archived=pr_path.is_file(),
    ))

    return violations


# ---------------------------------------------------------------------------
# Governance pipeline (main entry point)
# ---------------------------------------------------------------------------

def run_governance_pipeline(
    *,
    archive_path: Path,
    repo_fingerprint: str,
    run_id: str,
    observed_at: str,
    regulated_mode_config: RegulatedModeConfig = DEFAULT_CONFIG,
    role: Role = Role.SYSTEM,
    action: Action = Action.VERIFY_ARCHIVE,
    approver_role: Role | None = None,
    classification_level: str = "internal",
    archived_at_days_ago: int = 0,
    legal_holds: Sequence[LegalHold] = (),
) -> GovernancePipelineResult:
    """Run the full governance pipeline on a finalized archive.

    This is the primary integration point that wires all domain modules
    together. It:
    1. Validates the archive for export readiness
    2. Checks audit contract invariants
    3. Evaluates access control
    4. Evaluates regulated mode
    5. Produces classification summary
    6. Evaluates retention/deletion eligibility
    7. Generates failure report if any violations found

    Args:
        archive_path: Path to the finalized archive directory
        repo_fingerprint: Repository fingerprint (24 hex chars)
        run_id: Run identifier
        observed_at: RFC3339 UTC Z timestamp
        regulated_mode_config: Regulated mode configuration
        role: Role performing the governance check
        action: Action being evaluated
        classification_level: Data classification level for retention
        archived_at_days_ago: Days since archive was created
        legal_holds: Active legal holds to check

    Returns:
        GovernancePipelineResult with all evaluation results
    """
    # 1. Archive validation
    archive_valid, archive_errors = validate_archive_for_export(archive_path)

    # 2. Contract validation
    contract_violations = validate_archive_contract(archive_path)
    contract_valid = len(contract_violations) == 0

    # 3. Access control
    regulated_eval = evaluate_mode(regulated_mode_config)
    access_eval = evaluate_access(
        role=role,
        action=action,
        regulated_mode_active=regulated_eval.is_active,
        approver_role=approver_role,
    )

    # 4. Classification summary
    class_summary = get_classification_summary()

    # 5. Retention policy & deletion evaluation
    retention_policy = build_retention_policy(
        regulated_mode_minimum_days=(
            regulated_mode_config.minimum_retention_days
            if regulated_eval.is_active
            else 0
        ),
        legal_holds=legal_holds,
    )

    deletion_eval = evaluate_deletion(
        run_id=run_id,
        repo_fingerprint=repo_fingerprint,
        classification_level=classification_level,
        archived_at_days_ago=archived_at_days_ago,
        compliance_framework=regulated_mode_config.compliance_framework,
        regulated_mode_active=regulated_eval.is_active,
        regulated_mode_minimum_days=regulated_mode_config.minimum_retention_days,
        legal_holds=legal_holds,
    )

    # 6. Failure report (if violations exist)
    error_messages: list[str] = list(archive_errors)
    for v in contract_violations:
        error_messages.append(f"{v.code}: {v.message}")
    if access_eval.decision == AccessDecision.DENY:
        error_messages.append(f"ACCESS_DENIED: {access_eval.reason}")

    failure_report: Optional[FailureReport] = None
    if error_messages:
        failure_report = build_failure_report(
            run_id=run_id,
            repo_fingerprint=repo_fingerprint,
            observed_at=observed_at,
            error_messages=error_messages,
        )

    # 7. Overall governance decision
    governance_passed = (
        archive_valid
        and contract_valid
        and access_eval.decision == AccessDecision.ALLOW
    )

    return GovernancePipelineResult(
        run_id=run_id,
        repo_fingerprint=repo_fingerprint,
        observed_at=observed_at,
        archive_valid=archive_valid,
        archive_errors=tuple(archive_errors),
        contract_violations=tuple(contract_violations),
        contract_valid=contract_valid,
        access_evaluation=access_eval,
        regulated_mode=regulated_eval,
        classification_summary=class_summary,
        retention_policy=retention_policy,
        deletion_evaluation=deletion_eval,
        failure_report=failure_report,
        governance_passed=governance_passed,
    )


# ---------------------------------------------------------------------------
# Convenience: governance-enriched export
# ---------------------------------------------------------------------------

def governance_export(
    *,
    archive_path: Path,
    export_path: Path,
    repo_fingerprint: str,
    run_id: str,
    exported_at: str,
    exported_by: str,
    role: Role = Role.OPERATOR,
    approver_role: Role | None = None,
    regulated_mode_config: RegulatedModeConfig = DEFAULT_CONFIG,
    apply_redaction: bool = False,
    redaction_max_level: ClassificationLevel = ClassificationLevel.INTERNAL,
    legal_holds_dir: Optional[Path] = None,
) -> tuple[GovernancePipelineResult, Optional[ArchiveExportManifest]]:
    """Governance-gated export: validates all governance rules before exporting.

    Runs the full governance pipeline and only proceeds with export if all
    checks pass and the role has export permission.

    Args:
        archive_path: Source finalized archive directory
        export_path: Destination for the exported bundle
        repo_fingerprint: Repository fingerprint
        run_id: Run identifier
        exported_at: RFC3339 UTC Z timestamp
        exported_by: Identity of the exporter
        role: Role performing the export
        regulated_mode_config: Regulated mode configuration
        apply_redaction: Whether to apply redaction
        redaction_max_level: Maximum classification level in output
        legal_holds_dir: Directory containing legal hold records

    Returns:
        Tuple of (GovernancePipelineResult, ArchiveExportManifest or None)
        Manifest is None if governance checks failed.
    """
    # Load legal holds if directory provided
    holds: list[LegalHold] = []
    if legal_holds_dir is not None:
        holds = load_legal_holds(legal_holds_dir)

    # Run governance pipeline
    pipeline_result = run_governance_pipeline(
        archive_path=archive_path,
        repo_fingerprint=repo_fingerprint,
        run_id=run_id,
        observed_at=exported_at,
        regulated_mode_config=regulated_mode_config,
        role=role,
        action=Action.EXPORT_ARCHIVE,
        approver_role=approver_role,
        legal_holds=holds,
    )

    if not pipeline_result.governance_passed:
        return pipeline_result, None

    # Access check for export specifically
    regulated_eval = pipeline_result.regulated_mode
    export_access = evaluate_access(
        role=role,
        action=Action.EXPORT_ARCHIVE,
        regulated_mode_active=regulated_eval.is_active,
        approver_role=approver_role,
    )
    if export_access.decision == AccessDecision.DENY:
        return pipeline_result, None

    # Proceed with export
    manifest = export_finalized_bundle(
        archive_path=archive_path,
        export_path=export_path,
        repo_fingerprint=repo_fingerprint,
        run_id=run_id,
        exported_at=exported_at,
        exported_by=exported_by,
        apply_redaction=apply_redaction,
        redaction_max_level=redaction_max_level,
    )

    return pipeline_result, manifest


# ---------------------------------------------------------------------------
# Convenience: governance summary (for audit trail)
# ---------------------------------------------------------------------------

def build_governance_summary(
    result: GovernancePipelineResult,
) -> dict[str, Any]:
    """Build a JSON-serializable summary of governance pipeline results.

    Intended for writing alongside archive artifacts as an audit trail.
    """
    summary: dict[str, Any] = {
        "schema": "governance.governance-summary.v1",
        "run_id": result.run_id,
        "repo_fingerprint": result.repo_fingerprint,
        "observed_at": result.observed_at,
        "governance_passed": result.governance_passed,
        "archive_valid": result.archive_valid,
        "archive_errors": list(result.archive_errors),
        "contract_valid": result.contract_valid,
        "contract_violation_count": len(result.contract_violations),
        "access_decision": result.access_evaluation.decision.value,
        "access_role": result.access_evaluation.role.value,
        "access_action": result.access_evaluation.action.value,
        "regulated_mode_active": result.regulated_mode.is_active,
        "regulated_mode_state": result.regulated_mode.state.value,
        "classification_total_fields": result.classification_summary.get("total_classified_fields", 0),
    }

    if result.deletion_evaluation is not None:
        summary["deletion_decision"] = result.deletion_evaluation.decision.value
        summary["deletion_reason"] = result.deletion_evaluation.reason

    if result.failure_report is not None:
        summary["failure_report"] = failure_report_to_dict(result.failure_report)

    return summary


__all__ = [
    "GovernancePipelineResult",
    "validate_archive_contract",
    "run_governance_pipeline",
    "governance_export",
    "build_governance_summary",
]
