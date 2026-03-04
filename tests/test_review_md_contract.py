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
    assert "Resume Session State" in content
    assert "lead/staff" in content.lower()
    assert "paste-ready" in content.lower()


@pytest.mark.governance
def test_review_template_no_hard_stop_semantics() -> None:
    """review.md must not contain hard-stop wording that causes model refusals."""
    review_path = REPO_ROOT / "review.md"
    content = review_path.read_text(encoding="utf-8").lower()
    assert "mandatory first step" not in content, (
        "review.md must not use 'MANDATORY FIRST STEP' — this triggers model refusals"
    )
    assert not ("report" in content and "error" in content and "stop" in content), (
        "review.md must not use 'report the error verbatim and stop' — this creates dead-end paths"
    )


@pytest.mark.governance
def test_review_template_three_tier_fallback() -> None:
    """review.md must contain the three-tier fallback contract."""
    review_path = REPO_ROOT / "review.md"
    content = review_path.read_text(encoding="utf-8")
    content_lower = content.lower()

    assert "preferred:" in content_lower, "review.md must use 'Preferred:' wording"
    assert "command cannot be executed" in content_lower, (
        "review.md must contain fallback for command execution failure"
    )
    assert "no snapshot is available" in content_lower, (
        "review.md must contain fallback for missing snapshot"
    )

    # Ordering: preferred < paste < proceed
    preferred_pos = content_lower.find("preferred:")
    paste_pos = content_lower.find("command cannot be executed")
    proceed_pos = content_lower.find("no snapshot is available")
    assert preferred_pos < paste_pos < proceed_pos, (
        "review.md must present the three fallback tiers in order"
    )


@pytest.mark.governance
def test_review_injection_replaces_placeholders(tmp_path: Path) -> None:
    commands_dir = tmp_path / "commands"
    (commands_dir / "governance" / "entrypoints").mkdir(parents=True)
    review_md = commands_dir / "review.md"
    review_md.write_text(
        (
            "# Governance Review\n"
            "## Resume Session State\n"
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
