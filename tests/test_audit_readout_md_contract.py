from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from install import (
    BIN_DIR_PLACEHOLDER,
    inject_session_reader_path_for_command,
)
from tests.util import REPO_ROOT


@pytest.mark.governance
def test_audit_readout_md_exists_and_has_bridge_contract() -> None:
    path = REPO_ROOT / "opencode" / "commands" / "audit-readout.md"
    assert path.exists(), "opencode/commands/audit-readout.md must exist"
    content = path.read_text(encoding="utf-8")
    assert BIN_DIR_PLACEHOLDER in content
    assert "opencode-governance-bootstrap" in content
    assert "--session-reader" in content
    assert "safe to execute" not in content.lower(), (
        "audit-readout.md must NOT contain 'safe to execute' — trust-triggering language"
    )
    assert "do not infer additional state beyond the materialized output" in content.lower() or \
           "do not infer additional state" in content.lower()


@pytest.mark.governance
def test_audit_readout_md_rail_classification() -> None:
    path = REPO_ROOT / "opencode" / "commands" / "audit-readout.md"
    content = path.read_text(encoding="utf-8")
    match = re.search(r"<!--\s*rail-classification:\s*([^>]+)-->", content)
    assert match is not None
    classification = match.group(1)
    assert "READ-ONLY" in classification
    assert "OUTPUT-ONLY" in classification
    assert "NO-STATE-CHANGE" in classification
    assert "MUTATING" not in classification


@pytest.mark.governance
def test_audit_readout_md_injection_replaces_placeholders(tmp_path: Path) -> None:
    commands_dir = tmp_path / "commands"
    commands_dir.mkdir(parents=True)
    cmd = commands_dir / "audit-readout.md"
    cmd.write_text(
        (
            "# Governance Audit Readout\n"
            "```bash\n"
            f'PATH="{BIN_DIR_PLACEHOLDER}:$PATH" opencode-governance-bootstrap '
            "--session-reader --audit --tail-count 25\n"
            "```\n"
        ),
        encoding="utf-8",
    )

    result = inject_session_reader_path_for_command(
        commands_dir,
        command_markdown="audit-readout.md",
        bin_dir="/home/user/.config/opencode/bin",
        dry_run=False,
    )
    assert result["status"] == "injected"
    content = cmd.read_text(encoding="utf-8")
    assert BIN_DIR_PLACEHOLDER not in content
    assert "/home/user/.config/opencode/bin" in content
    assert "--audit --tail-count 25" in content
    if os.name == "nt":
        assert "```cmd" in content
        assert "opencode-governance-bootstrap.cmd" in content
    else:
        assert "```bash" in content
