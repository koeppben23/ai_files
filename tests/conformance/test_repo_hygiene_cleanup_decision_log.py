from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
LOG_PATH = REPO_ROOT / "governance_spec" / "migrations" / "CLEANUP_DECISION_LOG.md"


@pytest.mark.conformance
def test_cleanup_decision_log_exists() -> None:
    assert LOG_PATH.exists(), "cleanup decision log must exist"


@pytest.mark.conformance
def test_cleanup_decision_log_covers_required_candidates() -> None:
    content = LOG_PATH.read_text(encoding="utf-8")
    required = [
        "governance_content/docs/archived/governance-layer-separation-decisions.md",
        "governance_spec/migrations/archived/R2_Migration_Units.md",
        "governance_spec/migrations/archived/R2_Import_Inventory.md",
        "governance_spec/migrations/archived/WAVE_22_MIGRATION_INVENTORY.md",
        "governance_content/docs/backlog/guidance-language-cleanup.md",
        "governance_spec/migrations/F100_Frozen_Compatibility_Surface.txt",
    ]
    missing = [item for item in required if item not in content]
    assert not missing, f"cleanup decision log missing required candidate entries: {missing}"


@pytest.mark.conformance
def test_cleanup_decision_log_matches_path_reality() -> None:
    must_exist = [
        REPO_ROOT / "governance_content" / "docs" / "archived" / "governance-layer-separation-decisions.md",
        REPO_ROOT / "governance_spec" / "migrations" / "archived" / "R2_Migration_Units.md",
        REPO_ROOT / "governance_spec" / "migrations" / "archived" / "R2_Import_Inventory.md",
        REPO_ROOT / "governance_spec" / "migrations" / "archived" / "WAVE_22_MIGRATION_INVENTORY.md",
    ]
    must_not_exist = [
        REPO_ROOT / "governance_content" / "docs" / "backlog" / "guidance-language-cleanup.md",
        REPO_ROOT / "governance_spec" / "migrations" / "F100_Frozen_Compatibility_Surface.txt",
    ]

    missing = [p.relative_to(REPO_ROOT).as_posix() for p in must_exist if not p.exists()]
    assert not missing, f"archived paths missing from filesystem: {missing}"

    unexpected = [p.relative_to(REPO_ROOT).as_posix() for p in must_not_exist if p.exists()]
    assert not unexpected, f"deleted cleanup targets still exist: {unexpected}"
