"""
Tests for Governance Installer Integration - Wave 11

Validates the installer integration layer.

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from governance.installer import (
    collect_by_layer,
    collect_installable,
    collect_static_payload,
    is_installable_path,
    get_layer_info,
    exclude_state_files,
    iter_files_recursive,
)
from governance import GovernanceLayer


class TestIterFilesRecursive:
    """Test file iteration."""

    def test_iterates_files(self, tmp_path: Path) -> None:
        """Iterates all files under root."""
        (tmp_path / "file1.txt").touch()
        (tmp_path / "file2.md").touch()
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "file3.py").touch()
        
        files = list(iter_files_recursive(tmp_path))
        
        assert len(files) == 3


class TestCollectByLayer:
    """Test layer-based collection."""

    def test_collect_commands(self, tmp_path: Path) -> None:
        """Collects files by layer."""
        (tmp_path / "continue.md").write_text("# Continue")
        (tmp_path / "plan.md").write_text("# Plan")
        (tmp_path / "master.md").write_text("# Master")
        
        result = collect_by_layer(tmp_path, GovernanceLayer.OPENCODE_INTEGRATION)
        
        names = [p.name for p in result]
        assert "continue.md" in names
        assert "plan.md" in names
        assert "master.md" not in names

    def test_collect_content(self, tmp_path: Path) -> None:
        """Collects content files."""
        (tmp_path / "master.md").write_text("# Master")
        (tmp_path / "README.md").write_text("# Readme")
        (tmp_path / "continue.md").write_text("# Continue")
        
        result = collect_by_layer(tmp_path, GovernanceLayer.GOVERNANCE_CONTENT)
        
        names = [p.name for p in result]
        assert "master.md" in names
        assert "README.md" in names
        assert "continue.md" not in names


class TestCollectInstallable:
    """Test installable file collection."""

    def test_collects_installable(self, tmp_path: Path) -> None:
        """Collects all installable files."""
        (tmp_path / "commands").mkdir()
        (tmp_path / "commands" / "continue.md").write_text("# Continue")
        (tmp_path / "master.md").write_text("# Master")
        (tmp_path / "phase_api.yaml").write_text("spec: true")
        (tmp_path / "orchestrator.py").write_text("# Python")
        
        result = collect_installable(tmp_path)
        
        names = [p.name for p in result]
        assert "continue.md" in names
        assert "master.md" in names
        assert "phase_api.yaml" in names
        assert "orchestrator.py" in names


class TestCollectStaticPayload:
    """Test static payload collection."""

    def test_collects_static(self, tmp_path: Path) -> None:
        """Collects static content and spec files."""
        (tmp_path / "master.md").write_text("# Master")
        (tmp_path / "phase_api.yaml").write_text("spec: true")
        (tmp_path / "orchestrator.py").write_text("# Python")
        
        result = collect_static_payload(tmp_path)
        
        names = [p.name for p in result]
        assert "master.md" in names
        assert "phase_api.yaml" in names
        assert "orchestrator.py" not in names


class TestIsInstallablePath:
    """Test installability check."""

    def test_command_is_installable(self) -> None:
        """Commands are installable."""
        assert is_installable_path("commands/continue.md") is True

    def test_content_is_installable(self) -> None:
        """Content is installable."""
        assert is_installable_path("master.md") is True

    def test_state_not_installable(self) -> None:
        """State files are not installable."""
        assert is_installable_path("SESSION_STATE.json") is False

    def test_command_in_wrong_location(self) -> None:
        """Command in docs/ is still installable (wrong location, but layer is correct)."""
        assert is_installable_path("docs/continue.md") is True

    def test_content_in_wrong_location(self) -> None:
        """Content in commands/ is still installable (wrong location, but layer is correct)."""
        assert is_installable_path("commands/master.md") is True


class TestGetLayerInfo:
    """Test layer info retrieval."""

    def test_returns_layer_info(self) -> None:
        """Returns complete layer info."""
        info = get_layer_info("commands/continue.md")
        
        assert info["layer"] == GovernanceLayer.OPENCODE_INTEGRATION
        assert info["is_installable"] is True
        assert info["is_static_payload"] is False

    def test_content_in_commands(self) -> None:
        """Content in commands/ is still content layer."""
        info = get_layer_info("commands/master.md")
        
        assert info["layer"] == GovernanceLayer.GOVERNANCE_CONTENT
        assert info["is_installable"] is True
        assert info["is_static_payload"] is True

    def test_command_in_docs(self) -> None:
        """Command in docs/ is still command layer."""
        info = get_layer_info("docs/continue.md")
        
        assert info["layer"] == GovernanceLayer.OPENCODE_INTEGRATION
        assert info["is_installable"] is True


class TestExcludeStateFiles:
    """Test state file exclusion."""

    def test_excludes_state(self) -> None:
        """Removes state files from list."""
        paths = [
            Path("commands/continue.md"),
            Path("SESSION_STATE.json"),
            Path("master.md"),
            Path("events.jsonl"),
        ]
        
        result = exclude_state_files(paths)
        
        assert len(result) == 2
        assert Path("commands/continue.md") in result
        assert Path("master.md") in result
        assert Path("SESSION_STATE.json") not in result
        assert Path("events.jsonl") not in result

    def test_excludes_state_in_workspace(self) -> None:
        """Removes state files in workspaces/ from list."""
        paths = [
            Path("workspaces/abc/logs/flow.log.jsonl"),
            Path("commands/continue.md"),
            Path("master.md"),
        ]
        
        result = exclude_state_files(paths)
        
        assert len(result) == 2
        assert Path("workspaces/abc/logs/flow.log.jsonl") not in result

    def test_excludes_state_in_wrong_location(self) -> None:
        """Removes state files even in wrong locations."""
        paths = [
            Path("commands/logs/flow.log.jsonl"),  # Wrong location but still state type
            Path("commands/continue.md"),
        ]
        
        result = exclude_state_files(paths)
        
        assert len(result) == 1
        assert Path("commands/logs/flow.log.jsonl") not in result
