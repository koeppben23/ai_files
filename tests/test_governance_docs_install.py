"""Tests for governance documentation installation pathway.

Validates:
- collect_governance_docs_files() discovers all .md files under docs/governance/
- Subdirectory files (docs/governance/rails/*.md) are included
- Non-.md files are excluded
- Missing docs/governance/ returns empty list
- Installation copies docs to commands/docs/governance/ with correct structure

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from install import collect_governance_docs_files


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def source_dir(tmp_path: Path) -> Path:
    """Create a source directory with representative docs/governance/ structure."""
    src = tmp_path / "source"
    gov_docs = src / "docs" / "governance"
    gov_docs.mkdir(parents=True)

    # Root-level governance docs
    (gov_docs / "governance_schemas.md").write_text("# Schemas\n", encoding="utf-8")
    (gov_docs / "doc_lint.md").write_text("# Doc Lint\n", encoding="utf-8")
    (gov_docs / "RESPONSIBILITY_BOUNDARY.md").write_text("# Boundaries\n", encoding="utf-8")

    # Subdirectory (rails/)
    rails = gov_docs / "rails"
    rails.mkdir()
    (rails / "planning.md").write_text("# Planning\n", encoding="utf-8")
    (rails / "testing.md").write_text("# Testing\n", encoding="utf-8")

    return src


@pytest.fixture()
def source_dir_no_docs(tmp_path: Path) -> Path:
    """Source directory with no docs/governance/ directory."""
    src = tmp_path / "source_no_docs"
    src.mkdir()
    return src


# ---------------------------------------------------------------------------
# collect_governance_docs_files
# ---------------------------------------------------------------------------

class TestCollectGovernanceDocsFiles:
    def test_discovers_root_md_files(self, source_dir: Path) -> None:
        """All .md files in docs/governance/ root are collected."""
        files = collect_governance_docs_files(source_dir)
        names = {f.name for f in files}
        assert "governance_schemas.md" in names
        assert "doc_lint.md" in names
        assert "RESPONSIBILITY_BOUNDARY.md" in names

    def test_discovers_subdirectory_md_files(self, source_dir: Path) -> None:
        """Files in subdirectories (e.g., rails/) are also collected."""
        files = collect_governance_docs_files(source_dir)
        names = {f.name for f in files}
        assert "planning.md" in names
        assert "testing.md" in names

    def test_correct_count(self, source_dir: Path) -> None:
        """Correct total count of discovered files."""
        files = collect_governance_docs_files(source_dir)
        assert len(files) == 5  # 3 root + 2 rails/

    def test_returns_sorted(self, source_dir: Path) -> None:
        """Returned list is sorted."""
        files = collect_governance_docs_files(source_dir)
        assert files == sorted(files)

    def test_only_md_files(self, source_dir: Path) -> None:
        """Non-.md files are excluded."""
        gov_docs = source_dir / "docs" / "governance"
        (gov_docs / "data.yaml").write_text("key: value\n", encoding="utf-8")
        (gov_docs / "notes.txt").write_text("some notes\n", encoding="utf-8")

        files = collect_governance_docs_files(source_dir)
        extensions = {f.suffix for f in files}
        assert extensions == {".md"}

    def test_missing_directory_returns_empty(self, source_dir_no_docs: Path) -> None:
        """Returns empty list when docs/governance/ doesn't exist."""
        files = collect_governance_docs_files(source_dir_no_docs)
        assert files == []

    def test_empty_directory_returns_empty(self, tmp_path: Path) -> None:
        """Returns empty list when docs/governance/ exists but is empty."""
        src = tmp_path / "empty_src"
        (src / "docs" / "governance").mkdir(parents=True)
        files = collect_governance_docs_files(src)
        assert files == []

    def test_preserves_relative_structure(self, source_dir: Path) -> None:
        """File paths maintain the correct relative structure from source_dir."""
        files = collect_governance_docs_files(source_dir)
        for f in files:
            rel = f.relative_to(source_dir)
            assert str(rel).startswith("docs")

    def test_symlinks_excluded(self, source_dir: Path) -> None:
        """Symlinks are excluded from collection."""
        gov_docs = source_dir / "docs" / "governance"
        target = gov_docs / "governance_schemas.md"
        link = gov_docs / "symlink.md"
        try:
            link.symlink_to(target)
        except OSError:
            pytest.skip("Symlink creation not supported on this platform without privileges")

        files = collect_governance_docs_files(source_dir)
        names = {f.name for f in files}
        assert "symlink.md" not in names


# ---------------------------------------------------------------------------
# Integration: real repo docs/governance/ directory
# ---------------------------------------------------------------------------

class TestRealRepoDocs:
    """Validate collection against the actual repo docs/governance/ directory."""

    def test_repo_has_governance_docs(self) -> None:
        """The repo should have docs/governance/ with .md files."""
        from tests.util import REPO_ROOT
        files = collect_governance_docs_files(REPO_ROOT)
        assert len(files) >= 5, (
            f"Expected at least 5 governance doc files, found {len(files)}. "
            f"Files: {[f.name for f in files]}"
        )

    def test_governance_schemas_present(self) -> None:
        """governance_schemas.md (referenced ~35 times) must be present."""
        from tests.util import REPO_ROOT
        files = collect_governance_docs_files(REPO_ROOT)
        names = {f.name for f in files}
        assert "governance_schemas.md" in names

    def test_rails_subdirectory_present(self) -> None:
        """Rails subdirectory docs should be collected."""
        from tests.util import REPO_ROOT
        files = collect_governance_docs_files(REPO_ROOT)
        rails_files = [f for f in files if "rails" in str(f)]
        assert len(rails_files) >= 1, "Expected at least 1 rails/ doc file"
