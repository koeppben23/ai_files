"""Tests for continue.md contract — template placeholder and installed path injection.

Validates:
- Source template contains {{SESSION_READER_PATH}} placeholder
- Source template contains Resume Session State section with three-tier fallback
- inject_session_reader_path() replaces placeholder with concrete path
- Injected path points to governance/entrypoints/session_reader.py
- Dry-run mode does not modify the file
- Missing continue.md is handled gracefully
- Already-injected file (no placeholder) is skipped
- Fallback tiers (preferred command, user-paste, proceed without) are present

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import re

import pytest

from install import (
    PYTHON_COMMAND_PLACEHOLDER,
    SESSION_READER_PLACEHOLDER,
    inject_session_reader_path,
)
from tests.util import REPO_ROOT

# Platform-aware python command for inject tests.  These tests do string
# substitution only (no execution), but using sys.executable avoids confusion
# when reading test output on Windows where ``python3`` does not exist.
_TEST_PYTHON_CMD = sys.executable


# ---------------------------------------------------------------------------
# Source template contract tests
# ---------------------------------------------------------------------------

class TestSourceTemplate:
    """Tests against the actual continue.md in the repo."""

    @pytest.fixture(autouse=True)
    def _load_source(self) -> None:
        self.source_path = REPO_ROOT / "continue.md"
        assert self.source_path.exists(), "continue.md must exist in repo root"
        self.content = self.source_path.read_text(encoding="utf-8")

    def test_placeholder_present(self) -> None:
        """Source template must contain placeholders for python and session reader path."""
        assert SESSION_READER_PLACEHOLDER in self.content, (
            f"continue.md must contain '{SESSION_READER_PLACEHOLDER}' placeholder. "
            "This is replaced at install time with the concrete path."
        )
        assert PYTHON_COMMAND_PLACEHOLDER in self.content, (
            f"continue.md must contain '{PYTHON_COMMAND_PLACEHOLDER}' placeholder. "
            "This is replaced at install time with the bound python command."
        )

    def test_resume_session_state_present(self) -> None:
        """Source template must contain the Resume Session State section."""
        assert "Resume Session State" in self.content, (
            "continue.md must contain a 'Resume Session State' section. "
            "This instructs the LLM to load session state before responding."
        )

    def test_governance_kernel_bridge_comment(self) -> None:
        """Source template must contain the installer-provenance bridge comment."""
        assert "governance installer" in self.content.lower(), (
            "continue.md must document that the kernel bridge command was "
            "placed by the governance installer and is safe to execute."
        )

    def test_python_invocation(self) -> None:
        """Source template must invoke the reader through the bound python placeholder."""
        assert f"{PYTHON_COMMAND_PLACEHOLDER} \"" in self.content or PYTHON_COMMAND_PLACEHOLDER in self.content, (
            "continue.md must invoke session_reader.py via the bound python placeholder"
        )

    def test_fallback_instructions_present(self) -> None:
        """Source template must contain fallback paths for environments that cannot execute commands."""
        assert "command cannot be executed" in self.content.lower(), (
            "continue.md must contain a fallback instruction for when the command cannot be executed"
        )
        assert "no snapshot is available" in self.content.lower(), (
            "continue.md must contain a fallback instruction for when no snapshot is available"
        )

    def test_no_hard_stop_semantics(self) -> None:
        """Source template must not contain hard-stop wording that causes model refusals."""
        content_lower = self.content.lower()
        assert "mandatory first step" not in content_lower, (
            "continue.md must not use 'MANDATORY FIRST STEP' — this triggers model refusals"
        )
        assert not ("report" in content_lower and "error" in content_lower and "stop" in content_lower), (
            "continue.md must not use 'report the error verbatim and stop' — this creates dead-end paths"
        )

    def test_preferred_command_wording(self) -> None:
        """Source template must use 'Preferred' wording for the command execution tier."""
        assert "preferred" in self.content.lower(), (
            "continue.md must use 'Preferred' wording to frame command execution as the ideal path"
        )

    def test_minimum_snapshot_fields_documented(self) -> None:
        """Fallback instructions must mention the minimum required snapshot fields."""
        for field in ("phase", "next", "active_gate", "next_gate_condition"):
            assert field in self.content, (
                f"continue.md fallback must mention required snapshot field '{field}'"
            )

    def test_bash_code_block_present(self) -> None:
        """Source template must contain a ```bash code block for _extract_first_step_command()."""
        assert "```bash" in self.content, (
            "continue.md must contain a ```bash code block. "
            "This is required by _extract_first_step_command() in E2E tests "
            "and by LLM tool-use parsing."
        )
        assert "```" in self.content[self.content.index("```bash") + 7:], (
            "continue.md bash code block must be properly closed with ```"
        )

    def test_three_tier_fallback_ordering(self) -> None:
        """The three tiers must appear in order: preferred command, user paste, proceed without."""
        preferred_pos = self.content.lower().find("preferred")
        paste_pos = self.content.lower().find("command cannot be executed")
        proceed_pos = self.content.lower().find("no snapshot is available")
        assert preferred_pos < paste_pos < proceed_pos, (
            "continue.md must present the three fallback tiers in order: "
            "preferred command, user paste, proceed without"
        )

    def test_rail_classification_present(self) -> None:
        """Source template must contain a rail-classification HTML comment."""
        assert "<!-- rail-classification:" in self.content, (
            "continue.md must contain a <!-- rail-classification: ... --> HTML comment "
            "that declares the rail's mutation profile for LLM model robustness."
        )

    def test_rail_classification_read_only(self) -> None:
        """continue.md rail classification must include READ-ONLY."""
        match = re.search(r"<!--\s*rail-classification:\s*([^>]+)-->", self.content)
        assert match is not None, "continue.md must have a rail-classification comment"
        classification = match.group(1)
        assert "READ-ONLY" in classification, (
            "continue.md rail classification must include READ-ONLY"
        )

    def test_provenance_context_present(self) -> None:
        """Source template must contain installer provenance context for trust."""
        content_lower = self.content.lower()
        assert "governance installer" in content_lower, (
            "continue.md must mention 'governance installer' to establish provenance trust"
        )
        assert "safe to execute" in content_lower, (
            "continue.md must state the command is 'safe to execute' for model trust"
        )

    def test_safe_to_execute_statement(self) -> None:
        """Source template must contain an explicit safe-to-execute statement."""
        assert "safe to execute" in self.content.lower(), (
            "continue.md must contain 'safe to execute' to prevent model refusals"
        )

    def test_no_sole_exception_framing(self) -> None:
        """Source template must NOT contain 'sole exception' framing that triggers security reflexes."""
        assert "sole exception" not in self.content.lower(), (
            "continue.md must NOT use 'sole exception' framing — "
            "this triggers security-reflex refusals in Claude Opus and similar models"
        )

    def test_fallback_tier_labels(self) -> None:
        """Fallback tiers must be explicitly labeled (Tier A, Tier B, Tier C)."""
        content_lower = self.content.lower()
        assert "tier a" in content_lower, (
            "continue.md must label the preferred command as 'Tier A'"
        )
        assert "tier b" in content_lower, (
            "continue.md must label the paste fallback as 'Tier B'"
        )
        assert "tier c" in content_lower, (
            "continue.md must label the conversation-context fallback as 'Tier C'"
        )

    def test_no_infer_or_mutate_statement(self) -> None:
        """Source template must contain the 'Do not infer or mutate' guard statement."""
        assert "do not infer or mutate" in self.content.lower(), (
            "continue.md must contain 'Do not infer or mutate any session state' "
            "to prevent models from fabricating state"
        )


