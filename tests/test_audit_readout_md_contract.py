from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

from install import (
    PYTHON_COMMAND_PLACEHOLDER,
    SESSION_READER_PLACEHOLDER,
    inject_session_reader_path_for_command,
)
from tests.util import REPO_ROOT


@pytest.mark.governance
def test_audit_readout_md_exists_and_has_bridge_contract() -> None:
    path = REPO_ROOT / "audit-readout.md"
    assert path.exists(), "audit-readout.md must exist in repo root"
    content = path.read_text(encoding="utf-8")
    assert SESSION_READER_PLACEHOLDER in content
    assert PYTHON_COMMAND_PLACEHOLDER in content
    assert "safe to execute" in content.lower()
    assert "do not infer or mutate any session state" in content.lower()


@pytest.mark.governance
def test_audit_readout_md_rail_classification() -> None:
    path = REPO_ROOT / "audit-readout.md"
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
    (commands_dir / "governance" / "entrypoints").mkdir(parents=True)
    cmd = commands_dir / "audit-readout.md"
    cmd.write_text(
        (
            "# Governance Audit Readout\n"
            "```bash\n"
            f"{PYTHON_COMMAND_PLACEHOLDER} \"{SESSION_READER_PLACEHOLDER}\" --audit --tail-count 25\n"
            "```\n"
        ),
        encoding="utf-8",
    )

    result = inject_session_reader_path_for_command(
        commands_dir,
        command_markdown="audit-readout.md",
        python_command=sys.executable,
        dry_run=False,
    )
    assert result["status"] == "injected"
    content = cmd.read_text(encoding="utf-8")
    assert SESSION_READER_PLACEHOLDER not in content
    assert PYTHON_COMMAND_PLACEHOLDER not in content
    assert "--audit --tail-count 25" in content
