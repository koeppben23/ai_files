from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.conformance
def test_no_unclassified_backlog_markdown_docs() -> None:
    backlog_dir = REPO_ROOT / "governance_content" / "docs" / "backlog"
    if not backlog_dir.exists():
        return
    md_files = sorted(p.relative_to(REPO_ROOT).as_posix() for p in backlog_dir.rglob("*.md"))
    assert not md_files, (
        "backlog markdown docs must be deleted or archived out of active docs: "
        f"{md_files}"
    )
