"""Governed Archive — Wrapper combining archive_active_run() with governance pipeline.

This module provides `governed_archive_active_run()`, a drop-in replacement
for `archive_active_run()` that additionally runs the governance pipeline
after a successful archive. This is the primary integration point for
wiring the governance modules into the production runtime.

Usage:
    # In new_work_session.py, replace:
    #   archived = archive_active_run(...)
    # with:
    #   archived = governed_archive_active_run(...)

Design:
    - Wraps archive_active_run() — delegates all archive work unchanged
    - After successful archive, runs governance pipeline via hooks
    - Governance failures do NOT block the archive result
    - Returns the same WorkRunArchiveResult as archive_active_run()
    - The governance result is available via the additional return field
    - Zero external dependencies (stdlib + governance modules)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from governance.infrastructure.work_run_archive import (
    WorkRunArchiveResult,
    archive_active_run,
)
from governance.infrastructure.governance_hooks import (
    GovernanceHookResult,
    detect_regulated_mode,
    run_post_archive_governance,
)
from governance.infrastructure.workspace_paths import run_dir
from governance.domain.access_control import Role
from governance.domain.regulated_mode import RegulatedModeConfig


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GovernedArchiveResult:
    """Extended archive result including governance pipeline outcome."""
    archive: WorkRunArchiveResult
    governance: GovernanceHookResult


# ---------------------------------------------------------------------------
# Governed archive function
# ---------------------------------------------------------------------------

def governed_archive_active_run(
    *,
    workspaces_home: Path,
    repo_fingerprint: str,
    run_id: str,
    observed_at: str,
    session_state_document: Mapping[str, object],
    state_view: Mapping[str, object],
    write_json_atomic: Callable[[Path, Mapping[str, object]], None] | None = None,
    workspace_root: Optional[Path] = None,
    events_path: Optional[Path] = None,
    regulated_mode_config: Optional[RegulatedModeConfig] = None,
) -> GovernedArchiveResult:
    """Archive active run and then run the governance pipeline.

    This is a wrapper around archive_active_run() that adds governance
    pipeline execution after the archive completes. The archive result
    is always returned, even if governance fails.

    Args:
        workspaces_home: Base workspaces directory
        repo_fingerprint: Repository fingerprint (24 hex chars)
        run_id: Run identifier
        observed_at: RFC3339 UTC Z timestamp
        session_state_document: Full session state document
        state_view: SESSION_STATE view dict
        write_json_atomic: Optional custom JSON writer
        workspace_root: Workspace root for regulated mode detection
        events_path: Path to events.jsonl
        regulated_mode_config: Override for regulated mode config

    Returns:
        GovernedArchiveResult with both archive and governance results

    Raises:
        Any exception from archive_active_run() — governance never raises.
    """
    # Step 1: Run the standard archive (may raise)
    archive_result = archive_active_run(
        workspaces_home=workspaces_home,
        repo_fingerprint=repo_fingerprint,
        run_id=run_id,
        observed_at=observed_at,
        session_state_document=session_state_document,
        state_view=state_view,
        write_json_atomic=write_json_atomic,
    )

    # Step 2: Run governance pipeline (never raises)
    archive_path = run_dir(workspaces_home, repo_fingerprint, run_id)

    # Default workspace_root to the repo's workspace dir
    if workspace_root is None:
        workspace_root = workspaces_home / repo_fingerprint

    governance_result = run_post_archive_governance(
        archive_path=archive_path,
        repo_fingerprint=repo_fingerprint,
        run_id=run_id,
        observed_at=observed_at,
        workspace_root=workspace_root,
        events_path=events_path,
        regulated_mode_config=regulated_mode_config,
    )

    return GovernedArchiveResult(
        archive=archive_result,
        governance=governance_result,
    )


__all__ = [
    "GovernedArchiveResult",
    "governed_archive_active_run",
]
