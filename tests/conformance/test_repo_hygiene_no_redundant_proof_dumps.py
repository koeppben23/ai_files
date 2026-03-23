from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = REPO_ROOT / "governance_spec" / "migrations"
ARCHIVED = MIGRATIONS / "archived"


@pytest.mark.conformance
def test_redundant_frozen_surface_raw_dump_removed() -> None:
    redundant = MIGRATIONS / "F100_Frozen_Compatibility_Surface.txt"
    assert not redundant.exists(), "redundant raw frozen-surface dump must not exist"


@pytest.mark.conformance
def test_historical_r2_records_removed_by_patch1() -> None:
    """Patch 1 deleted archived directories including R2 records."""
    active_r2 = [
        MIGRATIONS / "R2_Migration_Units.md",
        MIGRATIONS / "R2_Import_Inventory.md",
    ]
    for path in active_r2:
        assert not path.exists(), f"historical migration record must not exist: {path.name}"

    assert not ARCHIVED.exists(), "archived directory should not exist after patch 1"


@pytest.mark.conformance
def test_cleanup_policy_exists_and_declares_classification() -> None:
    policy = MIGRATIONS / "REPO_CLEANUP_POLICY.md"
    assert policy.exists(), "cleanup policy must exist"
    content = policy.read_text(encoding="utf-8")
    for token in ["## Classification Rules", "### Keep", "### Archive", "### Delete"]:
        assert token in content, f"cleanup policy missing section: {token}"
