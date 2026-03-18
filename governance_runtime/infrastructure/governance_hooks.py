"""Governance Hooks — Post-archive hook wiring orchestrator into runtime.

This module provides the integration seam between the existing production
runtime (archive_active_run → purge_runtime_artifacts) and the governance
pipeline. It is designed to be called from new_work_session.py after
archiving completes.

Design:
    - Fail-open for the archive path: governance failures are logged but do NOT
      block the new work session from being created. The rationale is that the
      archive has already been finalized and verified by io_verify — governance
      enrichment is an additional audit layer, not a gate on session creation.
    - Writes governance-summary.json into the archive directory
    - Writes governance events to events.jsonl
    - Uses governance_config_loader for config validation
    - Zero external dependencies (stdlib + governance modules)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from governance_runtime.domain.access_control import Action, Role
from governance_runtime.domain.regulated_mode import (
    DEFAULT_CONFIG,
    RegulatedModeConfig,
    RegulatedModeState,
)
from governance_runtime.domain.retention import LegalHold
from governance_runtime.infrastructure.governance_config_loader import (
    load_all_governance_configs,
    validate_all_governance_configs,
)
from governance_runtime.infrastructure.governance_orchestrator import (
    GovernancePipelineResult,
    build_governance_summary,
    run_governance_pipeline,
)
from governance_runtime.infrastructure.fs_atomic import atomic_write_json


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GovernanceHookResult:
    """Result of the post-archive governance hook."""
    executed: bool
    governance_passed: bool
    summary_path: Optional[Path]
    error: str


# ---------------------------------------------------------------------------
# Configuration detection
# ---------------------------------------------------------------------------

_REGULATED_MODE_ENV_FILE = "governance-mode.json"


def detect_regulated_mode(workspace_root: Path) -> RegulatedModeConfig:
    """Detect regulated mode configuration from the workspace.

    Looks for a governance-mode.json file in the workspace root.
    If not found or invalid, returns the default (inactive) config.
    This is fail-safe: missing config = non-regulated mode.
    """
    mode_file = workspace_root / _REGULATED_MODE_ENV_FILE
    if not mode_file.is_file():
        return DEFAULT_CONFIG

    try:
        payload = json.loads(mode_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return DEFAULT_CONFIG

    if not isinstance(payload, dict):
        return DEFAULT_CONFIG

    state_str = str(payload.get("state", "inactive")).strip().lower()
    try:
        state = RegulatedModeState(state_str)
    except ValueError:
        state = RegulatedModeState.INACTIVE

    return RegulatedModeConfig(
        state=state,
        customer_id=str(payload.get("customer_id", "")),
        compliance_framework=str(payload.get("compliance_framework", "")),
        activated_at=str(payload.get("activated_at", "")),
        activated_by=str(payload.get("activated_by", "")),
        minimum_retention_days=int(payload.get("minimum_retention_days", 3650)),
    )


# ---------------------------------------------------------------------------
# Post-archive governance hook
# ---------------------------------------------------------------------------

def run_post_archive_governance(
    *,
    archive_path: Path,
    repo_fingerprint: str,
    run_id: str,
    observed_at: str,
    workspace_root: Path,
    events_path: Optional[Path] = None,
    regulated_mode_config: Optional[RegulatedModeConfig] = None,
    role: Role = Role.SYSTEM,
    legal_holds: tuple[LegalHold, ...] = (),
) -> GovernanceHookResult:
    """Run governance pipeline as a post-archive hook.

    Called after archive_active_run() succeeds. Runs the full governance
    pipeline and writes a governance-summary.json into the archive directory.

    This function NEVER raises — all errors are caught and returned in the
    result. The caller (new_work_session) should continue regardless of the
    governance outcome.

    Args:
        archive_path: Path to the finalized archive directory
        repo_fingerprint: Repository fingerprint (24 hex chars)
        run_id: Run identifier
        observed_at: RFC3339 UTC Z timestamp
        workspace_root: Workspace root for detecting regulated mode
        events_path: Path to events.jsonl for logging (optional)
        regulated_mode_config: Override for regulated mode config
        role: Role performing the check (default: SYSTEM)
        legal_holds: Active legal holds

    Returns:
        GovernanceHookResult with execution status
    """
    try:
        # Detect or use provided regulated mode config
        if regulated_mode_config is None:
            regulated_mode_config = detect_regulated_mode(workspace_root)

        # Run governance pipeline
        pipeline_result = run_governance_pipeline(
            archive_path=archive_path,
            repo_fingerprint=repo_fingerprint,
            run_id=run_id,
            observed_at=observed_at,
            regulated_mode_config=regulated_mode_config,
            role=role,
            action=Action.VERIFY_ARCHIVE,
            legal_holds=legal_holds,
        )

        # Write governance summary to archive directory
        summary = build_governance_summary(pipeline_result)
        summary_path = archive_path / "governance-summary.json"
        atomic_write_json(summary_path, summary)

        # Log governance event
        if events_path is not None:
            _append_governance_event(
                events_path,
                event="governance_pipeline_completed",
                run_id=run_id,
                repo_fingerprint=repo_fingerprint,
                observed_at=observed_at,
                governance_passed=pipeline_result.governance_passed,
                archive_valid=pipeline_result.archive_valid,
                contract_valid=pipeline_result.contract_valid,
            )

        return GovernanceHookResult(
            executed=True,
            governance_passed=pipeline_result.governance_passed,
            summary_path=summary_path,
            error="",
        )

    except Exception as exc:
        # Log the error but do not propagate
        if events_path is not None:
            try:
                _append_governance_event(
                    events_path,
                    event="governance_pipeline_failed",
                    run_id=run_id,
                    repo_fingerprint=repo_fingerprint,
                    observed_at=observed_at,
                    error=str(exc),
                )
            except Exception:
                pass

        return GovernanceHookResult(
            executed=False,
            governance_passed=False,
            summary_path=None,
            error=str(exc),
        )


# ---------------------------------------------------------------------------
# Config validation hook
# ---------------------------------------------------------------------------

def validate_governance_configs_at_startup() -> dict[str, list[str]]:
    """Validate all governance policy configs.

    Intended to be called at application startup to detect configuration
    drift early. Returns a dict mapping config filename to validation errors.
    Empty error lists = all configs valid.

    This function NEVER raises — returns errors in the result dict.
    """
    try:
        return validate_all_governance_configs()
    except Exception as exc:
        return {"__loader_error__": [str(exc)]}


# ---------------------------------------------------------------------------
# Event logging helpers
# ---------------------------------------------------------------------------

def _append_governance_event(
    events_path: Path,
    *,
    event: str,
    run_id: str,
    repo_fingerprint: str,
    observed_at: str,
    **extra: Any,
) -> None:
    """Append a governance event to events.jsonl."""
    record: dict[str, Any] = {
        "event": event,
        "observed_at": observed_at,
        "repo_fingerprint": repo_fingerprint,
        "run_id": run_id,
    }
    record.update(extra)
    events_path.parent.mkdir(parents=True, exist_ok=True)
    with events_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=True, separators=(",", ":")) + "\n")


__all__ = [
    "GovernanceHookResult",
    "detect_regulated_mode",
    "run_post_archive_governance",
    "validate_governance_configs_at_startup",
]
