#!/usr/bin/env python3
"""Governed Export CLI — Entrypoint for governance-gated archive export.

CLI tool that exports a finalized run archive through the governance pipeline.
Checks access control, retention policy, regulated mode, and classification
before producing an export bundle.

Usage:
    python -m governance_runtime.entrypoints.governed_export_cli \\
        --archive-path /path/to/runs/run-20260101T000000Z \\
        --export-path /path/to/export/output \\
        --repo-fingerprint abc123def456abc123def456 \\
        --run-id run-20260101T000000Z \\
        --exported-by operator@company.com \\
        [--role operator|auditor|compliance_officer] \\
        [--apply-redaction] \\
        [--redaction-max-level public|internal|confidential|restricted] \\
        [--legal-holds-dir /path/to/holds/]

Design:
    - CLI wrapper around governance_orchestrator.governance_export()
    - JSON output on stdout for machine consumption
    - Non-zero exit code on governance failure
    - Validates all governance rules before proceeding
    - Zero external dependencies (stdlib + governance modules)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from governance_runtime.domain.access_control import Role
from governance_runtime.domain.classification import ClassificationLevel
from governance_runtime.domain.regulated_mode import DEFAULT_CONFIG, RegulatedModeConfig, RegulatedModeState
from governance_runtime.infrastructure.governance_hooks import detect_regulated_mode
from governance_runtime.infrastructure.governance_orchestrator import (
    build_governance_summary,
    governance_export,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_role(value: str) -> Role:
    """Parse a role string into a Role enum."""
    try:
        return Role(value.strip().lower())
    except ValueError:
        valid = ", ".join(r.value for r in Role)
        raise argparse.ArgumentTypeError(f"invalid role '{value}', valid: {valid}")


def _parse_classification_level(value: str) -> ClassificationLevel:
    """Parse a classification level string."""
    try:
        return ClassificationLevel(value.strip().lower())
    except ValueError:
        valid = ", ".join(cl.value for cl in ClassificationLevel)
        raise argparse.ArgumentTypeError(f"invalid classification level '{value}', valid: {valid}")


def _payload(status: str, **kwargs: object) -> dict[str, object]:
    out: dict[str, object] = {"status": status}
    out.update(kwargs)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Governance-gated export of finalized run archives",
    )
    parser.add_argument("--archive-path", required=True, help="Path to finalized run archive directory")
    parser.add_argument("--export-path", required=True, help="Destination path for exported bundle")
    parser.add_argument("--repo-fingerprint", required=True, help="Repository fingerprint (24 hex chars)")
    parser.add_argument("--run-id", required=True, help="Run identifier")
    parser.add_argument("--exported-by", required=True, help="Identity of the exporter")
    parser.add_argument("--role", type=_parse_role, default=Role.OPERATOR, help="Role performing the export")
    parser.add_argument(
        "--approver-role",
        type=_parse_role,
        default=None,
        help="Independent approver role for four-eyes actions in regulated mode",
    )
    parser.add_argument("--apply-redaction", action="store_true", help="Apply field-level redaction to export")
    parser.add_argument(
        "--redaction-max-level",
        type=_parse_classification_level,
        default=ClassificationLevel.INTERNAL,
        help="Maximum classification level visible in export",
    )
    parser.add_argument("--legal-holds-dir", default=None, help="Directory containing legal hold JSON records")
    parser.add_argument("--workspace-root", default=None, help="Workspace root for regulated mode detection")
    parser.add_argument("--quiet", action="store_true", help="Emit JSON payload only")
    args = parser.parse_args(argv)

    archive_path = Path(args.archive_path)
    export_path = Path(args.export_path)
    exported_at = _now_iso()

    if not archive_path.is_dir():
        payload = _payload(
            "blocked",
            reason="archive-path-not-found",
            archive_path=str(archive_path),
            recovery_action="verify archive path exists and contains finalized archive",
        )
        print(json.dumps(payload, ensure_ascii=True))
        return 2

    # Detect regulated mode
    regulated_mode_config = DEFAULT_CONFIG
    if args.workspace_root:
        workspace_root = Path(args.workspace_root)
        if workspace_root.is_dir():
            regulated_mode_config = detect_regulated_mode(workspace_root)

    legal_holds_dir = Path(args.legal_holds_dir) if args.legal_holds_dir else None

    try:
        pipeline_result, export_manifest = governance_export(
            archive_path=archive_path,
            export_path=export_path,
            repo_fingerprint=args.repo_fingerprint,
            run_id=args.run_id,
            exported_at=exported_at,
            exported_by=args.exported_by,
            role=args.role,
            approver_role=args.approver_role,
            regulated_mode_config=regulated_mode_config,
            apply_redaction=args.apply_redaction,
            redaction_max_level=args.redaction_max_level,
            legal_holds_dir=legal_holds_dir,
        )
    except Exception as exc:
        payload = _payload(
            "blocked",
            reason="governance-export-failed",
            error=str(exc),
            recovery_action="check archive integrity and retry",
        )
        print(json.dumps(payload, ensure_ascii=True))
        return 2

    summary = build_governance_summary(pipeline_result)

    if export_manifest is None:
        # Governance blocked the export
        payload = _payload(
            "blocked",
            reason="governance-checks-failed",
            governance_passed=pipeline_result.governance_passed,
            archive_valid=pipeline_result.archive_valid,
            contract_valid=pipeline_result.contract_valid,
            access_decision=pipeline_result.access_evaluation.decision.value,
            recovery_action="resolve governance violations before retrying export",
            governance_summary=summary,
        )
        print(json.dumps(payload, ensure_ascii=True))
        return 1

    # Export succeeded
    payload = _payload(
        "ok",
        reason="governance-export-completed",
        repo_fingerprint=args.repo_fingerprint,
        run_id=args.run_id,
        export_path=str(export_path),
        exported_at=exported_at,
        exported_by=args.exported_by,
        governance_passed=pipeline_result.governance_passed,
        redaction_applied=export_manifest.redaction_applied,
        files_included=list(export_manifest.files_included),
        governance_summary=summary,
    )
    print(json.dumps(payload, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
