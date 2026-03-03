"""Tests for continue.md contract — template placeholder and installed path injection.

Validates:
- Source template contains {{SESSION_READER_PATH}} placeholder
- Source template contains MANDATORY FIRST STEP section
- inject_session_reader_path() replaces placeholder with concrete path
- Injected path points to governance/entrypoints/session_reader.py
- Dry-run mode does not modify the file
- Missing continue.md is handled gracefully
- Already-injected file (no placeholder) is skipped

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from install import (
    PYTHON_COMMAND_PLACEHOLDER,
    SESSION_READER_PLACEHOLDER,
    inject_session_reader_path,
)
from tests.util import REPO_ROOT


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

    def test_mandatory_first_step_present(self) -> None:
        """Source template must contain the MANDATORY FIRST STEP section."""
        assert "MANDATORY FIRST STEP" in self.content, (
            "continue.md must contain a 'MANDATORY FIRST STEP' section. "
            "This instructs the LLM to invoke session_reader.py before responding."
        )

    def test_governance_kernel_bridge_comment(self) -> None:
        """Source template must contain the sole-exception comment."""
        assert "sole exception" in self.content.lower(), (
            "continue.md must document that the MANDATORY FIRST STEP is the "
            "sole exception to the rails-only constraint."
        )

    def test_python_invocation(self) -> None:
        """Source template must invoke the reader through the bound python placeholder."""
        assert f"{PYTHON_COMMAND_PLACEHOLDER} \"" in self.content or PYTHON_COMMAND_PLACEHOLDER in self.content, (
            "continue.md must invoke session_reader.py via the bound python placeholder"
        )

    def test_error_handling_instruction(self) -> None:
        """Source template must instruct the LLM to handle errors."""
        assert "error" in self.content.lower() and "stop" in self.content.lower(), (
            "continue.md must instruct the LLM to report errors and stop"
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
            "## MANDATORY FIRST STEP\n"
            f'{PYTHON_COMMAND_PLACEHOLDER} "{SESSION_READER_PLACEHOLDER}"\n'
            "Use the YAML output.\n"
        )
        continue_md.write_text(content, encoding="utf-8")
        return continue_md

    def test_replaces_placeholder(self, commands_dir: Path) -> None:
        """Placeholder is replaced with concrete path."""
        self._write_template(commands_dir)
        result = inject_session_reader_path(commands_dir, python_command="python3", dry_run=False)
        assert result["status"] == "injected"

        content = (commands_dir / "continue.md").read_text(encoding="utf-8")
        assert SESSION_READER_PLACEHOLDER not in content
        assert PYTHON_COMMAND_PLACEHOLDER not in content

    def test_injected_path_is_correct(self, commands_dir: Path) -> None:
        """Injected path points to governance/entrypoints/session_reader.py."""
        self._write_template(commands_dir)
        inject_session_reader_path(commands_dir, python_command="python3", dry_run=False)

        content = (commands_dir / "continue.md").read_text(encoding="utf-8")
        expected_path = str(commands_dir / "governance" / "entrypoints" / "session_reader.py")
        assert expected_path in content

    def test_injected_path_is_absolute(self, commands_dir: Path) -> None:
        """Injected path is an absolute path."""
        self._write_template(commands_dir)
        inject_session_reader_path(commands_dir, python_command="python3", dry_run=False)

        content = (commands_dir / "continue.md").read_text(encoding="utf-8")
        # The path should be absolute — starts with / on Unix or drive letter on Windows
        expected_path = str(commands_dir / "governance" / "entrypoints" / "session_reader.py")
        assert os.path.isabs(expected_path)
        assert expected_path in content

    def test_dry_run_no_change(self, commands_dir: Path) -> None:
        """Dry run does not modify the file."""
        continue_md = self._write_template(commands_dir)
        original = continue_md.read_text(encoding="utf-8")

        result = inject_session_reader_path(commands_dir, python_command="python3", dry_run=True)
        assert result["status"] == "planned-inject"
        assert continue_md.read_text(encoding="utf-8") == original

    def test_missing_continue_md(self, commands_dir: Path) -> None:
        """Missing continue.md is handled gracefully."""
        result = inject_session_reader_path(commands_dir, python_command="python3", dry_run=False)
        assert result["status"] == "skipped-missing"

    def test_no_placeholder_skipped(self, commands_dir: Path) -> None:
        """File without placeholder is skipped."""
        continue_md = commands_dir / "continue.md"
        continue_md.write_text("# Already injected\npython /concrete/path\n", encoding="utf-8")

        result = inject_session_reader_path(commands_dir, python_command="python3", dry_run=False)
        assert result["status"] == "skipped-no-placeholder"

    def test_legacy_python_reader_command_is_upgraded(self, commands_dir: Path) -> None:
        continue_md = commands_dir / "continue.md"
        legacy_reader = commands_dir / "governance" / "entrypoints" / "session_reader.py"
        continue_md.write_text(
            f"# Governance Continue\npython \"{legacy_reader}\"\n",
            encoding="utf-8",
        )

        result = inject_session_reader_path(commands_dir, python_command="python3", dry_run=False)
        assert result["status"] == "injected"
        content = continue_md.read_text(encoding="utf-8")
        assert f'python3 "{legacy_reader}"' in content

    def test_preserves_other_content(self, commands_dir: Path) -> None:
        """Other content in continue.md is not altered."""
        self._write_template(commands_dir)
        inject_session_reader_path(commands_dir, python_command="python3", dry_run=False)

        content = (commands_dir / "continue.md").read_text(encoding="utf-8")
        assert "# Governance Continue" in content
        assert "## MANDATORY FIRST STEP" in content
        assert "Use the YAML output." in content

    def test_idempotent(self, commands_dir: Path) -> None:
        """Running twice produces the same result (second run is a no-op)."""
        self._write_template(commands_dir)
        inject_session_reader_path(commands_dir, python_command="python3", dry_run=False)
        content_after_first = (commands_dir / "continue.md").read_text(encoding="utf-8")

        result = inject_session_reader_path(commands_dir, python_command="python3", dry_run=False)
        assert result["status"] == "skipped-no-placeholder"
        content_after_second = (commands_dir / "continue.md").read_text(encoding="utf-8")
        assert content_after_first == content_after_second

    def test_injects_bound_python_command(self, commands_dir: Path) -> None:
        self._write_template(commands_dir)
        inject_session_reader_path(commands_dir, python_command="py -3", dry_run=False)
        content = (commands_dir / "continue.md").read_text(encoding="utf-8")
        assert 'py -3 "' in content
