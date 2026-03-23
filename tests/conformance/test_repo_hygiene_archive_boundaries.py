from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = REPO_ROOT / "governance_spec" / "migrations"
MIGRATIONS_ARCHIVED = MIGRATIONS / "archived"
DOCS = REPO_ROOT / "governance_content" / "docs"
DOCS_ARCHIVED = DOCS / "archived"


@pytest.mark.conformance
def test_active_migrations_are_constrained_to_final_state_records() -> None:
    active = sorted(p.name for p in MIGRATIONS.glob("*.md"))
    allowed = sorted(
        [
            "F100_Completion_Gate.md",
            "CLEANUP_DECISION_LOG.md",
            "F100_Final_Snapshot_Signoff.md",
            "PR7_README_UX_Completion.md",
            "R4a_Legacy_Sunset_Readiness.md",
            "R4b_Legacy_Sunset_Delete_Preparation.md",
            "R5_R10_Hardening_and_Readiness.md",
            "R10_Final_State_Proof.md",
            "REPO_CLEANUP_POLICY.md",
        ]
    )
    assert active == allowed, (
        "active migrations drifted from final-state record set: "
        f"active={active} allowed={allowed}"
    )


@pytest.mark.conformance
def test_historical_wave_and_r2_records_not_in_active_migrations() -> None:
    offenders: list[str] = []
    for path in MIGRATIONS.glob("*.md"):
        name = path.name.lower()
        if name.startswith("r2_") or "wave" in name:
            offenders.append(path.relative_to(REPO_ROOT).as_posix())
    assert not offenders, f"historical migration records must be archived or removed: {offenders}"


@pytest.mark.conformance
def test_archived_directories_removed_by_patch1() -> None:
    """Patch 1 deleted all archived directories."""
    archived_dirs = [
        MIGRATIONS_ARCHIVED,
        DOCS_ARCHIVED,
        REPO_ROOT / "historical",
    ]
    unexpected = [p.relative_to(REPO_ROOT).as_posix() for p in archived_dirs if p.exists()]
    assert not unexpected, f"archived directories should not exist after patch 1: {unexpected}"


@pytest.mark.conformance
def test_no_unclassified_historical_named_docs_in_active_paths() -> None:
    historical_markers = ("wave", "rollup", "inventory", "decision", "backlog")
    active_allowlist = {"CLEANUP_DECISION_LOG.md"}
    offenders: list[str] = []

    for path in MIGRATIONS.glob("*.md"):
        lowered = path.name.lower()
        if path.name in active_allowlist:
            continue
        if any(marker in lowered for marker in historical_markers):
            offenders.append(path.relative_to(REPO_ROOT).as_posix())

    for path in DOCS.glob("*.md"):
        lowered = path.name.lower()
        if any(marker in lowered for marker in historical_markers):
            offenders.append(path.relative_to(REPO_ROOT).as_posix())

    assert not offenders, (
        "historical-named docs must be archived or explicitly reclassified before staying active: "
        f"{offenders}"
    )
