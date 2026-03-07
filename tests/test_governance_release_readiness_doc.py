from __future__ import annotations

from pathlib import Path

import pytest

from .util import REPO_ROOT


@pytest.mark.governance
def test_governance_release_readiness_doc_contains_required_matrices() -> None:
    path = REPO_ROOT / "docs" / "governance-release-readiness.md"
    assert path.exists(), "docs/governance-release-readiness.md must exist"
    text = path.read_text(encoding="utf-8")

    required_headers = [
        "## Coverage Matrix (B1-B14 / C1-C4)",
        "## Cross-OS Compatibility Matrix",
        "## Model Identity Matrix (Opus/Codex)",
        "## Test Matrix (E1-E6 + Extensions)",
        "## Release Checklist",
    ]
    for header in required_headers:
        assert header in text, f"missing required section: {header}"


@pytest.mark.governance
def test_governance_release_readiness_doc_mentions_plan_rail_contract() -> None:
    path = REPO_ROOT / "docs" / "governance-release-readiness.md"
    text = path.read_text(encoding="utf-8")
    assert "/plan" in text
    assert "Free-text" in text
