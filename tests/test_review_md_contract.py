"""Tests for review.md contract and installer path injection.

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from install import (
    BIN_DIR_PLACEHOLDER,
    PYTHON_COMMAND_PLACEHOLDER,
    SESSION_READER_PLACEHOLDER,
    inject_session_reader_path_for_command,
)
from tests.util import REPO_ROOT

# Platform-aware python command for legacy inject tests (string substitution only).
_TEST_PYTHON_CMD = sys.executable


@pytest.mark.governance
def test_review_template_contains_required_placeholders_and_contract() -> None:
    review_path = REPO_ROOT / "review.md"
    assert review_path.exists(), "review.md must exist in repo root"
    content = review_path.read_text(encoding="utf-8")

    assert BIN_DIR_PLACEHOLDER in content
    assert "opencode-governance-bootstrap" in content
    assert "--session-reader" in content
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
def test_review_template_bash_code_block_present() -> None:
    """review.md must contain a ```bash code block for _extract_first_step_command()."""
    review_path = REPO_ROOT / "review.md"
    content = review_path.read_text(encoding="utf-8")
    assert "```bash" in content, (
        "review.md must contain a ```bash code block. "
        "This is required by _extract_first_step_command() in E2E tests "
        "and by LLM tool-use parsing."
    )
    assert "```" in content[content.index("```bash") + 7:], (
        "review.md bash code block must be properly closed with ```"
    )


@pytest.mark.governance
def test_review_template_three_tier_fallback() -> None:
    """review.md must contain the three-tier fallback contract."""
    review_path = REPO_ROOT / "review.md"
    content = review_path.read_text(encoding="utf-8")
    content_lower = content.lower()

    assert "preferred" in content_lower, "review.md must use 'Preferred' wording"
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
def test_review_template_minimum_snapshot_fields_documented() -> None:
    """Fallback instructions in review.md must mention the minimum required snapshot fields."""
    review_path = REPO_ROOT / "review.md"
    content = review_path.read_text(encoding="utf-8")
    for field in ("phase", "next", "active_gate", "next_gate_condition"):
        assert field in content, (
            f"review.md fallback must mention required snapshot field '{field}'"
        )


@pytest.mark.governance
def test_review_injection_replaces_bin_dir(tmp_path: Path) -> None:
    """Primary path: BIN_DIR placeholder is replaced with concrete bin dir."""
    commands_dir = tmp_path / "commands"
    commands_dir.mkdir(parents=True)
    review_md = commands_dir / "review.md"
    review_md.write_text(
        (
            "# Governance Review\n"
            "## Resume Session State\n"
            f'PATH="{BIN_DIR_PLACEHOLDER}:$PATH" opencode-governance-bootstrap --session-reader\n'
        ),
        encoding="utf-8",
    )

    concrete_bin = "/opt/governance/bin"
    result = inject_session_reader_path_for_command(
        commands_dir,
        command_markdown="review.md",
        bin_dir=concrete_bin,
        dry_run=False,
    )
    assert result["status"] == "injected"

    content = review_md.read_text(encoding="utf-8")
    assert BIN_DIR_PLACEHOLDER not in content
    assert concrete_bin in content
    assert "opencode-governance-bootstrap --session-reader" in content


@pytest.mark.governance
def test_review_injection_legacy_replaces_placeholders(tmp_path: Path) -> None:
    """Legacy path: PYTHON_COMMAND/SESSION_READER_PATH placeholders still work."""
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
        python_command=_TEST_PYTHON_CMD,
        dry_run=False,
    )
    assert result["status"] == "injected"

    content = review_md.read_text(encoding="utf-8")
    assert SESSION_READER_PLACEHOLDER not in content
    assert PYTHON_COMMAND_PLACEHOLDER not in content
    assert str(commands_dir / "governance" / "entrypoints" / "session_reader.py") in content


# ---------------------------------------------------------------------------
# Rail classification and provenance tests (new)
# ---------------------------------------------------------------------------


@pytest.mark.governance
def test_review_rail_classification_present() -> None:
    """review.md must contain a rail-classification HTML comment."""
    review_path = REPO_ROOT / "review.md"
    content = review_path.read_text(encoding="utf-8")
    assert "<!-- rail-classification:" in content, (
        "review.md must contain a <!-- rail-classification: ... --> HTML comment "
        "that declares the rail's mutation profile for LLM model robustness."
    )


@pytest.mark.governance
def test_review_rail_classification_includes_gate_evaluation() -> None:
    """review.md rail classification must include GATE-EVALUATION."""
    import re
    review_path = REPO_ROOT / "review.md"
    content = review_path.read_text(encoding="utf-8")
    match = re.search(r"<!--\s*rail-classification:\s*([^>]+)-->", content)
    assert match is not None, "review.md must have a rail-classification comment"
    classification = match.group(1)
    assert "GATE-EVALUATION" in classification, (
        "review.md rail classification must include GATE-EVALUATION "
        "(it evaluates review gates)"
    )
    assert "READ-ONLY" in classification, (
        "review.md rail classification must include READ-ONLY "
        "(it does not mutate state)"
    )


@pytest.mark.governance
def test_review_provenance_context_present() -> None:
    """review.md must contain installer provenance context for trust."""
    review_path = REPO_ROOT / "review.md"
    content = review_path.read_text(encoding="utf-8").lower()
    assert "governance installer" in content, (
        "review.md must mention 'governance installer' to establish provenance trust"
    )
    assert "safe to execute" in content, (
        "review.md must state the command is 'safe to execute' for model trust"
    )


@pytest.mark.governance
def test_review_phase4_entrypoint_documented() -> None:
    """review.md must document /review as a read-only rail entrypoint, with gate authority in the kernel."""
    review_path = REPO_ROOT / "review.md"
    content = review_path.read_text(encoding="utf-8")
    assert "Phase 4" in content, (
        "review.md must document that /review surfaces during Phase 4"
    )
    assert "read-only rail entrypoint" in content, (
        "review.md must describe /review as a read-only rail entrypoint"
    )
    content_lower = content.lower()
    assert "authoritative review gate" in content_lower, (
        "review.md must clarify the authoritative review gate is kernel-owned, not the rail itself"
    )
    assert "does not perform implementation" in content_lower, (
        "review.md must state the rail does not perform implementation"
    )


@pytest.mark.governance
def test_review_no_sole_exception_framing() -> None:
    """review.md must NOT contain 'sole exception' framing."""
    review_path = REPO_ROOT / "review.md"
    content = review_path.read_text(encoding="utf-8").lower()
    assert "sole exception" not in content, (
        "review.md must NOT use 'sole exception' framing — "
        "this triggers security-reflex refusals in Claude Opus and similar models"
    )


@pytest.mark.governance
def test_review_no_infer_or_mutate_statement() -> None:
    """review.md must contain the 'Do not infer or mutate' guard."""
    review_path = REPO_ROOT / "review.md"
    content = review_path.read_text(encoding="utf-8").lower()
    assert "do not infer or mutate" in content, (
        "review.md must contain 'Do not infer or mutate any session state' "
        "to prevent models from fabricating state"
    )