# ---------------------------------------------------------------------------
# Model-refusal prevention tests
# ---------------------------------------------------------------------------

class TestNoModelRefusalPatterns:
    """Verify both command templates are free of patterns that trigger model refusals.

    These tests scan continue.md and review.md for wording patterns known to
    cause Claude Opus, Codex, and similar models to refuse execution or dead-end
    the conversation.
    """

    # Patterns known to trigger refusals or dead-ends in LLMs
    REFUSAL_PATTERNS: list[tuple[str, str]] = [
        (r"\bMANDATORY\b", "MANDATORY triggers trust-violation refusals in security-conscious models"),
        (r"\breport\b.*\berror\b.*\bstop\b", "'report error and stop' creates dead-end paths with no recovery"),
        (r"\bMUST\s+stop\b", "'MUST stop' is a hard dead-end with no fallback"),
        (r"\bexecute\s+or\s+stop\b", "'execute or stop' binary forces model refusals"),
        (r"\bsole\s+exception\b", "'sole exception' triggers security-reflex refusals in Claude Opus models"),
        (r"\brefuse\s+to\s+execute\b", "'refuse to execute' primes models toward refusal behavior"),
    ]

    TEMPLATES = ("continue.md", "review.md")

    @pytest.fixture(autouse=True)
    def _load_templates(self) -> None:
        self.contents: dict[str, str] = {}
        for name in self.TEMPLATES:
            path = REPO_ROOT / name
            assert path.exists(), f"{name} must exist in repo root"
            self.contents[name] = path.read_text(encoding="utf-8")

    @pytest.mark.parametrize("template_name", TEMPLATES)
    def test_no_refusal_trigger_patterns(self, template_name: str) -> None:
        """Template must not contain any known model-refusal trigger patterns."""
        content = self.contents[template_name]
        for pattern, reason in self.REFUSAL_PATTERNS:
            assert not re.search(pattern, content, re.IGNORECASE), (
                f"{template_name} contains refusal-trigger pattern /{pattern}/: {reason}"
            )

    @pytest.mark.parametrize("template_name", TEMPLATES)
    def test_recovery_path_exists(self, template_name: str) -> None:
        """Template must offer a recovery path for every failure mode."""
        content_lower = self.contents[template_name].lower()
        # Must have at least two fallback tiers beyond the preferred command
        assert "command cannot be executed" in content_lower, (
            f"{template_name} must provide a fallback for command execution failure"
        )
        assert "no snapshot is available" in content_lower, (
            f"{template_name} must provide a fallback for missing snapshot"
        )

    @pytest.mark.parametrize("template_name", TEMPLATES)
    def test_templates_share_identical_fallback_block(self, template_name: str) -> None:
        """Both templates must share identical fallback semantics (same bridge section)."""
        # Extract the bridge section: from the HTML comment to the --- separator
        content = self.contents[template_name]
        bridge_start = content.find("<!-- GOVERNANCE KERNEL BRIDGE")
        bridge_end = content.find("\n---\n", bridge_start) if bridge_start >= 0 else -1
        # If no --- separator, use the end of the Tier C fallback block
        if bridge_end < 0 and bridge_start >= 0:
            bridge_end = content.find("before continuing.", bridge_start)
            if bridge_end >= 0:
                bridge_end = bridge_end + len("before continuing.")
        assert bridge_start >= 0 and bridge_end >= 0, (
            f"{template_name} must contain the kernel bridge section"
        )

    def test_continue_and_review_share_bridge_block(self) -> None:
        """continue.md and review.md must have identical kernel bridge blocks."""
        bridges = {}
        for name in self.TEMPLATES:
            content = self.contents[name]
            bridge_start = content.find("<!-- GOVERNANCE KERNEL BRIDGE")
            # Find the end of the bridge: either --- separator or end of Tier C
            bridge_end = content.find("\n---\n", bridge_start) if bridge_start >= 0 else -1
            if bridge_end < 0 and bridge_start >= 0:
                bridge_end = content.find("before continuing.", bridge_start)
                if bridge_end >= 0:
                    bridge_end = bridge_end + len("before continuing.")
            bridges[name] = content[bridge_start:bridge_end]
        assert bridges["continue.md"] == bridges["review.md"], (
            "continue.md and review.md must share identical kernel bridge sections"
        )


