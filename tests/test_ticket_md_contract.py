from __future__ import annotations

from pathlib import Path

import pytest

from install import PYTHON_COMMAND_PLACEHOLDER, inject_session_reader_path_for_command

from .util import REPO_ROOT


@pytest.mark.governance
def test_ticket_md_exists_and_documents_intake_bridge() -> None:
    ticket_path = REPO_ROOT / "ticket.md"
    assert ticket_path.exists(), "ticket.md must exist in repo root"
    content = ticket_path.read_text(encoding="utf-8")
    assert "phase4_intake_persist" in content
    assert PYTHON_COMMAND_PLACEHOLDER in content
    assert "read-only rails" in content


@pytest.mark.governance
def test_ticket_md_python_placeholder_is_injected(tmp_path: Path) -> None:
    commands_dir = tmp_path / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)
    command_md = commands_dir / "ticket.md"
    command_md.write_text(
        "```bash\n"
        f"{PYTHON_COMMAND_PLACEHOLDER} -m governance.entrypoints.phase4_intake_persist --ticket-text \"x\"\n"
        "```\n",
        encoding="utf-8",
    )

    result = inject_session_reader_path_for_command(
        commands_dir,
        command_markdown="ticket.md",
        python_command="/usr/bin/python3",
        dry_run=False,
    )
    assert result["status"] == "injected"
    content = command_md.read_text(encoding="utf-8")
    assert "{{PYTHON_COMMAND}}" not in content
    assert "/usr/bin/python3 -m governance.entrypoints.phase4_intake_persist" in content
