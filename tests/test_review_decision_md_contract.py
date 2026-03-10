from __future__ import annotations

import os
from pathlib import Path

import pytest

from install import BIN_DIR_PLACEHOLDER, inject_session_reader_path_for_command

from .util import REPO_ROOT


@pytest.mark.governance
def test_review_decision_md_exists_and_documents_canonical_surface() -> None:
    path = REPO_ROOT / "review-decision.md"
    assert path.exists(), "review-decision.md must exist in repo root"
    content = path.read_text(encoding="utf-8")
    assert "--review-decision-persist" in content
    assert "governance.entrypoints.review_decision_persist" not in content
    assert BIN_DIR_PLACEHOLDER in content
    assert "opencode-governance-bootstrap" in content
    assert "decision=approve|changes_requested|reject" in content
    assert "No default is allowed" in content


@pytest.mark.governance
def test_review_decision_md_bin_dir_placeholder_is_injected(tmp_path: Path) -> None:
    commands_dir = tmp_path / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)
    command_md = commands_dir / "review-decision.md"
    command_md.write_text(
        "```bash\n"
        f'PATH="{BIN_DIR_PLACEHOLDER}:$PATH" opencode-governance-bootstrap '
        '--review-decision-persist --decision "approve" --note "ok" --quiet\n'
        "```\n",
        encoding="utf-8",
    )

    result = inject_session_reader_path_for_command(
        commands_dir,
        command_markdown="review-decision.md",
        bin_dir="/usr/local/governance/bin",
        dry_run=False,
    )
    assert result["status"] == "injected"
    content = command_md.read_text(encoding="utf-8")
    assert "{{BIN_DIR}}" not in content
    assert "/usr/local/governance/bin" in content
    if os.name == "nt":
        assert "opencode-governance-bootstrap.cmd --review-decision-persist" in content
    else:
        assert "opencode-governance-bootstrap --review-decision-persist" in content
