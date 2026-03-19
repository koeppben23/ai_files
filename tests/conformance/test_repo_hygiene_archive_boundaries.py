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
    assert not offenders, f"historical migration records must be archived: {offenders}"


@pytest.mark.conformance
def test_archived_migration_records_exist_for_r2_and_wave_history() -> None:
    required = [
        MIGRATIONS_ARCHIVED / "R2_Import_Inventory.md",
        MIGRATIONS_ARCHIVED / "R2_Migration_Units.md",
        MIGRATIONS_ARCHIVED / "WAVE_22_MIGRATION_INVENTORY.md",
        MIGRATIONS_ARCHIVED / "README.md",
    ]
    missing = [p.relative_to(REPO_ROOT).as_posix() for p in required if not p.exists()]
    assert not missing, f"missing archived migration records: {missing}"


@pytest.mark.conformance
def test_historical_governance_docs_are_archived_not_active() -> None:
    historical_doc_name = "governance-layer-separation-decisions.md"
    active_path = DOCS / historical_doc_name
    archived_path = DOCS_ARCHIVED / historical_doc_name

    assert not active_path.exists(), (
        f"historical governance decision doc must not remain active: {active_path.relative_to(REPO_ROOT)}"
    )
    assert archived_path.exists(), (
        f"historical governance decision doc missing from archive: {archived_path.relative_to(REPO_ROOT)}"
    )


@pytest.mark.conformance
def test_archived_docs_directory_has_readme() -> None:
    readme = DOCS_ARCHIVED / "README.md"
    assert readme.exists(), "archived governance docs directory must include README.md"