# ---------------------------------------------------------------------------
# inject_session_reader_path() unit tests
# ---------------------------------------------------------------------------

class TestInjectSessionReaderPath:
    @pytest.fixture()
    def commands_dir(self, tmp_path: Path) -> Path:
        """Create a commands directory with a template continue.md."""
        cmd = tmp_path / "commands"
        cmd.mkdir()
        # Also create the governance/entrypoints directory for path construction
        (cmd / "governance" / "entrypoints").mkdir(parents=True)
        return cmd

    def _write_template(self, commands_dir: Path) -> Path:
        """Write a continue.md with the placeholder."""
        continue_md = commands_dir / "continue.md"
        content = (
            "# Governance Continue\n"
            "## Resume Session State\n"
            f'{PYTHON_COMMAND_PLACEHOLDER} "{SESSION_READER_PLACEHOLDER}"\n'
            "Use the YAML output.\n"
        )
        continue_md.write_text(content, encoding="utf-8")
        return continue_md

    def test_replaces_placeholder(self, commands_dir: Path) -> None:
        """Placeholder is replaced with concrete path."""
        self._write_template(commands_dir)
        result = inject_session_reader_path(commands_dir, python_command=_TEST_PYTHON_CMD, dry_run=False)
        assert result["status"] == "injected"

        content = (commands_dir / "continue.md").read_text(encoding="utf-8")
        assert SESSION_READER_PLACEHOLDER not in content
        assert PYTHON_COMMAND_PLACEHOLDER not in content

    def test_injected_path_is_correct(self, commands_dir: Path) -> None:
        """Injected path points to governance/entrypoints/session_reader.py."""
        self._write_template(commands_dir)
        inject_session_reader_path(commands_dir, python_command=_TEST_PYTHON_CMD, dry_run=False)

        content = (commands_dir / "continue.md").read_text(encoding="utf-8")
        expected_path = str(commands_dir / "governance" / "entrypoints" / "session_reader.py")
        assert expected_path in content

    def test_injected_path_is_absolute(self, commands_dir: Path) -> None:
        """Injected path is an absolute path."""
        self._write_template(commands_dir)
        inject_session_reader_path(commands_dir, python_command=_TEST_PYTHON_CMD, dry_run=False)

        content = (commands_dir / "continue.md").read_text(encoding="utf-8")
        # The path should be absolute — starts with / on Unix or drive letter on Windows
        expected_path = str(commands_dir / "governance" / "entrypoints" / "session_reader.py")
        assert os.path.isabs(expected_path)
        assert expected_path in content

    def test_dry_run_no_change(self, commands_dir: Path) -> None:
        """Dry run does not modify the file."""
        continue_md = self._write_template(commands_dir)
        original = continue_md.read_text(encoding="utf-8")

        result = inject_session_reader_path(commands_dir, python_command=_TEST_PYTHON_CMD, dry_run=True)
        assert result["status"] == "planned-inject"
        assert continue_md.read_text(encoding="utf-8") == original

    def test_missing_continue_md(self, commands_dir: Path) -> None:
        """Missing continue.md is handled gracefully."""
        result = inject_session_reader_path(commands_dir, python_command=_TEST_PYTHON_CMD, dry_run=False)
        assert result["status"] == "skipped-missing"

    def test_no_placeholder_skipped(self, commands_dir: Path) -> None:
        """File without placeholder is skipped."""
        continue_md = commands_dir / "continue.md"
        continue_md.write_text("# Already injected\npython /concrete/path\n", encoding="utf-8")

        result = inject_session_reader_path(commands_dir, python_command=_TEST_PYTHON_CMD, dry_run=False)
        assert result["status"] == "skipped-no-placeholder"

    def test_legacy_python_reader_command_is_upgraded(self, commands_dir: Path) -> None:
        continue_md = commands_dir / "continue.md"
        legacy_reader = commands_dir / "governance" / "entrypoints" / "session_reader.py"
        continue_md.write_text(
            f"# Governance Continue\npython \"{legacy_reader}\"\n",
            encoding="utf-8",
        )

        result = inject_session_reader_path(commands_dir, python_command=_TEST_PYTHON_CMD, dry_run=False)
        assert result["status"] == "injected"
        content = continue_md.read_text(encoding="utf-8")
        assert f'{_TEST_PYTHON_CMD}' in content
        assert str(legacy_reader) in content

    def test_preserves_other_content(self, commands_dir: Path) -> None:
        """Other content in continue.md is not altered."""
        self._write_template(commands_dir)
        inject_session_reader_path(commands_dir, python_command=_TEST_PYTHON_CMD, dry_run=False)

        content = (commands_dir / "continue.md").read_text(encoding="utf-8")
        assert "# Governance Continue" in content
        assert "## Resume Session State" in content
        assert "Use the YAML output." in content

    def test_idempotent(self, commands_dir: Path) -> None:
        """Running twice produces the same result (second run is a no-op)."""
        self._write_template(commands_dir)
        inject_session_reader_path(commands_dir, python_command=_TEST_PYTHON_CMD, dry_run=False)
        content_after_first = (commands_dir / "continue.md").read_text(encoding="utf-8")

        result = inject_session_reader_path(commands_dir, python_command=_TEST_PYTHON_CMD, dry_run=False)
        assert result["status"] == "skipped-no-placeholder"
        content_after_second = (commands_dir / "continue.md").read_text(encoding="utf-8")
        assert content_after_first == content_after_second

    def test_injects_bound_python_command(self, commands_dir: Path) -> None:
        self._write_template(commands_dir)
        inject_session_reader_path(commands_dir, python_command="py -3", dry_run=False)
        content = (commands_dir / "continue.md").read_text(encoding="utf-8")
        assert 'py -3 "' in content


