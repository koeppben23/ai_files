from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
LOG_PATH = REPO_ROOT / "governance_spec" / "migrations" / "CLEANUP_DECISION_LOG.md"


@pytest.mark.conformance
def test_cleanup_decision_log_exists() -> None:
    assert LOG_PATH.exists(), "cleanup decision log must exist"


@pytest.mark.conformance
def test_cleanup_decision_log_covers_patch1_candidates() -> None:
    content = LOG_PATH.read_text(encoding="utf-8")
    required = [
        "governance_content/docs/backlog/guidance-language-cleanup.md",
        "governance_spec/migrations/F100_Frozen_Compatibility_Surface.txt",
    ]
    missing = [item for item in required if item not in content]
    assert not missing, f"cleanup decision log missing required candidate entries: {missing}"


@pytest.mark.conformance
def test_cleanup_decision_log_matches_path_reality() -> None:
    must_not_exist = [
        REPO_ROOT / "historical",
        REPO_ROOT / "governance_content" / "docs" / "archived",
        REPO_ROOT / "governance_spec" / "migrations" / "archived",
        REPO_ROOT / "governance_content" / "docs" / "backlog" / "guidance-language-cleanup.md",
        REPO_ROOT / "governance_spec" / "migrations" / "F100_Frozen_Compatibility_Surface.txt",
    ]

    unexpected = [p.relative_to(REPO_ROOT).as_posix() for p in must_not_exist if p.exists()]
    assert not unexpected, f"patch 1 cleanup targets still exist: {unexpected}"
