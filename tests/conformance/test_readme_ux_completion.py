from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


def _read(path: Path) -> str:
    assert path.exists(), f"Missing file: {path.relative_to(REPO_ROOT)}"
    return path.read_text(encoding="utf-8")


@pytest.mark.conformance
class TestReadmeUxCompletion:
    def test_governance_content_docs_are_not_shims(self) -> None:
        for rel in [
            "governance_content/README.md",
            "governance_content/README-OPENCODE.md",
            "governance_content/QUICKSTART.md",
        ]:
            content = _read(REPO_ROOT / rel)
            assert "shim" not in content.lower(), f"{rel} must be a completed UX doc, not a shim"
            assert len(content.splitlines()) >= 30, f"{rel} must contain substantive content"

    def test_readme_surfaces_include_canonical_rail_progression(self) -> None:
        readme = _read(REPO_ROOT / "governance_content" / "README.md")
        assert "/continue" in readme
        assert "/review" in readme
        assert "read-only rail entrypoint" in readme
        assert "/review-decision" in readme
        assert "/implement" in readme

    def test_opencode_readme_covers_launcher_and_gates(self) -> None:
        opencode = _read(REPO_ROOT / "governance_content" / "README-OPENCODE.md")
        assert "opencode-governance-bootstrap" in opencode
        assert "/continue" in opencode
        assert "/review" in opencode
        assert "read-only rail entrypoint" in opencode
        assert "/review-decision" in opencode

    def test_quickstart_covers_end_to_end_operator_flow(self) -> None:
        quickstart = _read(REPO_ROOT / "governance_content" / "QUICKSTART.md")
        assert "Step 1: Install" in quickstart
        assert "opencode-governance-bootstrap" in quickstart
        assert "/continue" in quickstart
        assert "/review" in quickstart
        assert "read-only rail entrypoint" in quickstart
        assert "/review-decision" in quickstart