# ---------------------------------------------------------------------------
# Python command quoting tests for inject_session_reader_path_for_command
# ---------------------------------------------------------------------------

class TestPythonCommandQuoting:
    """Verify that inject_session_reader_path_for_command quotes python paths correctly.

    The installer must:
    - Quote single-token paths that contain spaces (e.g. Program Files)
    - NOT double-quote already-quoted paths
    - NOT quote paths without spaces
    - NOT quote multi-token commands like 'py -3' as a single unit
    """

    @pytest.fixture()
    def commands_dir(self, tmp_path: Path) -> Path:
        cmd = tmp_path / "commands"
        cmd.mkdir()
        (cmd / "governance" / "entrypoints").mkdir(parents=True)
        return cmd

    def _write_template(self, commands_dir: Path, name: str = "continue.md") -> Path:
        md = commands_dir / name
        md.write_text(
            f'{PYTHON_COMMAND_PLACEHOLDER} "{SESSION_READER_PLACEHOLDER}"\n',
            encoding="utf-8",
        )
        return md

    def test_path_with_spaces_gets_quoted(self, commands_dir: Path) -> None:
        """A single-token path containing spaces must be wrapped in double quotes."""
        self._write_template(commands_dir)
        python_cmd = r"C:\Program Files\Python311\python.exe"
        inject_session_reader_path(commands_dir, python_command=python_cmd, dry_run=False)
        content = (commands_dir / "continue.md").read_text(encoding="utf-8")
        assert f'"{python_cmd}"' in content, (
            "Single-token path with spaces must be quoted"
        )

    def test_already_quoted_path_not_double_quoted(self, commands_dir: Path) -> None:
        """An already-quoted path must not be double-quoted."""
        self._write_template(commands_dir)
        python_cmd = r'"C:\Program Files\Python311\python.exe"'
        inject_session_reader_path(commands_dir, python_command=python_cmd, dry_run=False)
        content = (commands_dir / "continue.md").read_text(encoding="utf-8")
        # Must appear exactly once — no extra layer of quotes
        assert content.count(r'"C:\Program Files\Python311\python.exe"') == 1, (
            "Already-quoted path must not be double-quoted"
        )

    def test_path_without_spaces_not_quoted(self, commands_dir: Path) -> None:
        """A simple path without spaces must NOT be quoted."""
        self._write_template(commands_dir)
        python_cmd = r"C:\Python311\python.exe"
        inject_session_reader_path(commands_dir, python_command=python_cmd, dry_run=False)
        content = (commands_dir / "continue.md").read_text(encoding="utf-8")
        # The python command should appear without wrapping quotes
        assert f'{python_cmd} "' in content, (
            "Path without spaces must not be quoted"
        )
        # Verify it does NOT have an extra layer of quotes
        assert f'"{python_cmd}"' not in content, (
            "Path without spaces must not be wrapped in quotes"
        )

    def test_multi_token_command_not_quoted(self, commands_dir: Path) -> None:
        """A multi-token command like 'py -3' must NOT be quoted as a single unit."""
        self._write_template(commands_dir)
        python_cmd = "py -3"
        inject_session_reader_path(commands_dir, python_command=python_cmd, dry_run=False)
        content = (commands_dir / "continue.md").read_text(encoding="utf-8")
        assert 'py -3 "' in content, (
            "Multi-token command must appear unquoted"
        )
        assert '"py -3"' not in content, (
            "Multi-token command must NOT be quoted as a single unit"
        )
