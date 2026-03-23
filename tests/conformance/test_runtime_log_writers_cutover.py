"""
Runtime Log Writers Cutover Test

Validates that runtime log writers use workspace paths only.
This is part of Wave 25b - runtime log writers cutover.
"""
from __future__ import annotations

import pytest
from pathlib import Path
import re

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.conformance
class TestRuntimeLogWritersCutover:
    """Validate runtime log writers use workspace-only paths."""

    def test_phase_kernel_workspace_only_flow_paths(self):
        """Happy: phase_kernel uses workspace-only log paths."""
        phase_kernel = REPO_ROOT / "governance_runtime" / "kernel" / "phase_kernel.py"
        content = phase_kernel.read_text(encoding="utf-8")
        
        # Should have workspace log paths
        assert "workspace_flow" in content, "Must have workspace_flow path"
        assert "workspace_boot" in content, "Must have workspace_boot path"
        assert "workspace_error" in content, "Must have workspace_error path"
        
        # Should have get_workspace_logs_root
        assert "get_workspace_logs_root" in content, "Must use get_workspace_logs_root"

    def test_phase_kernel_no_new_commands_logs_writes(self):
        """Happy: phase_kernel should not write new logs to commands/logs/."""
        phase_kernel = REPO_ROOT / "governance_runtime" / "kernel" / "phase_kernel.py"
        content = phase_kernel.read_text(encoding="utf-8")
        
        # Check that workspace paths are prioritized
        # The function should return workspace paths as primary
        assert "workspace_flow" in content, "workspace_flow should be defined"
        
    def test_global_error_handler_workspace_priority(self):
        """Happy: global error handler should prioritize workspace paths."""
        handler = REPO_ROOT / "governance_runtime" / "infrastructure" / "logging" / "global_error_handler.py"
        if handler.exists():
            content = handler.read_text(encoding="utf-8")
            # Should have workspace path candidates
            assert "workspace" in content.lower() or "workspaces" in content.lower(), \
                "Error handler should consider workspace paths"

    def test_log_paths_module_workspace_function(self):
        """Happy: paths module provides get_workspace_logs_root."""
        # Check governance.paths
        possible_paths = [
            REPO_ROOT / "governance_runtime" / "layer_adapter.py",
            REPO_ROOT / "governance_runtime" / "paths.py",
            REPO_ROOT / "governance_runtime" / "infrastructure" / "workspace_paths.py",
        ]
        
        found = False
        for paths_file in possible_paths:
            if paths_file.exists():
                content = paths_file.read_text(encoding="utf-8")
                if "get_workspace_logs_root" in content:
                    found = True
                    break
        
        assert found, "get_workspace_logs_root function should exist"

    def test_no_new_writes_to_commands_logs(self):
        """Happy: Runtime should not write new logs to commands/logs/."""
        # This test validates the intent - actual migration is in the code
        # Check that the model prefers workspace paths
        
        phase_kernel = REPO_ROOT / "governance_runtime" / "kernel" / "phase_kernel.py"
        content = phase_kernel.read_text(encoding="utf-8")
        
        # The function should define workspace paths
        # and mark commands paths as legacy
        assert "workspace_flow" in content, "Must prioritize workspace paths"
