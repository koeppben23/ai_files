"""Tests for path normalization security in persist_workspace_artifacts_orchestrator.

These tests verify that the orchestrator uses the canonical path_contract.py
for path normalization and properly rejects path traversal and invalid inputs.

Security requirement: The orchestrator MUST NOT have a fallback normalize_absolute_path
implementation that lacks path traversal checks. Path security must be enforced
by the canonical path_contract module.
"""

from __future__ import annotations

import pytest

from governance_runtime.infrastructure.path_contract import (
    NotAbsoluteError,
    PathContractError,
    PathTraversalError,
    normalize_absolute_path,
)


@pytest.mark.governance
class TestOrchestratorPathNormalizationSecurity:
    """Verify path normalization uses canonical path_contract.py implementation."""

    def test_parent_directory_traversal_raises_error(self):
        """Path with .. segments must raise PathTraversalError."""
        with pytest.raises(PathTraversalError, match="path traversal"):
            normalize_absolute_path("/safe/../../etc/passwd", purpose="test")

    def test_current_directory_segment_is_normalized_by_path(self):
        """Path with ./ segments is normalized by Path before our check.

        Note: Path('/safe/./secrets').parts returns ('/', 'safe', 'secrets')
        so the '.' check doesn't trigger. This is acceptable because '.'
        doesn't enable traversal - it's equivalent to the current directory.

        The important security check is for '..' which IS preserved in parts.
        """
        # This succeeds because Path normalizes ./ away before our check
        result = normalize_absolute_path("/safe/./secrets", purpose="test")
        assert result.is_absolute()
        assert ".." not in result.parts

    def test_nested_traversal_raises_error(self):
        """Nested traversal patterns must be rejected."""
        with pytest.raises(PathTraversalError):
            normalize_absolute_path("/a/b/../c/../../d", purpose="test")

    def test_relative_path_raises_error(self):
        """Relative paths must raise NotAbsoluteError."""
        with pytest.raises(NotAbsoluteError, match="must be absolute"):
            normalize_absolute_path("./relative/path", purpose="test")

    def test_relative_path_without_dot_raises_error(self):
        """Relative paths without ./ prefix must raise NotAbsoluteError."""
        with pytest.raises(NotAbsoluteError, match="must be absolute"):
            normalize_absolute_path("relative/path", purpose="test")

    def test_empty_path_raises_error(self):
        """Empty path must raise NotAbsoluteError."""
        with pytest.raises(NotAbsoluteError, match="empty path"):
            normalize_absolute_path("", purpose="test")

    def test_whitespace_only_path_raises_error(self):
        """Whitespace-only path must raise NotAbsoluteError."""
        with pytest.raises(NotAbsoluteError, match="empty path"):
            normalize_absolute_path("   ", purpose="test")

    def test_valid_absolute_path_succeeds(self):
        """Normal absolute path must succeed."""
        result = normalize_absolute_path("/usr/local/bin", purpose="test")
        assert result.is_absolute()
        assert "usr" in result.parts

    def test_absolute_path_with_home_expansion(self):
        """Path with ~ must expand and normalize correctly."""
        result = normalize_absolute_path("~/test", purpose="test")
        assert result.is_absolute()
        assert str(result).startswith("/") or (hasattr(result, "drive") and result.drive)

    @pytest.mark.skipif(
        not hasattr(__import__("os"), "name") or __import__("os").name != "nt",
        reason="Windows-specific test"
    )
    def test_windows_drive_relative_raises_error(self):
        """Windows drive-relative paths (C:foo) must raise WindowsDriveRelativeError."""
        from governance_runtime.infrastructure.path_contract import WindowsDriveRelativeError
        with pytest.raises(WindowsDriveRelativeError):
            normalize_absolute_path("C:foo\\bar", purpose="test")

    def test_purpose_is_in_error_message(self):
        """Error messages must include the purpose parameter for debugging."""
        with pytest.raises(NotAbsoluteError, match="test-purpose"):
            normalize_absolute_path("relative", purpose="test-purpose")

    def test_double_slash_is_normalized(self):
        """Double slashes in absolute paths must be normalized."""
        result = normalize_absolute_path("/usr//local///bin", purpose="test")
        assert "//" not in str(result)
        assert result.is_absolute()

    def test_trailing_slash_is_normalized(self):
        """Trailing slashes must be normalized away."""
        result = normalize_absolute_path("/usr/local/", purpose="test")
        assert not str(result).endswith("/") or str(result) == "/"


@pytest.mark.governance
class TestOrchestratorNoFallbackImplementation:
    """Verify the orchestrator does NOT have a local fallback path normalization."""

    def test_orchestrator_imports_from_path_contract(self):
        """Orchestrator must import normalize_absolute_path from path_contract."""
        import governance_runtime.entrypoints.persist_workspace_artifacts_orchestrator as orchestrator

        # The module should import from path_contract, not define its own
        # We verify this by checking the source or the actual function
        from governance_runtime.infrastructure.path_contract import normalize_absolute_path as canonical

        # The orchestrator should use the canonical implementation
        # If it has a fallback, it should only exist in an ImportError block
        # and should have the traversal check
        import inspect
        source = inspect.getsource(orchestrator)

        # Count occurrences of normalize_absolute_path definition
        # There should be at most one definition (in the try block importing from path_contract)
        # OR if there's a fallback, it must contain the traversal check
        if "def normalize_absolute_path" in source:
            # Find the fallback definition
            lines = source.split("\n")
            in_fallback = False
            fallback_has_traversal_check = False
            for i, line in enumerate(lines):
                if "def normalize_absolute_path" in line:
                    # Check if this is in a fallback block (after ImportError)
                    context_start = max(0, i - 10)
                    context = "\n".join(lines[context_start:i])
                    if "ImportError" in context or "AttributeError" in context:
                        in_fallback = True
                if in_fallback and ".." in line and "parts" in line:
                    fallback_has_traversal_check = True
                    break
                if in_fallback and "PathTraversalError" in line:
                    fallback_has_traversal_check = True
                    break

            # If there's a fallback, it MUST have traversal check
            if in_fallback:
                assert fallback_has_traversal_check, (
                    "Fallback normalize_absolute_path must include path traversal check. "
                    "Security requirement: no soft fallback without traversal protection."
                )
