from __future__ import annotations

import os
from pathlib import Path

import pytest

from install import BIN_DIR_PLACEHOLDER, inject_session_reader_path_for_command

from .util import REPO_ROOT


@pytest.mark.governance
def test_implement_md_exists_and_documents_canonical_surface() -> None:
    path = REPO_ROOT / "opencode" / "commands" / "implement.md"
    assert path.exists(), "opencode/commands/implement.md must exist"
    content = path.read_text(encoding="utf-8")
    assert "--implement-start" in content
    assert BIN_DIR_PLACEHOLDER in content
    assert "opencode-governance-bootstrap" in content
    assert "starts execution of the approved implementation plan" in content
    assert "run internal implementation self-review" in content


@pytest.mark.governance
def test_implement_md_bin_dir_placeholder_is_injected(tmp_path: Path) -> None:
    commands_dir = tmp_path / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)
    command_md = commands_dir / "implement.md"
    command_md.write_text(
        "```bash\n"
        f'PATH="{BIN_DIR_PLACEHOLDER}:$PATH" opencode-governance-bootstrap '
        '--implement-start --quiet\n'
        "```\n",
        encoding="utf-8",
    )

    result = inject_session_reader_path_for_command(
        commands_dir,
        command_markdown="implement.md",
        bin_dir="/usr/local/governance/bin",
        dry_run=False,
    )
    assert result["status"] == "injected"
    content = command_md.read_text(encoding="utf-8")
    assert "{{BIN_DIR}}" not in content
    assert "/usr/local/governance/bin" in content
    if os.name == "nt":
        assert "opencode-governance-bootstrap.cmd --implement-start" in content
    else:
        assert "opencode-governance-bootstrap --implement-start" in content
