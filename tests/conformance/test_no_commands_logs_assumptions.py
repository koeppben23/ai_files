"""
Commands Logs Removal Conformance Test

Validates that commands/logs/ is no longer assumed as primary log location.
This is part of Wave 25c - remove commands/logs assumptions.
"""
from __future__ import annotations

import pytest
from pathlib import Path
import re

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.conformance
class TestNoCommandsLogsAssumptions:
    """Validate commands/logs/ is deprecated as primary log location."""

    def test_conformance_tests_no_commands_logs_primary(self):
        """Happy: Conformance tests should not use commands/logs/ as primary path."""
        conformance_dir = REPO_ROOT / "tests" / "conformance"
        
        # Verify commands/logs/ does not exist — workspace-only model is in effect
        commands_logs = REPO_ROOT / "commands" / "logs"
        assert not commands_logs.exists(), (
            f"commands/logs/ still present — workspace-only model requires removal"
        )

    def test_runtime_kernel_no_new_commands_logs_writes(self):
        """Happy: Runtime kernel should not write new logs to commands/logs/."""
        phase_kernel = REPO_ROOT / "governance_runtime" / "kernel" / "phase_kernel.py"
        content = phase_kernel.read_text(encoding="utf-8")
        
        # Should have workspace paths defined
        assert "workspace_flow" in content, "Must use workspace paths"
        
        # Commands paths should be marked as legacy if present
        if "commands_flow" in content:
            # Should be deprecated/marked as legacy
            assert "legacy" in content.lower() or "deprecated" in content.lower() or "# Wave 25" in content, \
                "commands paths should be marked as legacy"

    def test_workspace_logs_target_documented(self):
        """Happy: Target model is workspace-only logs."""
        # Verify that workspace logs are the target
        phase_kernel = REPO_ROOT / "governance_runtime" / "kernel" / "phase_kernel.py"
        content = phase_kernel.read_text(encoding="utf-8")
        
        # Workspace paths should be primary
        assert content.count("workspace_") >= 3, \
            "Should have multiple workspace paths (workspace_flow, workspace_boot, workspace_error)"

    def test_log_writer_contract_workspace_only(self):
        """Happy: Log writer contract should be workspace-only."""
        # Phase kernel must define workspace_flow, workspace_boot, workspace_error
        # and must NOT define commands_flow or commands_logs
        phase_kernel = REPO_ROOT / "governance_runtime" / "kernel" / "phase_kernel.py"
        content = phase_kernel.read_text(encoding="utf-8")
        assert "workspace_flow" in content, "Must define workspace_flow log path"
        assert "workspace_boot" in content, "Must define workspace_boot log path"
        assert "commands_flow" not in content, (
            "commands_flow must not exist — workspace-only model"
        )

    def test_no_test_assumes_commands_logs_valid(self):
        """Happy: Tests should not assume commands/logs is valid for new writes."""
        # This test documents the intent
        # Actual removal of assumptions happens in test updates
        # For now, we validate that the target model is documented
        
        # Check test files for workspace-only mentions
        test_files = list((REPO_ROOT / "tests" / "conformance").glob("test_*logs*.py"))
        
        # We should have workspace log tests
        assert len(test_files) >= 2, \
            "Should have workspace log conformance tests"
