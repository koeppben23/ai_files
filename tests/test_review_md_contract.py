"""Tests for review.md contract and installer path injection.

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from install import (
    BIN_DIR_PLACEHOLDER,
    PYTHON_COMMAND_PLACEHOLDER,
    SESSION_READER_PLACEHOLDER,
    inject_session_reader_path_for_command,
)
from tests.util import REPO_ROOT, get_phase_api_path, get_master_path, get_review_path

# Platform-aware python command for legacy inject tests (string substitution only).
_TEST_PYTHON_CMD = sys.executable


@pytest.mark.governance
def test_review_template_contains_required_placeholders_and_contract() -> None:
    review_path = get_review_path()
    master_path = get_master_path()
    assert master_path.exists(), "master.md must exist in governed layout"
    assert review_path.exists(), "review.md must exist in command surface"
    content = review_path.read_text(encoding="utf-8")

    assert BIN_DIR_PLACEHOLDER in content
    assert "opencode-governance-bootstrap" in content
    assert "--session-reader" in content
    assert "## Purpose" in content
    # R1 compressed audience labels (lead/staff); verify review-specific content instead
    assert "review" in content.lower()
    assert "paste-ready" in content.lower()
    assert "does not reroute phase state" in content.lower()
    assert "changes_requested" in content


@pytest.mark.governance
def test_phase4_review_reference_is_explicitly_read_only_no_state_change() -> None:
    """phase_api wording for Phase 4 /review must be explicit about no state mutation."""
    phase_api_path = get_phase_api_path()
    assert phase_api_path.exists(), "phase_api.yaml must exist in repo root"
    content = phase_api_path.read_text(encoding="utf-8").lower()
    assert "run /review for read-only feedback with no state change" in content


@pytest.mark.governance
def test_review_template_no_hard_stop_semantics() -> None:
    """review.md must not contain hard-stop wording that causes model refusals."""
    review_path = get_review_path()
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
    review_path = get_review_path()
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
    review_path = get_review_path()
    content = review_path.read_text(encoding="utf-8")
    content_lower = content.lower()

    assert "preferred" in content_lower or "commands by platform" in content_lower, (
        "review.md must have a command section"
    )
    assert "command cannot be executed" in content_lower, (
        "review.md must contain fallback for command execution failure"
    )
    assert "no snapshot is available" in content_lower, (
        "review.md must contain fallback for missing snapshot"
    )

    # Ordering: commands section < paste < proceed
    commands_pos = content_lower.find("commands by platform")
    if commands_pos < 0:
        commands_pos = content_lower.find("preferred:")
    paste_pos = content_lower.find("command cannot be executed")
    proceed_pos = content_lower.find("no snapshot is available")
    assert commands_pos < paste_pos < proceed_pos, (
        "review.md must present the three fallback tiers in order"
    )


@pytest.mark.governance
def test_review_template_minimum_snapshot_fields_documented() -> None:
    """Fallback instructions in review.md must mention the minimum required snapshot fields."""
    review_path = get_review_path()
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
            "```bash\n"
            f'PATH="{BIN_DIR_PLACEHOLDER}:$PATH" opencode-governance-bootstrap --session-reader\n'
            "```\n"
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
    # Bash block is always preserved (OpenCode's LLM tool runner uses bash
    # even on Windows via Git Bash / WSL).
    assert "opencode-governance-bootstrap --session-reader" in content
    assert "```bash" in content
    if os.name == "nt":
        # On Windows a cmd block is appended after the bash block.
        assert "```cmd" in content
        assert "opencode-governance-bootstrap.cmd --session-reader" in content


@pytest.mark.governance
def test_review_injection_legacy_replaces_placeholders(tmp_path: Path) -> None:
    """Legacy path: PYTHON_COMMAND/SESSION_READER_PATH placeholders still work."""
    commands_dir = tmp_path / "commands"
    (commands_dir / "governance_runtime" / "entrypoints").mkdir(parents=True)
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
    assert str(commands_dir / "governance_runtime" / "entrypoints" / "session_reader.py") in content


# ---------------------------------------------------------------------------
# Rail classification and provenance tests (new)
# ---------------------------------------------------------------------------


@pytest.mark.governance
def test_review_rail_classification_present() -> None:
    """review.md must contain a rail-classification HTML comment."""
    review_path = get_review_path()
    content = review_path.read_text(encoding="utf-8")
    assert "<!-- rail-classification:" in content, (
        "review.md must contain a <!-- rail-classification: ... --> HTML comment "
        "that declares the rail's mutation profile for LLM model robustness."
    )


@pytest.mark.governance
def test_review_rail_classification_includes_gate_evaluation() -> None:
    """review.md rail classification must include GATE-EVALUATION."""
    import re
    review_path = get_review_path()
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
    """review.md must contain descriptive context and NOT contain trust-triggering language."""
    review_path = get_review_path()
    content = review_path.read_text(encoding="utf-8").lower()
    assert "read-only rail entrypoint" in content, (
        "review.md must describe the command as a read-only rail entrypoint"
    )
    assert "safe to execute" not in content, (
        "review.md must NOT contain 'safe to execute' — trust-triggering language"
    )
    assert "governance installer" not in content, (
        "review.md must NOT contain 'governance installer' — trust-triggering language"
    )


@pytest.mark.governance
def test_review_phase4_entrypoint_documented() -> None:
    """review.md must document /review as a read-only rail entrypoint, with gate authority in the kernel."""
    review_path = get_review_path()
    content = review_path.read_text(encoding="utf-8")
    assert "Phase 4" in content or "Phase 5" in content or \
           "phase_api.yaml" in content, (
        "review.md must reference phase context (Phase 4/5 or phase_api.yaml)"
    )
    assert "read-only rail entrypoint" in content, (
        "review.md must describe /review as a read-only rail entrypoint"
    )
    content_lower = content.lower()
    assert "review gate" in content_lower, (
        "review.md must clarify the review gate is phase-model-owned, not the rail itself"
    )
    assert "does not perform implementation" in content_lower, (
        "review.md must state the rail does not perform implementation"
    )


@pytest.mark.governance
def test_review_no_sole_exception_framing() -> None:
    """review.md must NOT contain 'sole exception' framing."""
    review_path = get_review_path()
    content = review_path.read_text(encoding="utf-8").lower()
    assert "sole exception" not in content, (
        "review.md must NOT use 'sole exception' framing — "
        "this triggers security-reflex refusals in Claude Opus and similar models"
    )


@pytest.mark.governance
def test_review_no_infer_or_mutate_statement() -> None:
    """review.md must contain the 'Do not infer or mutate' guard."""
    review_path = get_review_path()
    content = review_path.read_text(encoding="utf-8").lower()
    assert "do not infer or mutate" in content, (
        "review.md must contain 'Do not infer or mutate any session state' "
        "to prevent models from fabricating state"
    )


@pytest.mark.governance
def test_review_hydration_soft_guard_is_documented() -> None:
    """review.md must document session_hydrated soft guard and fail-closed behavior."""
    review_path = get_review_path()
    content = review_path.read_text(encoding="utf-8").lower()
    assert "session_hydrated" in content, (
        "review.md must require checking session_hydrated before review execution"
    )
    assert "fail-closed" in content, (
        "review.md must mark hydration prerequisite as fail-closed"
    )


@pytest.mark.governance
def test_review_not_hydrated_recovery_message_is_explicit() -> None:
    """review.md must prescribe blocked recovery to /hydrate when not hydrated."""
    review_path = get_review_path()
    content = review_path.read_text(encoding="utf-8").lower()
    assert "blocked: session-not-hydrated" in content, (
        "review.md must include blocked response for non-hydrated review"
    )
    assert "run /hydrate first" in content, (
        "review.md must direct recovery via /hydrate"
    )
    assert "do no review work" in content, (
        "review.md must explicitly forbid review execution when not hydrated"
    )
