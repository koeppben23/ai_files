from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.conformance
class TestF100WorkspaceLogsOnly:
    def test_runtime_error_handler_has_no_commands_logs_fallback(self) -> None:
        handler = REPO_ROOT / "governance_runtime" / "infrastructure" / "logging" / "global_error_handler.py"
        content = handler.read_text(encoding="utf-8")
        assert "cmd_path / \"logs\"" not in content

    def test_phase_kernel_uses_workspace_flow_paths_only(self) -> None:
        kernel = REPO_ROOT / "governance_runtime" / "kernel" / "phase_kernel.py"
        content = kernel.read_text(encoding="utf-8")
        assert "workspace_flow" in content
        assert "workspace_boot" in content
        assert "workspace_error" in content
        assert "commands_flow" not in content
        assert "commands_boot" not in content

    def test_runtime_installer_global_error_logs_home_is_workspace_global(self) -> None:
        installer = REPO_ROOT / "governance_runtime" / "install" / "install.py"
        content = installer.read_text(encoding="utf-8")
        assert 'global_error_logs_home = workspaces_home / "_global" / "logs"' in content
