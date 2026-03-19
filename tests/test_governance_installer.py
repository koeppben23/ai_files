"""
Tests for Governance Installer Integration - Wave 13

Validates the installer integration layer including new layer-based collectors.

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
    collect_commands,
    collect_opencode_integration,
    collect_content,
    collect_specs,
    collect_runtime,
    collect_for_install_target,
    install_commands_target,
    install_content_target,
    install_spec_target,
    install_runtime_target,
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


class TestCollectCommands:
    """Test canonical command collection."""

    def test_collects_only_canonical_commands(self, tmp_path: Path) -> None:
        """Collects only the 8 canonical commands."""
        (tmp_path / "continue.md").write_text("# Continue")
        (tmp_path / "plan.md").write_text("# Plan")
        (tmp_path / "review.md").write_text("# Review")
        (tmp_path / "review-decision.md").write_text("# Review Decision")
        (tmp_path / "ticket.md").write_text("# Ticket")
        (tmp_path / "implement.md").write_text("# Implement")
        (tmp_path / "implementation-decision.md").write_text("# Implementation Decision")
        (tmp_path / "audit-readout.md").write_text("# Audit Readout")
        (tmp_path / "master.md").write_text("# Master")  # Not a command
        (tmp_path / "rules.md").write_text("# Rules")    # Not a command
        
        result = collect_commands(tmp_path)
        
        names = {p.name for p in result}
        assert names == {
            "continue.md",
            "plan.md",
            "review.md",
            "review-decision.md",
            "ticket.md",
            "implement.md",
            "implementation-decision.md",
            "audit-readout.md",
        }

    def test_ignores_non_commands(self, tmp_path: Path) -> None:
        """Ignores content files that are not commands."""
        (tmp_path / "master.md").write_text("# Master")
        (tmp_path / "rules.md").write_text("# Rules")
        (tmp_path / "README.md").write_text("# Readme")
        
        result = collect_commands(tmp_path)
        
        assert len(result) == 0


class TestCollectOpencodeIntegration:
    """Test OpenCode integration collection."""

    def test_collects_commands_and_plugins(self, tmp_path: Path) -> None:
        """Collects commands and plugins."""
        (tmp_path / "commands").mkdir()
        (tmp_path / "commands" / "continue.md").write_text("# Continue")
        (tmp_path / "plugins").mkdir()
        (tmp_path / "plugins" / "test.py").write_text("# Plugin")
        (tmp_path / "master.md").write_text("# Master")  # Content, not integration
        
        result = collect_opencode_integration(tmp_path)
        
        names = {p.name for p in result}
        assert "continue.md" in names


class TestCollectContent:
    """Test content collection."""

    def test_collects_content_files(self, tmp_path: Path) -> None:
        """Collects content files."""
        (tmp_path / "master.md").write_text("# Master")
        (tmp_path / "rules.md").write_text("# Rules")
        (tmp_path / "README.md").write_text("# Readme")
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "guide.md").write_text("# Guide")
        (tmp_path / "profiles").mkdir()
        (tmp_path / "profiles" / "default.json").write_text("{}")
        (tmp_path / "continue.md").write_text("# Continue")  # Command, not content
        
        result = collect_content(tmp_path)
        
        names = {p.name for p in result}
        assert "master.md" in names
        assert "rules.md" in names
        assert "README.md" in names
        assert "guide.md" in names
        assert "default.json" in names
        assert "continue.md" not in names


class TestCollectSpecs:
    """Test spec collection."""

    def test_collects_spec_files(self, tmp_path: Path) -> None:
        """Collects spec files."""
        (tmp_path / "phase_api.yaml").write_text("phases: []")
        (tmp_path / "rules.yml").write_text("rules: {}")
        (tmp_path / "schemas").mkdir()
        (tmp_path / "schemas" / "schema.json").write_text("{}")
        (tmp_path / "master.md").write_text("# Master")  # Content, not spec
        
        result = collect_specs(tmp_path)
        
        names = {p.name for p in result}
        assert "phase_api.yaml" in names
        assert "rules.yml" in names
        assert "schema.json" in names


class TestCollectRuntime:
    """Test runtime collection."""

    def test_collects_runtime_files(self, tmp_path: Path) -> None:
        """Collects runtime Python files."""
        (tmp_path / "governance").mkdir()
        (tmp_path / "governance" / "orchestrator.py").write_text("# Python")
        (tmp_path / "governance" / "__init__.py").write_text("# Init")
        (tmp_path / "master.md").write_text("# Master")  # Content, not runtime
        
        result = collect_runtime(tmp_path)
        
        names = {p.name for p in result}
        assert "orchestrator.py" in names
        assert "__init__.py" in names


class TestInstallTargets:
    """Test install target path functions."""

    def test_commands_target(self) -> None:
        """Returns commands target path."""
        assert install_commands_target() == "commands"

    def test_content_target(self) -> None:
        """Returns content target path."""
        assert install_content_target() == "commands"

    def test_spec_target(self) -> None:
        """Returns spec target path."""
        assert install_spec_target() == "commands"

    def test_runtime_target(self) -> None:
        """Returns runtime target path."""
        assert install_runtime_target() == "local/governance_runtime"


class TestCollectForInstallTarget:
    """Test target-based collection."""

    def test_collects_commands_for_target(self, tmp_path: Path) -> None:
        """Collects commands when target is 'commands'."""
        (tmp_path / "continue.md").write_text("# Continue")
        (tmp_path / "master.md").write_text("# Master")
        
        result = collect_for_install_target(tmp_path, "commands")
        
        names = {p.name for p in result}
        assert "continue.md" in names
        assert "master.md" not in names

    def test_collects_content_for_target(self, tmp_path: Path) -> None:
        """Collects content when target is 'content'."""
        (tmp_path / "continue.md").write_text("# Continue")
        (tmp_path / "master.md").write_text("# Master")
        
        result = collect_for_install_target(tmp_path, "content")
        
        names = {p.name for p in result}
        assert "master.md" in names
        assert "continue.md" not in names

    def test_collects_specs_for_target(self, tmp_path: Path) -> None:
        """Collects specs when target is 'specs'."""
        (tmp_path / "phase_api.yaml").write_text("phases: []")
        (tmp_path / "master.md").write_text("# Master")
        
        result = collect_for_install_target(tmp_path, "specs")
        
        names = {p.name for p in result}
        assert "phase_api.yaml" in names
        assert "master.md" not in names

    def test_collects_runtime_for_target(self, tmp_path: Path) -> None:
        """Collects runtime when target is 'runtime'."""
        (tmp_path / "governance").mkdir()
        (tmp_path / "governance" / "orchestrator.py").write_text("# Python")
        (tmp_path / "master.md").write_text("# Master")
        
        result = collect_for_install_target(tmp_path, "runtime")
        
        names = {p.name for p in result}
        assert "orchestrator.py" in names
        assert "master.md" not in names

    def test_returns_empty_for_unknown_target(self, tmp_path: Path) -> None:
        """Returns empty list for unknown target."""
        result = collect_for_install_target(tmp_path, "unknown")
        
        assert result == []
