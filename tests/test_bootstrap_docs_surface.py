from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.governance
@pytest.mark.parametrize(
    "doc_path",
    [
        "README.md",
        "QUICKSTART.md",
        "README-OPENCODE.md",
        "BOOTSTRAP.md",
    ],
)
def test_bootstrap_docs_include_canonical_init_profile_surface(doc_path: str) -> None:
    text = (REPO_ROOT / doc_path).read_text(encoding="utf-8")
    assert "init --profile" in text, f"missing canonical init/profile surface in {doc_path}"


@pytest.mark.governance
def test_bootstrap_docs_explain_alias_as_secondary_surface() -> None:
    text = (REPO_ROOT / "BOOTSTRAP.md").read_text(encoding="utf-8")
    assert "--set-operating-mode" in text
    assert "optional" in text.lower()
