"""Tests for review.md contract and installer path injection.

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from install import (
    PYTHON_COMMAND_PLACEHOLDER,
    SESSION_READER_PLACEHOLDER,
    inject_session_reader_path_for_command,
)
from tests.util import REPO_ROOT


@pytest.mark.governance
def test_review_template_contains_required_placeholders_and_contract() -> None:
    review_path = REPO_ROOT / "review.md"
    assert review_path.exists(), "review.md must exist in repo root"
    content = review_path.read_text(encoding="utf-8")

    assert SESSION_READER_PLACEHOLDER in content
    assert PYTHON_COMMAND_PLACEHOLDER in content
    assert "MANDATORY FIRST STEP" in content
    assert "lead/staff" in content.lower()
    assert "paste-ready" in content.lower()


@pytest.mark.governance
def test_review_injection_replaces_placeholders(tmp_path: Path) -> None:
    commands_dir = tmp_path / "commands"
    (commands_dir / "governance" / "entrypoints").mkdir(parents=True)
    review_md = commands_dir / "review.md"
    review_md.write_text(
        (
            "# Governance Review\n"
            "## MANDATORY FIRST STEP\n"
            f'{PYTHON_COMMAND_PLACEHOLDER} "{SESSION_READER_PLACEHOLDER}"\n'
        ),
        encoding="utf-8",
    )

    result = inject_session_reader_path_for_command(
        commands_dir,
        command_markdown="review.md",
        python_command="python3",
        dry_run=False,
    )
    assert result["status"] == "injected"

    content = review_md.read_text(encoding="utf-8")
    assert SESSION_READER_PLACEHOLDER not in content
    assert PYTHON_COMMAND_PLACEHOLDER not in content
    assert str(commands_dir / "governance" / "entrypoints" / "session_reader.py") in content
