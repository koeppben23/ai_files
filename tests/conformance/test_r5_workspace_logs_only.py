"""R5 hard conformance: runtime logs must use workspace logs only."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.conformance
class TestR5WorkspaceLogsOnly:
    def test_global_error_handler_has_no_commands_logs_fallback(self) -> None:
        handler = REPO_ROOT / "governance_runtime" / "infrastructure" / "logging" / "global_error_handler.py"
        content = handler.read_text(encoding="utf-8")
        assert '"logs" / "error.log.jsonl"' in content, "workspace error log path must exist"
        assert "commands_home" in content, "context may keep commands_home for diagnostics"
        assert "cmd_path / \"logs\"" not in content, "commands/logs fallback must be removed"

    def test_phase_kernel_uses_workspace_logs_root(self) -> None:
        phase_kernel = REPO_ROOT / "governance_runtime" / "kernel" / "phase_kernel.py"
        content = phase_kernel.read_text(encoding="utf-8")
        assert "from governance_runtime.paths import get_workspace_logs_root" in content
        assert "workspace_flow" in content
        assert "workspace_boot" in content
        assert "workspace_error" in content
