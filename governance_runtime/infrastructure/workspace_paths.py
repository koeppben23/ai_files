"""SSOT path utilities for workspace-scoped artifacts.

All phase artifacts are written deterministically under:
    ${WORKSPACES_HOME}/<repo_fingerprint>/

The repo_fingerprint is a canonical 24-hex hash derived from:
    - Git remote URL: SHA256("repo:" + canonical_remote)[:24]
    - Local path: SHA256("repo:local:" + normalized_path)[:24]

This module provides canonical path functions for all persisted artifacts.
Each function returns a Path object for a specific artifact under the
workspace directory.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path


def workspace_root(workspaces_home: Path, repo_fingerprint: str) -> Path:
    """Get the root directory for a repository's workspace.
    
    Args:
        workspaces_home: The base workspaces directory.
        repo_fingerprint: The canonical 24-hex fingerprint.
    
    Returns:
        Path to ${WORKSPACES_HOME}/${fingerprint}/
    """
    return workspaces_home / repo_fingerprint


def session_state_path(workspaces_home: Path, repo_fingerprint: str) -> Path:
    """Get the path to a repository's SESSION_STATE.json file.
    
    Args:
        workspaces_home: The base workspaces directory.
        repo_fingerprint: The canonical 24-hex fingerprint.
    
    Returns:
        Path to ${WORKSPACES_HOME}/${fingerprint}/SESSION_STATE.json
    """
    return workspaces_home / repo_fingerprint / "SESSION_STATE.json"


def repo_cache_path(workspaces_home: Path, repo_fingerprint: str) -> Path:
    """Get the path to a repository's repo-cache.yaml file.
    
    Args:
        workspaces_home: The base workspaces directory.
        repo_fingerprint: The canonical 24-hex fingerprint.
    
    Returns:
        Path to ${WORKSPACES_HOME}/${fingerprint}/repo-cache.yaml
    """
    return workspaces_home / repo_fingerprint / "repo-cache.yaml"


def repo_map_digest_path(workspaces_home: Path, repo_fingerprint: str) -> Path:
    """Get the path to a repository's repo-map-digest.md file.
    
    Args:
        workspaces_home: The base workspaces directory.
        repo_fingerprint: The canonical 24-hex fingerprint.
    
    Returns:
        Path to ${WORKSPACES_HOME}/${fingerprint}/repo-map-digest.md
    """
    return workspaces_home / repo_fingerprint / "repo-map-digest.md"


def workspace_memory_path(workspaces_home: Path, repo_fingerprint: str) -> Path:
    """Get the path to a repository's workspace-memory.yaml file.
    
    Args:
        workspaces_home: The base workspaces directory.
        repo_fingerprint: The canonical 24-hex fingerprint.
    
    Returns:
        Path to ${WORKSPACES_HOME}/${fingerprint}/workspace-memory.yaml
    """
    return workspaces_home / repo_fingerprint / "workspace-memory.yaml"


def decision_pack_path(workspaces_home: Path, repo_fingerprint: str) -> Path:
    """Get the path to a repository's decision-pack.md file.
    
    Args:
        workspaces_home: The base workspaces directory.
        repo_fingerprint: The canonical 24-hex fingerprint.
    
    Returns:
        Path to ${WORKSPACES_HOME}/${fingerprint}/decision-pack.md
    """
    return workspaces_home / repo_fingerprint / "decision-pack.md"


def business_rules_path(workspaces_home: Path, repo_fingerprint: str) -> Path:
    """Get the path to a repository's business-rules.md file.
    
    Args:
        workspaces_home: The base workspaces directory.
        repo_fingerprint: The canonical 24-hex fingerprint.
    
    Returns:
        Path to ${WORKSPACES_HOME}/${fingerprint}/business-rules.md
    """
    return workspaces_home / repo_fingerprint / "business-rules.md"


def business_rules_status_path(workspaces_home: Path, repo_fingerprint: str) -> Path:
    """Get the path to a repository's business-rules-status.md file.

    Args:
        workspaces_home: The base workspaces directory.
        repo_fingerprint: The canonical 24-hex fingerprint.

    Returns:
        Path to ${WORKSPACES_HOME}/${fingerprint}/business-rules-status.md
    """
    return workspaces_home / repo_fingerprint / "business-rules-status.md"


def plan_record_path(workspaces_home: Path, repo_fingerprint: str) -> Path:
    """Get the path to a repository's plan-record.json file.

    Args:
        workspaces_home: The base workspaces directory.
        repo_fingerprint: The canonical 24-hex fingerprint.

    Returns:
        Path to ${WORKSPACES_HOME}/${fingerprint}/plan-record.json
    """
    return workspaces_home / repo_fingerprint / "plan-record.json"


def plan_record_archive_dir(workspaces_home: Path, repo_fingerprint: str) -> Path:
    """Get the path to the plan-record archive directory.

    Finalized plan records are rotated here when a new cycle begins.

    Args:
        workspaces_home: The base workspaces directory.
        repo_fingerprint: The canonical 24-hex fingerprint.

    Returns:
        Path to ${WORKSPACES_HOME}/${fingerprint}/plan-record-archive/
    """
    return workspaces_home / repo_fingerprint / "plan-record-archive"


def repo_identity_map_path(workspaces_home: Path, repo_fingerprint: str) -> Path:
    return workspaces_home / repo_fingerprint / "repo-identity-map.yaml"


def global_pointer_path(opencode_home: Path) -> Path:
    return opencode_home / "SESSION_STATE.json"


def evidence_dir(workspaces_home: Path, repo_fingerprint: str) -> Path:
    return workspaces_home / repo_fingerprint / "evidence"


def locks_dir(workspaces_home: Path, repo_fingerprint: str) -> Path:
    return workspaces_home / repo_fingerprint / "locks"


def runs_dir(workspaces_home: Path, repo_fingerprint: str) -> Path:
    return workspaces_home / "governance-records" / repo_fingerprint / "runs"


def _date_segments(observed_at: str) -> tuple[str, str, str]:
    if len(observed_at) >= 10:
        day = observed_at[:10]
        month = day[:7]
        year = day[:4]
        if day[4] == "-" and day[7] == "-":
            return year, month, day
    now = datetime.utcnow().strftime("%Y-%m-%d")
    return now[:4], now[:7], now


def run_dir(
    workspaces_home: Path,
    repo_fingerprint: str,
    run_id: str,
    *,
    repo_slug: str | None = None,
    observed_at: str | None = None,
) -> Path:
    if repo_slug and observed_at:
        year, month, day = _date_segments(observed_at)
        return runs_dir(workspaces_home, repo_fingerprint) / repo_slug / year / month / day / run_id
    legacy = runs_dir(workspaces_home, repo_fingerprint) / run_id
    if legacy.exists():
        return legacy
    root = runs_dir(workspaces_home, repo_fingerprint)
    for candidate in root.glob(f"*/*/*/*/{run_id}"):
        if candidate.is_dir():
            return candidate
    return legacy


def locate_run_dir(workspaces_home: Path, repo_fingerprint: str, run_id: str) -> Path:
    legacy = run_dir(workspaces_home, repo_fingerprint, run_id)
    if legacy.exists():
        return legacy

    root = runs_dir(workspaces_home, repo_fingerprint)
    for candidate in root.glob(f"*/*/*/*/{run_id}"):
        if candidate.is_dir():
            return candidate
    return legacy


def run_session_state_path(
    workspaces_home: Path,
    repo_fingerprint: str,
    run_id: str,
    *,
    repo_slug: str | None = None,
    observed_at: str | None = None,
) -> Path:
    return run_dir(
        workspaces_home,
        repo_fingerprint,
        run_id,
        repo_slug=repo_slug,
        observed_at=observed_at,
    ) / "SESSION_STATE.json"


def run_plan_record_path(
    workspaces_home: Path,
    repo_fingerprint: str,
    run_id: str,
    *,
    repo_slug: str | None = None,
    observed_at: str | None = None,
) -> Path:
    return run_dir(
        workspaces_home,
        repo_fingerprint,
        run_id,
        repo_slug=repo_slug,
        observed_at=observed_at,
    ) / "plan-record.json"


def run_metadata_path(
    workspaces_home: Path,
    repo_fingerprint: str,
    run_id: str,
    *,
    repo_slug: str | None = None,
    observed_at: str | None = None,
) -> Path:
    return run_dir(
        workspaces_home,
        repo_fingerprint,
        run_id,
        repo_slug=repo_slug,
        observed_at=observed_at,
    ) / "metadata.json"


def run_manifest_path(
    workspaces_home: Path,
    repo_fingerprint: str,
    run_id: str,
    *,
    repo_slug: str | None = None,
    observed_at: str | None = None,
) -> Path:
    return run_dir(
        workspaces_home,
        repo_fingerprint,
        run_id,
        repo_slug=repo_slug,
        observed_at=observed_at,
    ) / "run-manifest.json"


def run_checksums_path(
    workspaces_home: Path,
    repo_fingerprint: str,
    run_id: str,
    *,
    repo_slug: str | None = None,
    observed_at: str | None = None,
) -> Path:
    return run_dir(
        workspaces_home,
        repo_fingerprint,
        run_id,
        repo_slug=repo_slug,
        observed_at=observed_at,
    ) / "checksums.json"


def run_provenance_path(
    workspaces_home: Path,
    repo_fingerprint: str,
    run_id: str,
    *,
    repo_slug: str | None = None,
    observed_at: str | None = None,
) -> Path:
    return run_dir(
        workspaces_home,
        repo_fingerprint,
        run_id,
        repo_slug=repo_slug,
        observed_at=observed_at,
    ) / "provenance-record.json"


def run_pr_record_path(
    workspaces_home: Path,
    repo_fingerprint: str,
    run_id: str,
    *,
    repo_slug: str | None = None,
    observed_at: str | None = None,
) -> Path:
    return run_dir(
        workspaces_home,
        repo_fingerprint,
        run_id,
        repo_slug=repo_slug,
        observed_at=observed_at,
    ) / "pr-record.json"


def run_ticket_record_path(
    workspaces_home: Path,
    repo_fingerprint: str,
    run_id: str,
    *,
    repo_slug: str | None = None,
    observed_at: str | None = None,
) -> Path:
    return run_dir(
        workspaces_home,
        repo_fingerprint,
        run_id,
        repo_slug=repo_slug,
        observed_at=observed_at,
    ) / "ticket-record.json"


def run_review_decision_record_path(
    workspaces_home: Path,
    repo_fingerprint: str,
    run_id: str,
    *,
    repo_slug: str | None = None,
    observed_at: str | None = None,
) -> Path:
    return run_dir(
        workspaces_home,
        repo_fingerprint,
        run_id,
        repo_slug=repo_slug,
        observed_at=observed_at,
    ) / "review-decision-record.json"


def run_outcome_record_path(
    workspaces_home: Path,
    repo_fingerprint: str,
    run_id: str,
    *,
    repo_slug: str | None = None,
    observed_at: str | None = None,
) -> Path:
    return run_dir(
        workspaces_home,
        repo_fingerprint,
        run_id,
        repo_slug=repo_slug,
        observed_at=observed_at,
    ) / "outcome-record.json"


def run_evidence_index_path(
    workspaces_home: Path,
    repo_fingerprint: str,
    run_id: str,
    *,
    repo_slug: str | None = None,
    observed_at: str | None = None,
) -> Path:
    return run_dir(
        workspaces_home,
        repo_fingerprint,
        run_id,
        repo_slug=repo_slug,
        observed_at=observed_at,
    ) / "evidence-index.json"


def run_finalization_record_path(
    workspaces_home: Path,
    repo_fingerprint: str,
    run_id: str,
    *,
    repo_slug: str | None = None,
    observed_at: str | None = None,
) -> Path:
    return run_dir(
        workspaces_home,
        repo_fingerprint,
        run_id,
        repo_slug=repo_slug,
        observed_at=observed_at,
    ) / "finalization-record.json"


def repository_manifest_path(workspaces_home: Path, repo_fingerprint: str) -> Path:
    return runs_dir(workspaces_home, repo_fingerprint) / "repository-manifest.json"


def current_run_path(workspaces_home: Path, repo_fingerprint: str) -> Path:
    return workspace_root(workspaces_home, repo_fingerprint) / "current_run.json"


PHASE2_ARTIFACTS = ["repo-cache.yaml", "repo-map-digest.md", "workspace-memory.yaml"]
PHASE21_ARTIFACTS = ["decision-pack.md"]
PHASE15_ARTIFACTS = ["business-rules.md", "business-rules-status.md"]
PHASE4_ARTIFACTS = ["plan-record.json"]


def all_phase_artifact_paths(workspaces_home: Path, repo_fingerprint: str) -> dict[str, Path]:
    return {
        "session_state": session_state_path(workspaces_home, repo_fingerprint),
        "repo_cache": repo_cache_path(workspaces_home, repo_fingerprint),
        "repo_map_digest": repo_map_digest_path(workspaces_home, repo_fingerprint),
        "workspace_memory": workspace_memory_path(workspaces_home, repo_fingerprint),
        "decision_pack": decision_pack_path(workspaces_home, repo_fingerprint),
        "business_rules": business_rules_path(workspaces_home, repo_fingerprint),
        "business_rules_status": business_rules_status_path(workspaces_home, repo_fingerprint),
        "plan_record": plan_record_path(workspaces_home, repo_fingerprint),
    }


def phase2_artifact_paths(workspaces_home: Path, repo_fingerprint: str) -> dict[str, Path]:
    return {
        "repo_cache": repo_cache_path(workspaces_home, repo_fingerprint),
        "repo_map_digest": repo_map_digest_path(workspaces_home, repo_fingerprint),
        "workspace_memory": workspace_memory_path(workspaces_home, repo_fingerprint),
    }


def governance_plan_dir(workspaces_home: Path, repo_fingerprint: str | None = None) -> Path:
    """Return canonical governance plan artifacts directory.

    When ``repo_fingerprint`` is provided, returns a workspace-scoped path.
    Otherwise, preserves legacy behavior under ``workspaces_home``.
    """
    if repo_fingerprint:
        return workspace_root(workspaces_home, repo_fingerprint) / "plan"
    return workspaces_home / "plan"


def governance_review_dir(workspaces_home: Path, repo_fingerprint: str | None = None) -> Path:
    """Return canonical governance review artifacts directory.

    When ``repo_fingerprint`` is provided, returns a workspace-scoped path.
    Otherwise, preserves legacy behavior under ``workspaces_home``.
    """
    if repo_fingerprint:
        return workspace_root(workspaces_home, repo_fingerprint) / "review"
    return workspaces_home / "review"


def governance_runtime_state_dir(workspaces_home: Path, repo_fingerprint: str | None = None) -> Path:
    """Return canonical governance runtime state directory.

    When ``repo_fingerprint`` is provided, returns a workspace-scoped path.
    Otherwise, preserves legacy behavior under ``workspaces_home``.
    """
    if repo_fingerprint:
        return workspace_root(workspaces_home, repo_fingerprint) / "runtime_state"
    return workspaces_home / "runtime_state"


def governance_implementation_dir(workspaces_home: Path, repo_fingerprint: str | None = None) -> Path:
    """Return canonical governance implementation artifacts directory.

    When ``repo_fingerprint`` is provided, returns a workspace-scoped path.
    Otherwise, preserves legacy behavior under ``workspaces_home``.
    """
    if repo_fingerprint:
        return workspace_root(workspaces_home, repo_fingerprint) / "implementation"
    return workspaces_home / "implementation"


def governance_allowed_artifact_dirs(workspaces_home: Path, repo_fingerprint: str | None = None) -> tuple[Path, ...]:
    """Return allowed governance directories for materialized artifacts."""
    root = workspace_root(workspaces_home, repo_fingerprint) if repo_fingerprint else workspaces_home
    return (
        root,
        governance_runtime_state_dir(workspaces_home, repo_fingerprint),
        governance_plan_dir(workspaces_home, repo_fingerprint),
        governance_review_dir(workspaces_home, repo_fingerprint),
        governance_implementation_dir(workspaces_home, repo_fingerprint),
    )
