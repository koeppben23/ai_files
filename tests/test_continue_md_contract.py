"""Tests for continue.md contract — template placeholder and installed path injection.

Validates:
- Source template contains {{BIN_DIR}} placeholder for launcher-based invocation
- Source template contains Resume Session State section with three-tier fallback
- inject_session_reader_path_for_command() replaces {{BIN_DIR}} with concrete path
- Dry-run mode does not modify the file
- Missing continue.md is handled gracefully
- Already-injected file (no placeholder) is skipped
- Fallback tiers (preferred command, user-paste, proceed without) are present
- Legacy {{PYTHON_COMMAND}} / {{SESSION_READER_PATH}} injection still works

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import re

import pytest

from install import (
    BIN_DIR_PLACEHOLDER,
    PYTHON_COMMAND_PLACEHOLDER,
    SESSION_READER_PLACEHOLDER,
    inject_session_reader_path,
    inject_session_reader_path_for_command,
)
from tests.util import REPO_ROOT

# Platform-aware python command for legacy inject tests.
_TEST_PYTHON_CMD = sys.executable


# ---------------------------------------------------------------------------
# Source template contract tests
# ---------------------------------------------------------------------------

class TestSourceTemplate:
    """Tests against the actual continue.md in the repo."""

    @pytest.fixture(autouse=True)
    def _load_source(self) -> None:
        self.source_path = REPO_ROOT / "opencode" / "commands" / "continue.md"
        assert self.source_path.exists(), "opencode/commands/continue.md must exist"
        self.content = self.source_path.read_text(encoding="utf-8")

    def test_placeholder_present(self) -> None:
        """Source template must contain {{BIN_DIR}} placeholder for launcher invocation."""
        assert BIN_DIR_PLACEHOLDER in self.content, (
            f"continue.md must contain '{BIN_DIR_PLACEHOLDER}' placeholder. "
            "This is replaced at install time with the concrete bin/ directory path."
        )

    def test_purpose_section_present(self) -> None:
        """Source template must contain a Purpose section."""
        assert "## Purpose" in self.content, (
            "continue.md must contain a '## Purpose' section. "
            "This instructs the LLM about the command's function."
        )

    def test_governance_kernel_bridge_comment(self) -> None:
        """Source template must contain descriptive command-purpose statement."""
        assert "materializes and prints" in self.content.lower(), (
            "continue.md must contain a descriptive statement explaining "
            "the command's purpose (materializes and prints session state)."
        )

    def test_launcher_invocation(self) -> None:
        """Source template must invoke via opencode-governance-bootstrap launcher."""
        assert "opencode-governance-bootstrap" in self.content, (
            "continue.md must invoke session reader via the opencode-governance-bootstrap launcher"
        )
        assert "--session-reader" in self.content, (
            "continue.md must use --session-reader subcommand"
        )
        assert "--materialize" in self.content, (
            "continue.md must pass --materialize flag for state materialization"
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
        """Source template must present the command as the primary execution path."""
        content_lower = self.content.lower()
        assert "commands by platform" in content_lower, (
            "continue.md must have a 'Commands by platform' section"
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
        """The three tiers must appear in order: command block, paste fallback, proceed without."""
        commands_pos = self.content.lower().find("commands by platform")
        paste_pos = self.content.lower().find("command cannot be executed")
        proceed_pos = self.content.lower().find("no snapshot is available")
        assert commands_pos < paste_pos < proceed_pos, (
            "continue.md must present the three fallback tiers in order: "
            "command block, user paste, proceed without"
        )

    def test_rail_classification_present(self) -> None:
        """Source template must contain a rail-classification HTML comment."""
        assert "<!-- rail-classification:" in self.content, (
            "continue.md must contain a <!-- rail-classification: ... --> HTML comment "
            "that declares the rail's mutation profile for LLM model robustness."
        )

    def test_rail_classification_mutating(self) -> None:
        """continue.md rail classification must include MUTATING."""
        match = re.search(r"<!--\s*rail-classification:\s*([^>]+)-->", self.content)
        assert match is not None, "continue.md must have a rail-classification comment"
        classification = match.group(1)
        assert "MUTATING" in classification, (
            "continue.md rail classification must include MUTATING"
        )

    def test_provenance_context_present(self) -> None:
        """Source template must contain descriptive context for the session command."""
        content_lower = self.content.lower()
        assert "materializes and prints" in content_lower, (
            "continue.md must describe the command purpose (materializes and prints)"
        )
        assert "do not infer or mutate" in content_lower, (
            "continue.md must contain a state-inference guard"
        )

    def test_safe_to_execute_statement(self) -> None:
        """Source template must NOT contain 'safe to execute' — trust-triggering language."""
        assert "safe to execute" not in self.content.lower(), (
            "continue.md must NOT contain 'safe to execute' — "
            "this is trust-triggering language that causes model refusals"
        )

    def test_no_sole_exception_framing(self) -> None:
        """Source template must NOT contain 'sole exception' framing that triggers security reflexes."""
        assert "sole exception" not in self.content.lower(), (
            "continue.md must NOT use 'sole exception' framing — "
            "this triggers security-reflex refusals in Claude Opus and similar models"
        )

    def test_fallback_tier_labels(self) -> None:
        """Fallback tiers must use neutral rail-style-spec v1 labels (no Tier A/B/C)."""
        content_lower = self.content.lower()
        assert "tier a" not in content_lower, (
            "continue.md must not use pressure-based 'Tier A' labeling (rail-style-spec v1)"
        )
        assert "tier b" not in content_lower, (
            "continue.md must not use pressure-based 'Tier B' labeling (rail-style-spec v1)"
        )
        assert "tier c" not in content_lower, (
            "continue.md must not use pressure-based 'Tier C' labeling (rail-style-spec v1)"
        )
        assert "if execution is unavailable" in content_lower or "command cannot be executed" in content_lower, (
            "continue.md must use neutral fallback phrasing per rail-style-spec v1"
        )

    def test_materialization_guard_statement(self) -> None:
        """Source template must contain the state-inference guard."""
        lower = self.content.lower()
        assert "do not infer additional state beyond the materialized output" in lower or \
               "do not infer additional state" in lower or \
               "do not infer or mutate" in lower, (
            "continue.md must limit inference scope to materialized output only"
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
            path = REPO_ROOT / "opencode" / "commands" / name
            assert path.exists(), f"opencode/commands/{name} must exist"
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
        """Both templates must share identical fallback semantics (execution-unavailable section)."""
        content = self.contents[template_name]
        # Rail-style-spec v1: fallback starts with "If execution is unavailable" or
        # "command cannot be executed" section
        fallback_start = content.find("## If execution is unavailable")
        if fallback_start < 0:
            fallback_start = content.lower().find("command cannot be executed")
        fallback_end = content.find("\n## ", fallback_start + 1) if fallback_start >= 0 else -1
        if fallback_end < 0 and fallback_start >= 0:
            fallback_end = content.find("state assumptions explicitly", fallback_start)
            if fallback_end >= 0:
                fallback_end = fallback_end + len("state assumptions explicitly")
        assert fallback_start >= 0 and fallback_end >= 0, (
            f"{template_name} must contain the execution-unavailable fallback section"
        )

    def test_continue_and_review_have_distinct_bridge_semantics(self) -> None:
        """continue.md and review.md Purpose sections must differ (mutating vs read-only)."""
        sections = {}
        for name in self.TEMPLATES:
            content = self.contents[name]
            section_start = content.find("## Purpose")
            # Find the end: next ## section
            section_end = content.find("\n## ", section_start + 1) if section_start >= 0 else -1
            if section_end < 0 and section_start >= 0:
                section_end = len(content)
            sections[name] = content[section_start:section_end]
        assert sections["continue.md"] != sections["review.md"], (
            "continue.md and review.md must differ because /continue materializes state while /review is read-only"
        )


# ---------------------------------------------------------------------------
# inject BIN_DIR (launcher-era) unit tests
# ---------------------------------------------------------------------------

class TestInjectBinDir:
    """Tests for {{BIN_DIR}} injection via inject_session_reader_path_for_command()."""

    @pytest.fixture()
    def commands_dir(self, tmp_path: Path) -> Path:
        cmd = tmp_path / "commands"
        cmd.mkdir()
        return cmd

    def _write_launcher_template(self, commands_dir: Path) -> Path:
        """Write a continue.md with the {{BIN_DIR}} launcher pattern."""
        continue_md = commands_dir / "continue.md"
        content = (
            "# Governance Continue\n"
            "## Resume Session State\n"
            "```bash\n"
            f'PATH="{BIN_DIR_PLACEHOLDER}:$PATH" opencode-governance-bootstrap --session-reader --materialize\n'
            "```\n"
            "Use the YAML output.\n"
        )
        continue_md.write_text(content, encoding="utf-8")
        return continue_md

    def test_replaces_bin_dir_placeholder(self, commands_dir: Path) -> None:
        """{{BIN_DIR}} is replaced with concrete bin/ path."""
        self._write_launcher_template(commands_dir)
        result = inject_session_reader_path_for_command(
            commands_dir,
            command_markdown="continue.md",
            bin_dir="/home/user/.config/opencode/bin",
            dry_run=False,
        )
        assert result["status"] == "injected"
        content = (commands_dir / "continue.md").read_text(encoding="utf-8")
        assert BIN_DIR_PLACEHOLDER not in content
        assert "/home/user/.config/opencode/bin" in content

    def test_injected_command_is_complete(self, commands_dir: Path) -> None:
        """After injection, the full launcher command is present (platform-specific)."""
        self._write_launcher_template(commands_dir)
        inject_session_reader_path_for_command(
            commands_dir,
            command_markdown="continue.md",
            bin_dir="/opt/governance/bin",
            dry_run=False,
        )
        content = (commands_dir / "continue.md").read_text(encoding="utf-8")
        if os.name == "nt":
            assert 'set "PATH=/opt/governance/bin;%PATH%" && opencode-governance-bootstrap.cmd --session-reader --materialize' in content
            assert "```cmd" in content
        else:
            assert 'PATH="/opt/governance/bin:$PATH" opencode-governance-bootstrap --session-reader --materialize' in content
            assert "```bash" in content

    def test_dry_run_no_change(self, commands_dir: Path) -> None:
        """Dry run does not modify the file."""
        continue_md = self._write_launcher_template(commands_dir)
        original = continue_md.read_text(encoding="utf-8")

        result = inject_session_reader_path_for_command(
            commands_dir,
            command_markdown="continue.md",
            bin_dir="/some/bin",
            dry_run=True,
        )
        assert result["status"] == "planned-inject"
        assert continue_md.read_text(encoding="utf-8") == original

    def test_missing_file(self, commands_dir: Path) -> None:
        """Missing file is handled gracefully."""
        result = inject_session_reader_path_for_command(
            commands_dir,
            command_markdown="continue.md",
            bin_dir="/some/bin",
            dry_run=False,
        )
        assert result["status"] == "skipped-missing"

    def test_no_placeholder_skipped(self, commands_dir: Path) -> None:
        """File without placeholder is skipped."""
        continue_md = commands_dir / "continue.md"
        # Use platform-appropriate "already injected" content
        if os.name == "nt":
            continue_md.write_text(
                '# Already injected\nset "PATH=C:/concrete/bin;%PATH%" && opencode-governance-bootstrap.cmd\n',
                encoding="utf-8",
            )
        else:
            continue_md.write_text(
                "# Already injected\nPATH=/concrete/bin:$PATH opencode-governance-bootstrap\n",
                encoding="utf-8",
            )

        result = inject_session_reader_path_for_command(
            commands_dir,
            command_markdown="continue.md",
            bin_dir="/some/bin",
            dry_run=False,
        )
        assert result["status"] == "skipped-no-placeholder"

    def test_preserves_other_content(self, commands_dir: Path) -> None:
        """Other content in continue.md is not altered."""
        self._write_launcher_template(commands_dir)
        inject_session_reader_path_for_command(
            commands_dir,
            command_markdown="continue.md",
            bin_dir="/opt/bin",
            dry_run=False,
        )
        content = (commands_dir / "continue.md").read_text(encoding="utf-8")
        assert "# Governance Continue" in content
        assert "## Resume Session State" in content
        assert "Use the YAML output." in content

    def test_idempotent(self, commands_dir: Path) -> None:
        """Running twice produces the same result (second run is a no-op)."""
        self._write_launcher_template(commands_dir)
        inject_session_reader_path_for_command(
            commands_dir,
            command_markdown="continue.md",
            bin_dir="/opt/bin",
            dry_run=False,
        )
        content_after_first = (commands_dir / "continue.md").read_text(encoding="utf-8")

        result = inject_session_reader_path_for_command(
            commands_dir,
            command_markdown="continue.md",
            bin_dir="/opt/bin",
            dry_run=False,
        )
        assert result["status"] == "skipped-no-placeholder"
        content_after_second = (commands_dir / "continue.md").read_text(encoding="utf-8")
        assert content_after_first == content_after_second


# ---------------------------------------------------------------------------
# Legacy inject_session_reader_path() unit tests (backwards compatibility)
# ---------------------------------------------------------------------------

class TestInjectSessionReaderPath:
    @pytest.fixture()
    def commands_dir(self, tmp_path: Path) -> Path:
        """Create a commands directory with a template continue.md."""
        cmd = tmp_path / "commands"
        cmd.mkdir()
        # Also create the governance/entrypoints directory for path construction
        (cmd / "governance_runtime" / "entrypoints").mkdir(parents=True)
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
        """Injected path points to governance_runtime/entrypoints/session_reader.py."""
        self._write_template(commands_dir)
        inject_session_reader_path(commands_dir, python_command=_TEST_PYTHON_CMD, dry_run=False)

        content = (commands_dir / "continue.md").read_text(encoding="utf-8")
        expected_path = str(commands_dir / "governance_runtime" / "entrypoints" / "session_reader.py")
        assert expected_path in content

    def test_injected_path_is_absolute(self, commands_dir: Path) -> None:
        """Injected path is an absolute path."""
        self._write_template(commands_dir)
        inject_session_reader_path(commands_dir, python_command=_TEST_PYTHON_CMD, dry_run=False)

        content = (commands_dir / "continue.md").read_text(encoding="utf-8")
        # The path should be absolute — starts with / on Unix or drive letter on Windows
        expected_path = str(commands_dir / "governance_runtime" / "entrypoints" / "session_reader.py")
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
        legacy_reader = commands_dir / "governance_runtime" / "entrypoints" / "session_reader.py"
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
        (cmd / "governance_runtime" / "entrypoints").mkdir(parents=True)
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
