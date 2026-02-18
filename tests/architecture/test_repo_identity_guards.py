from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.governance
def test_repo_root_resolution_is_git_evidence_only():
    resolver = REPO_ROOT / "governance" / "context" / "repo_context_resolver.py"
    text = resolver.read_text(encoding="utf-8")

    required = [
        "rev-parse",
        "--show-toplevel",
        "repo_root=None",
    ]
    missing = [token for token in required if token not in text]
    assert not missing, f"repo resolver missing required git-evidence tokens: {missing}"

    forbidden = [
        "cwd-parent-search",
        "parent search",
        "parent-walk",
        "repo_root=cwd",
        "repo_root = cwd",
    ]
    hits = [token for token in forbidden if token in text]
    assert not hits, f"repo resolver contains forbidden fallback heuristics: {hits}"


@pytest.mark.governance
def test_start_persistence_unresolved_requires_null_repo_root():
    path = REPO_ROOT / "governance" / "application" / "use_cases" / "start_persistence.py"
    text = path.read_text(encoding="utf-8")

    assert "reason=\"identity-bootstrap-fingerprint-missing\"" in text or "identity-bootstrap-fingerprint-missing" in text
    assert "repo_root=None" in text
