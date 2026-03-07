from __future__ import annotations

import os
from pathlib import Path

import pytest

from install import BIN_DIR_PLACEHOLDER, inject_session_reader_path_for_command

from .util import REPO_ROOT


@pytest.mark.governance
def test_ticket_md_exists_and_documents_intake_bridge() -> None:
    ticket_path = REPO_ROOT / "ticket.md"
    assert ticket_path.exists(), "ticket.md must exist in repo root"
    content = ticket_path.read_text(encoding="utf-8")
    assert "phase4_intake_persist" in content
    assert BIN_DIR_PLACEHOLDER in content
    assert "opencode-governance-bootstrap" in content
    assert "/review` is read-only; `/continue` is the state materialization rail" in content


@pytest.mark.governance
def test_ticket_md_bin_dir_placeholder_is_injected(tmp_path: Path) -> None:
    commands_dir = tmp_path / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)
    command_md = commands_dir / "ticket.md"
    command_md.write_text(
        "```bash\n"
        f'PATH="{BIN_DIR_PLACEHOLDER}:$PATH" opencode-governance-bootstrap '
        "--entrypoint governance.entrypoints.phase4_intake_persist "
        '--ticket-text "x"\n'
        "```\n",
        encoding="utf-8",
    )

    result = inject_session_reader_path_for_command(
        commands_dir,
        command_markdown="ticket.md",
        bin_dir="/usr/local/governance/bin",
        dry_run=False,
    )
    assert result["status"] == "injected"
    content = command_md.read_text(encoding="utf-8")
    assert "{{BIN_DIR}}" not in content
    assert "/usr/local/governance/bin" in content
    if os.name == "nt":
        assert "opencode-governance-bootstrap.cmd --entrypoint governance.entrypoints.phase4_intake_persist" in content
    else:
        assert "opencode-governance-bootstrap --entrypoint governance.entrypoints.phase4_intake_persist" in content
