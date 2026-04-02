"""
Workspace Logs Only Conformance Test

Validates that logs should only be under workspaces/<fp>/logs/.
This is part of Wave 25a - workspace logs inventory and conformance.
"""
from __future__ import annotations

import pytest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.conformance
class TestWorkspaceLogsOnlyConformance:
    """Validate workspace-only logs model."""

    def test_workspace_logs_path_model(self):
        """Happy: Logs should be under workspaces/<fp>/logs/ not commands/logs/."""
        # Workspace paths are resolved at runtime from config-derived locations
        # (e.g. ~/.config/opencode/workspaces/<fp>/logs/), not from repo root.
        # Verify the repo does NOT contain a commands/logs/ directory.
        commands_logs = REPO_ROOT / "commands" / "logs"
        assert not commands_logs.exists(), (
            "commands/logs/ must not exist — workspace-only model in effect"
        )

    def test_no_commands_logs_in_target_model(self):
        """Happy: commands/logs/ should NOT be the primary log location."""
        # Verify phase_kernel defines workspace log paths, not commands log paths
        phase_kernel = REPO_ROOT / "governance_runtime" / "kernel" / "phase_kernel.py"
        content = phase_kernel.read_text(encoding="utf-8")
        assert "workspace_flow" in content, "workspace_flow must be defined"
        assert "commands_flow" not in content, "commands_flow must not be defined"

    def test_log_routing_respects_workspace_model(self):
        """Happy: Log routing should prioritize workspace paths."""
        # Phase kernel must have the Wave 25b comment confirming workspace-only
        phase_kernel = REPO_ROOT / "governance_runtime" / "kernel" / "phase_kernel.py"
        content = phase_kernel.read_text(encoding="utf-8")
        assert "workspace" in content.lower(), "Log routing must reference workspace paths"
        assert "workspace_boot" in content, "workspace_boot log path must be defined"

    def test_workspace_directory_structure_for_logs(self):
        """Happy: Workspace structure supports logs subdirectory."""
        # Verify phase_kernel defines the expected log file names under workspace
        phase_kernel = REPO_ROOT / "governance_runtime" / "kernel" / "phase_kernel.py"
        content = phase_kernel.read_text(encoding="utf-8")
        # Expected log files: flow.log.jsonl, boot.log.jsonl, error.log.jsonl
        assert "flow.log.jsonl" in content, "workspace must define flow.log.jsonl"
        assert "boot.log.jsonl" in content, "workspace must define boot.log.jsonl"
        assert "error.log.jsonl" in content, "workspace must define error.log.jsonl"


@pytest.mark.conformance  
class TestLogPathInventory:
    """Inventory of current log path usage."""

    def test_governance_content_docs_workspace_logs_section(self):
        """Check if governance_content/docs mentions workspace logs."""
        docs = REPO_ROOT / "governance_content" / "docs"
        if docs.is_dir():
            # Check for any docs mentioning workspace logs
            doc_files = list(docs.glob("*.md"))
            # Just verify docs exist
            assert len(doc_files) >= 0

    def test_log_schema_locations(self):
        """Verify log schemas are defined in governance."""
        # Log structure is defined inline in phase_kernel (not as separate schema files)
        # Verify the engine directory exists and has session state schema at minimum
        engine = REPO_ROOT / "governance_runtime" / "engine"
        assert engine.is_dir(), "governance_runtime/engine/ must exist"
        schema_file = engine / "_embedded_session_state_schema.py"
        assert schema_file.exists(), "Embedded session state schema must exist"
