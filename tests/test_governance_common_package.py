"""Tests for governance.common package integrity and path_normalization utilities.

Coverage: Happy, Bad, Corner, Edge cases for:
- Fix 1: governance/common/__init__.py existence (package importability)
- path_normalization.normalize_for_fingerprint correctness
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Fix 1 -- governance.common package importability
# ---------------------------------------------------------------------------


class TestGovernanceCommonPackageImport:
    """Verify governance.common is a proper Python package."""

    def test_happy_import_governance_common(self) -> None:
        """The governance.common package itself can be imported."""
        mod = importlib.import_module("governance.common")
        assert mod is not None

    def test_happy_import_path_normalization_from_common(self) -> None:
        """The path_normalization module can be imported via the package path."""
        from governance_runtime.common.path_normalization import normalize_for_fingerprint

        assert callable(normalize_for_fingerprint)

    def test_bad_import_nonexistent_module_raises(self) -> None:
        """Importing a module that does not exist under governance.common raises ImportError."""
        with pytest.raises(ImportError):
            importlib.import_module("governance.common.nonexistent_module_xyz")

    def test_corner_reimport_is_idempotent(self) -> None:
        """Reimporting governance.common returns the same cached module object."""
        mod1 = importlib.import_module("governance.common")
        mod2 = importlib.import_module("governance.common")
        assert mod1 is mod2

    def test_edge_init_file_exists_on_disk(self) -> None:
        """The __init__.py file physically exists on disk."""
        import governance_runtime.common as gc

        init_path = Path(gc.__file__)
        assert init_path.exists()
        assert init_path.name == "__init__.py"


# ---------------------------------------------------------------------------
# path_normalization -- normalize_for_fingerprint
# ---------------------------------------------------------------------------


class TestNormalizeForFingerprint:
    """Verify normalize_for_fingerprint across platforms and edge cases."""

    def test_happy_simple_path_normalized(self, tmp_path: Path) -> None:
        """A simple path returns a forward-slash normalized absolute string."""
        from governance_runtime.common.path_normalization import normalize_for_fingerprint

        result = normalize_for_fingerprint(tmp_path / "my_repo")
        assert "/" in result or "\\" not in result  # forward slashes on all platforms
        assert "my_repo" in result

    def test_happy_backslash_converted(self, tmp_path: Path) -> None:
        """Backslashes are converted to forward slashes."""
        from governance_runtime.common.path_normalization import normalize_for_fingerprint

        result = normalize_for_fingerprint(tmp_path / "a" / "b" / "c")
        assert "\\" not in result

    def test_bad_relative_path_resolved_to_absolute(self) -> None:
        """Even a relative path is resolved to an absolute path."""
        from governance_runtime.common.path_normalization import normalize_for_fingerprint

        result = normalize_for_fingerprint(Path("some/relative/path"))
        assert os.path.isabs(result.replace("/", os.sep))

    def test_corner_dot_dot_components_collapsed(self, tmp_path: Path) -> None:
        """Parent directory references (..) are collapsed."""
        from governance_runtime.common.path_normalization import normalize_for_fingerprint

        result = normalize_for_fingerprint(tmp_path / "a" / "b" / ".." / "c")
        assert ".." not in result
        assert result.endswith("a/c")

    def test_edge_windows_case_folding(self, tmp_path: Path) -> None:
        """On Windows, paths are case-folded; on other OS they are not."""
        from governance_runtime.common.path_normalization import normalize_for_fingerprint

        mixed = tmp_path / "MyRepo"
        result = normalize_for_fingerprint(mixed)
        if os.name == "nt":
            assert result == result.casefold()
        else:
            assert "MyRepo" in result

    def test_edge_tilde_expansion(self) -> None:
        """Tilde (~) in path is expanded to the user home directory."""
        from governance_runtime.common.path_normalization import normalize_for_fingerprint

        result = normalize_for_fingerprint(Path("~/some_project"))
        assert "~" not in result
        assert "some_project" in result
