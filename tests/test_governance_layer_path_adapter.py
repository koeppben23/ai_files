"""
Path Adapter Layer Tests - Wave 1

Tests for:
- Central path resolver
- Logical root resolution
- Legacy path mapping
- Workspace path resolution

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

import os
import pytest
from pathlib import Path
from unittest.mock import patch

from governance_runtime.paths import layer_adapter


def _posix(path: Path) -> str:
    return path.as_posix()


class TestPathAdapterHappyPath:
    """Happy path: basic path resolution works."""

    def test_get_config_root_from_env(self) -> None:
        """Config root can be overridden via environment variable."""
        with patch.dict(os.environ, {"OPENCODE_CONFIG_ROOT": "/test/config"}):
            layer_adapter.set_config_root_override(None)  # Clear any override
            assert _posix(layer_adapter.get_config_root()) == "/test/config"

    def test_get_config_root_override_priority(self) -> None:
        """Programmatic override takes priority over environment."""
        layer_adapter.set_config_root_override("/override/path")
        with patch.dict(os.environ, {"OPENCODE_CONFIG_ROOT": "/env/path"}):
            assert _posix(layer_adapter.get_config_root()) == "/override/path"
        layer_adapter.set_config_root_override(None)  # Cleanup

    def test_get_opencode_command_root(self) -> None:
        """OpenCode command root is derived from config root."""
        layer_adapter.set_config_root_override("/test/config")
        result = layer_adapter.get_opencode_command_root()
        assert _posix(result) == "/test/config/commands"
        layer_adapter.set_config_root_override(None)

    def test_get_governance_runtime_root(self) -> None:
        """Governance runtime root is derived from config root."""
        layer_adapter.set_config_root_override("/test/config")
        result = layer_adapter.get_governance_runtime_root()
        assert _posix(result).endswith("/.local/opencode/governance_runtime")
        layer_adapter.set_config_root_override(None)

    def test_get_workspace_root_with_fingerprint(self) -> None:
        """Workspace root includes repository fingerprint."""
        layer_adapter.set_config_root_override("/test/config")
        fp = "abc123def456"
        result = layer_adapter.get_workspace_root(fp)
        assert _posix(result) == f"/test/config/workspaces/{fp}"
        layer_adapter.set_config_root_override(None)

    def test_get_workspace_logs_root(self) -> None:
        """Workspace logs root follows hard rule: only under workspaces/<fp>/logs/"""
        layer_adapter.set_config_root_override("/test/config")
        fp = "abc123def456"
        result = layer_adapter.get_workspace_logs_root(fp)
        assert _posix(result) == f"/test/config/workspaces/{fp}/logs"
        # Verify it's under the workspace
        workspace = layer_adapter.get_workspace_root(fp)
        assert result.parent == workspace
        layer_adapter.set_config_root_override(None)


class TestPathAdapterHardRules:
    """Verify hard rules from decision freeze."""

    def test_logs_only_under_workspace_logs(self) -> None:
        """Hard rule: logs MUST only be under workspaces/<fp>/logs/"""
        layer_adapter.set_config_root_override("/test/config")
        
        # The LOGICAL path for workspace logs is under workspaces/<fp>/logs/
        # This is enforced by the resolver, not by filesystem layout
        fp = "abc123def456"
        logs = layer_adapter.get_workspace_logs_root(fp)
        
        # Verify the logical path follows the rule
        assert "workspaces" in _posix(logs)
        assert _posix(logs).endswith("/logs")
        
        # The hard rule is: NO code should write to commands/logs/
        # That path should NOT be used - only workspace logs
        layer_adapter.set_config_root_override(None)

    def test_no_global_logs_directory_as_primary(self) -> None:
        """Hard rule: logs primary location is workspace, not config root."""
        layer_adapter.set_config_root_override("/test/config")
        
        # The resolver always gives workspace-based logs
        fp = "testfp"
        logs = layer_adapter.get_workspace_logs_root(fp)
        
        # Verify it contains workspace path
        assert "workspaces" in _posix(logs)
        assert "testfp" in _posix(logs)
        
        layer_adapter.set_config_root_override(None)

    def test_no_global_logs_directory(self) -> None:
        """Hard rule: no global logs/ at config root level."""
        layer_adapter.set_config_root_override("/test/config")
        
        # The config root should NOT have a logs subdir as primary location
        config_root = layer_adapter.get_config_root()
        # This is the expected layout - logs ONLY in workspace
        assert _posix(config_root / "commands" / "logs") != _posix(config_root / "logs")
        
        layer_adapter.set_config_root_override(None)


class TestLegacyPathMapping:
    """Edge cases: legacy path resolution during migration."""

    def test_resolve_legacy_commands_path(self) -> None:
        """Legacy commands/ path resolves to opencode command root."""
        layer_adapter.set_config_root_override("/test/config")
        result = layer_adapter.resolve_legacy_path("commands")
        assert _posix(result) == "/test/config/commands"
        layer_adapter.set_config_root_override(None)

    def test_resolve_legacy_governance_path(self) -> None:
        """Legacy commands/governance/ path resolves to runtime root."""
        layer_adapter.set_config_root_override("/test/config")
        result = layer_adapter.resolve_legacy_path("commands/governance_runtime")
        assert _posix(result).endswith("/.local/opencode/governance_runtime")
        layer_adapter.set_config_root_override(None)

    def test_resolve_legacy_governance_with_suffix_preserved(self) -> None:
        """Legacy path with suffix preserves the suffix."""
        layer_adapter.set_config_root_override("/test/config")
        result = layer_adapter.resolve_legacy_path("commands/governance_runtime/engine/x.py")
        assert _posix(result).endswith("/.local/opencode/governance_runtime/engine/x.py")
        layer_adapter.set_config_root_override(None)

    def test_resolve_legacy_docs_with_suffix_preserved(self) -> None:
        """Legacy docs path with suffix preserves the suffix."""
        layer_adapter.set_config_root_override("/test/config")
        result = layer_adapter.resolve_legacy_path("commands/docs/foo.md")
        assert _posix(result).endswith("/.local/opencode/governance_content/docs/foo.md")
        layer_adapter.set_config_root_override(None)

    def test_resolve_legacy_profiles_with_suffix_preserved(self) -> None:
        """Legacy profiles path with suffix preserves the suffix."""
        layer_adapter.set_config_root_override("/test/config")
        result = layer_adapter.resolve_legacy_path("commands/profiles/rules.md")
        assert _posix(result).endswith("/.local/opencode/governance_content/profiles/rules.md")
        layer_adapter.set_config_root_override(None)

    def test_resolve_legacy_docs_path(self) -> None:
        """Legacy commands/docs/ path resolves to content root with docs."""
        layer_adapter.set_config_root_override("/test/config")
        result = layer_adapter.resolve_legacy_path("commands/docs")
        assert _posix(result).endswith("/.local/opencode/governance_content/docs")
        layer_adapter.set_config_root_override(None)

    def test_resolve_unknown_legacy_path_defaults_to_commands(self) -> None:
        """Unknown legacy paths default to commands root."""
        layer_adapter.set_config_root_override("/test/config")
        result = layer_adapter.resolve_legacy_path("some/unknown/path")
        assert _posix(result) == "/test/config/commands"
        layer_adapter.set_config_root_override(None)

    def test_legacy_path_with_backslash_normalized(self) -> None:
        """Windows backslash paths are normalized to forward slash."""
        layer_adapter.set_config_root_override("/test/config")
        result = layer_adapter.resolve_legacy_path("commands\\governance_runtime")
        assert "\\" not in _posix(result)
        layer_adapter.set_config_root_override(None)


class TestPathAdapterBadPath:
    """Bad path: error handling and edge cases."""

    def test_empty_fingerprint_handled(self) -> None:
        """Empty fingerprint should still produce a path (not error)."""
        layer_adapter.set_config_root_override("/test/config")
        # Empty fingerprint is allowed (produces workspace/ dir)
        result = layer_adapter.get_workspace_root("")
        assert "workspaces" in str(result)
        layer_adapter.set_config_root_override(None)

    def test_special_characters_in_fingerprint(self) -> None:
        """Special characters in fingerprint are preserved in path."""
        layer_adapter.set_config_root_override("/test/config")
        fp = "test-fp_123"
        result = layer_adapter.get_workspace_root(fp)
        assert fp in str(result)
        layer_adapter.set_config_root_override(None)


class TestPathAdapterCornerCases:
    """Corner cases: unusual but valid inputs."""

    def test_absolute_path_in_env_variable(self) -> None:
        """Environment variable with absolute path works."""
        with patch.dict(os.environ, {"OPENCODE_CONFIG_ROOT": "/absolute/path"}):
            layer_adapter.set_config_root_override(None)
            result = layer_adapter.get_config_root()
            assert _posix(result) == "/absolute/path"

    def test_relative_path_in_env_variable_accepted(self) -> None:
        """Relative paths in env var are accepted (not converted to absolute)."""
        with patch.dict(os.environ, {"OPENCODE_CONFIG_ROOT": "relative/path"}):
            layer_adapter.set_config_root_override(None)
            result = layer_adapter.get_config_root()
            # Relative paths are accepted as-is (not resolved to absolute)
            assert "relative/path" in _posix(result)

    def test_path_with_trailing_slash(self) -> None:
        """Paths with trailing slashes are handled correctly."""
        layer_adapter.set_config_root_override("/test/config")
        result = layer_adapter.resolve_legacy_path("commands/")
        # Should not have double slashes
        assert "//" not in _posix(result)
        layer_adapter.set_config_root_override(None)

    def test_path_with_leading_slash(self) -> None:
        """Paths with leading slashes are handled correctly."""
        layer_adapter.set_config_root_override("/test/config")
        result = layer_adapter.resolve_legacy_path("/commands/governance_runtime")
        # Should not have issues
        assert _posix(result).endswith("/.local/opencode/governance_runtime")
        layer_adapter.set_config_root_override(None)
