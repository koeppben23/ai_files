"""Tests for Defect 1: Windows rail injection must keep bash block and append cmd block.

On Windows the ``inject_session_reader_path_for_command()`` function previously
replaced the ``bash`` code block with a ``cmd`` block, destroying the bash
invocation that OpenCode's LLM tool runner needs (it uses bash via Git
Bash/WSL even on Windows).

The fix keeps the bash block intact and appends a ``cmd`` block on Windows,
guarded by an idempotency check (``"```cmd" not in content``).

These tests cover Happy / Bad / Corner / Edge scenarios.  They use
``unittest.mock.patch`` to simulate ``os.name`` on both platforms so the
full matrix is exercised regardless of the CI host OS.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from install import (
    BIN_DIR_PLACEHOLDER,
    inject_session_reader_path_for_command,
)


def _plain_write_text(path: Path, text: str, **_kwargs) -> int:
    """Fallback for atomic_write_text when os.name is mocked to 'nt' on POSIX.

    ``atomic_write_text`` internally creates new ``Path`` objects which fails
    on Python 3.9 when ``os.name`` is spoofed to ``"nt"`` on a POSIX host
    (``WindowsPath`` cannot be instantiated).  This shim writes via the
    already-instantiated *path* object, which is safe.
    """
    path.write_text(text, encoding="utf-8")
    return 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _launcher_template(*, bin_dir_placeholder: str = BIN_DIR_PLACEHOLDER) -> str:
    """Return a continue.md template matching the real source layout."""
    return (
        "# Governance Continue\n"
        "\n"
        "## Commands by platform\n"
        "\n"
        "```bash\n"
        f'PATH="{bin_dir_placeholder}:$PATH" opencode-governance-bootstrap --session-reader --materialize\n'
        "```\n"
        "\n"
        "```powershell\n"
        f'$env:Path = "{bin_dir_placeholder};" + $env:Path; opencode-governance-bootstrap --session-reader --materialize\n'
        "```\n"
    )


def _write_template(commands_dir: Path, content: str | None = None) -> Path:
    md = commands_dir / "continue.md"
    md.write_text(content or _launcher_template(), encoding="utf-8")
    return md


def _read(commands_dir: Path) -> str:
    return (commands_dir / "continue.md").read_text(encoding="utf-8")


_BIN = "C:/Users/test/.config/opencode/bin"


# ---------------------------------------------------------------------------
# Happy-path tests
# ---------------------------------------------------------------------------


class TestHappyPathWindows:
    """On Windows (os.name == 'nt'), bash is preserved and cmd is appended."""

    @pytest.fixture(autouse=True)
    def _bypass_atomic_write(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Prevent atomic_write_text from creating Path objects while os.name is spoofed."""
        import governance_runtime.install.install as _inner
        monkeypatch.setattr(_inner, "atomic_write_text", _plain_write_text)

    @pytest.fixture()
    def commands_dir(self, tmp_path: Path) -> Path:
        d = tmp_path / "commands"
        d.mkdir()
        return d

    @patch("install.os.name", "nt")
    def test_bash_block_preserved(self, commands_dir: Path) -> None:
        _write_template(commands_dir)
        inject_session_reader_path_for_command(
            commands_dir, command_markdown="continue.md", bin_dir=_BIN, dry_run=False,
        )
        content = _read(commands_dir)
        assert "```bash" in content
        assert f'PATH="{_BIN}:$PATH" opencode-governance-bootstrap --session-reader --materialize' in content

    @patch("install.os.name", "nt")
    def test_cmd_block_appended(self, commands_dir: Path) -> None:
        _write_template(commands_dir)
        inject_session_reader_path_for_command(
            commands_dir, command_markdown="continue.md", bin_dir=_BIN, dry_run=False,
        )
        content = _read(commands_dir)
        assert "```cmd" in content
        assert f'set "PATH={_BIN};%PATH%" && opencode-governance-bootstrap.cmd --session-reader --materialize' in content

    @patch("install.os.name", "nt")
    def test_powershell_block_preserved(self, commands_dir: Path) -> None:
        _write_template(commands_dir)
        inject_session_reader_path_for_command(
            commands_dir, command_markdown="continue.md", bin_dir=_BIN, dry_run=False,
        )
        content = _read(commands_dir)
        assert "```powershell" in content

    @patch("install.os.name", "nt")
    def test_all_three_blocks_present(self, commands_dir: Path) -> None:
        """After injection on Windows, exactly bash + cmd + powershell blocks exist."""
        _write_template(commands_dir)
        inject_session_reader_path_for_command(
            commands_dir, command_markdown="continue.md", bin_dir=_BIN, dry_run=False,
        )
        content = _read(commands_dir)
        assert content.count("```bash") == 1
        assert content.count("```cmd") == 1
        assert content.count("```powershell") == 1

    @patch("install.os.name", "nt")
    def test_placeholder_fully_replaced(self, commands_dir: Path) -> None:
        _write_template(commands_dir)
        inject_session_reader_path_for_command(
            commands_dir, command_markdown="continue.md", bin_dir=_BIN, dry_run=False,
        )
        content = _read(commands_dir)
        assert BIN_DIR_PLACEHOLDER not in content

    @patch("install.os.name", "nt")
    def test_status_is_injected(self, commands_dir: Path) -> None:
        _write_template(commands_dir)
        result = inject_session_reader_path_for_command(
            commands_dir, command_markdown="continue.md", bin_dir=_BIN, dry_run=False,
        )
        assert result["status"] == "injected"


class TestHappyPathUnix:
    """On non-Windows (os.name != 'nt'), only the bash block is present."""

    @pytest.fixture(autouse=True)
    def _bypass_atomic_write(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Prevent atomic_write_text from creating Path objects while os.name is spoofed."""
        import governance_runtime.install.install as _inner
        monkeypatch.setattr(_inner, "atomic_write_text", _plain_write_text)

    @pytest.fixture()
    def commands_dir(self, tmp_path: Path) -> Path:
        d = tmp_path / "commands"
        d.mkdir()
        return d

    @patch("install.os.name", "posix")
    def test_bash_block_preserved(self, commands_dir: Path) -> None:
        _write_template(commands_dir)
        inject_session_reader_path_for_command(
            commands_dir, command_markdown="continue.md", bin_dir=_BIN, dry_run=False,
        )
        content = _read(commands_dir)
        assert "```bash" in content

    @patch("install.os.name", "posix")
    def test_no_cmd_block_on_unix(self, commands_dir: Path) -> None:
        _write_template(commands_dir)
        inject_session_reader_path_for_command(
            commands_dir, command_markdown="continue.md", bin_dir=_BIN, dry_run=False,
        )
        content = _read(commands_dir)
        assert "```cmd" not in content


# ---------------------------------------------------------------------------
# Bad-path tests
# ---------------------------------------------------------------------------


class TestBadPath:
    """Error and skip conditions."""

    @pytest.fixture(autouse=True)
    def _bypass_atomic_write(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Prevent atomic_write_text from creating Path objects while os.name is spoofed."""
        import governance_runtime.install.install as _inner
        monkeypatch.setattr(_inner, "atomic_write_text", _plain_write_text)

    @pytest.fixture()
    def commands_dir(self, tmp_path: Path) -> Path:
        d = tmp_path / "commands"
        d.mkdir()
        return d

    @patch("install.os.name", "nt")
    def test_missing_file_returns_skipped(self, commands_dir: Path) -> None:
        result = inject_session_reader_path_for_command(
            commands_dir, command_markdown="continue.md", bin_dir=_BIN, dry_run=False,
        )
        assert result["status"] == "skipped-missing"

    @patch("install.os.name", "nt")
    def test_no_placeholder_returns_skipped(self, commands_dir: Path) -> None:
        """File without {{BIN_DIR}} placeholder is skipped."""
        (commands_dir / "continue.md").write_text(
            "# Already injected\nNo placeholders here.\n", encoding="utf-8",
        )
        result = inject_session_reader_path_for_command(
            commands_dir, command_markdown="continue.md", bin_dir=_BIN, dry_run=False,
        )
        assert result["status"] == "skipped-no-placeholder"

    @patch("install.os.name", "nt")
    def test_dry_run_does_not_modify_file(self, commands_dir: Path) -> None:
        md = _write_template(commands_dir)
        original = md.read_text(encoding="utf-8")
        result = inject_session_reader_path_for_command(
            commands_dir, command_markdown="continue.md", bin_dir=_BIN, dry_run=True,
        )
        assert result["status"] == "planned-inject"
        assert md.read_text(encoding="utf-8") == original


# ---------------------------------------------------------------------------
# Corner-case tests
# ---------------------------------------------------------------------------


class TestCornerCases:
    @pytest.fixture(autouse=True)
    def _bypass_atomic_write(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Prevent atomic_write_text from creating Path objects while os.name is spoofed."""
        import governance_runtime.install.install as _inner
        monkeypatch.setattr(_inner, "atomic_write_text", _plain_write_text)

    @pytest.fixture()
    def commands_dir(self, tmp_path: Path) -> Path:
        d = tmp_path / "commands"
        d.mkdir()
        return d

    @patch("install.os.name", "nt")
    def test_idempotent_no_duplicate_cmd(self, commands_dir: Path) -> None:
        """Running twice on Windows must NOT duplicate the cmd block."""
        _write_template(commands_dir)
        inject_session_reader_path_for_command(
            commands_dir, command_markdown="continue.md", bin_dir=_BIN, dry_run=False,
        )
        first_content = _read(commands_dir)

        # Second run — file already has ```cmd, no placeholder left
        result = inject_session_reader_path_for_command(
            commands_dir, command_markdown="continue.md", bin_dir=_BIN, dry_run=False,
        )
        second_content = _read(commands_dir)

        assert result["status"] == "skipped-no-placeholder"
        assert first_content == second_content
        assert second_content.count("```cmd") == 1

    @patch("install.os.name", "nt")
    def test_bin_dir_with_spaces(self, commands_dir: Path) -> None:
        """Paths with spaces (common on Windows) are handled correctly."""
        bin_path = "C:/Program Files/opencode/bin"
        _write_template(commands_dir)
        inject_session_reader_path_for_command(
            commands_dir, command_markdown="continue.md", bin_dir=bin_path, dry_run=False,
        )
        content = _read(commands_dir)
        assert f'set "PATH={bin_path};%PATH%"' in content
        assert f'PATH="{bin_path}:$PATH"' in content

    @patch("install.os.name", "nt")
    def test_template_without_trailing_args(self, commands_dir: Path) -> None:
        """A bash block with no trailing args after the launcher name."""
        template = (
            "# Test\n"
            "```bash\n"
            f'PATH="{BIN_DIR_PLACEHOLDER}:$PATH" opencode-governance-bootstrap\n'
            "```\n"
        )
        _write_template(commands_dir, template)
        inject_session_reader_path_for_command(
            commands_dir, command_markdown="continue.md", bin_dir=_BIN, dry_run=False,
        )
        content = _read(commands_dir)
        assert "```bash" in content
        assert "```cmd" in content
        # cmd block should have the launcher with .cmd extension but no trailing args
        assert f'set "PATH={_BIN};%PATH%" && opencode-governance-bootstrap.cmd\n```' in content

    @patch("install.os.name", "nt")
    def test_preserves_surrounding_content(self, commands_dir: Path) -> None:
        """Non-code-block content is not altered."""
        template = (
            "# Governance Continue\n"
            "\n"
            "Some intro text.\n"
            "\n"
            "```bash\n"
            f'PATH="{BIN_DIR_PLACEHOLDER}:$PATH" opencode-governance-bootstrap --session-reader --materialize\n'
            "```\n"
            "\n"
            "## Interpretation scope\n"
            "\n"
            "Use the YAML output.\n"
        )
        _write_template(commands_dir, template)
        inject_session_reader_path_for_command(
            commands_dir, command_markdown="continue.md", bin_dir=_BIN, dry_run=False,
        )
        content = _read(commands_dir)
        assert "# Governance Continue" in content
        assert "Some intro text." in content
        assert "## Interpretation scope" in content
        assert "Use the YAML output." in content

    @patch("install.os.name", "nt")
    def test_pre_existing_cmd_block_prevents_insertion(self, commands_dir: Path) -> None:
        """If the template already has a ```cmd block (e.g., manually added),
        the idempotency guard prevents adding another one."""
        template = (
            "```bash\n"
            f'PATH="{BIN_DIR_PLACEHOLDER}:$PATH" opencode-governance-bootstrap --session-reader --materialize\n'
            "```\n"
            "\n"
            "```cmd\n"
            f'set "PATH={BIN_DIR_PLACEHOLDER};%PATH%" && opencode-governance-bootstrap.cmd --session-reader --materialize\n'
            "```\n"
        )
        _write_template(commands_dir, template)
        inject_session_reader_path_for_command(
            commands_dir, command_markdown="continue.md", bin_dir=_BIN, dry_run=False,
        )
        content = _read(commands_dir)
        # Exactly one cmd block — the pre-existing one with placeholder replaced
        assert content.count("```cmd") == 1
        assert BIN_DIR_PLACEHOLDER not in content


# ---------------------------------------------------------------------------
# Edge-case tests
# ---------------------------------------------------------------------------


class TestEdgeCases:
    @pytest.fixture(autouse=True)
    def _bypass_atomic_write(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Prevent atomic_write_text from creating Path objects while os.name is spoofed."""
        import governance_runtime.install.install as _inner
        monkeypatch.setattr(_inner, "atomic_write_text", _plain_write_text)

    @pytest.fixture()
    def commands_dir(self, tmp_path: Path) -> Path:
        d = tmp_path / "commands"
        d.mkdir()
        return d

    @patch("install.os.name", "nt")
    def test_cmd_block_ordering(self, commands_dir: Path) -> None:
        """The cmd block must appear between the bash and powershell blocks."""
        _write_template(commands_dir)
        inject_session_reader_path_for_command(
            commands_dir, command_markdown="continue.md", bin_dir=_BIN, dry_run=False,
        )
        content = _read(commands_dir)
        bash_pos = content.index("```bash")
        cmd_pos = content.index("```cmd")
        ps_pos = content.index("```powershell")
        assert bash_pos < cmd_pos < ps_pos

    @patch("install.os.name", "nt")
    def test_different_command_markdowns(self, commands_dir: Path) -> None:
        """The function works for any command_markdown, not just continue.md."""
        md = commands_dir / "review.md"
        md.write_text(_launcher_template(), encoding="utf-8")
        result = inject_session_reader_path_for_command(
            commands_dir, command_markdown="review.md", bin_dir=_BIN, dry_run=False,
        )
        assert result["status"] == "injected"
        content = md.read_text(encoding="utf-8")
        assert "```bash" in content
        assert "```cmd" in content

    @patch("install.os.name", "nt")
    def test_forward_slashes_in_windows_paths(self, commands_dir: Path) -> None:
        """POSIX-style forward slashes work in both bash and cmd blocks."""
        _write_template(commands_dir)
        inject_session_reader_path_for_command(
            commands_dir, command_markdown="continue.md", bin_dir=_BIN, dry_run=False,
        )
        content = _read(commands_dir)
        # Both blocks should reference the same bin dir with forward slashes
        assert f'PATH="{_BIN}:$PATH"' in content
        assert f'set "PATH={_BIN};%PATH%"' in content

    @patch("install.os.name", "posix")
    def test_unix_does_not_add_cmd_even_with_nt_like_path(self, commands_dir: Path) -> None:
        """On Unix, even if the path looks like a Windows path, no cmd block is added."""
        _write_template(commands_dir)
        inject_session_reader_path_for_command(
            commands_dir, command_markdown="continue.md", bin_dir="C:/Users/test/bin", dry_run=False,
        )
        content = _read(commands_dir)
        assert "```cmd" not in content
        assert "```bash" in content

    @patch("install.os.name", "nt")
    def test_bin_dir_none_skips_injection(self, commands_dir: Path) -> None:
        """When bin_dir is None, the BIN_DIR branch is skipped entirely."""
        _write_template(commands_dir)
        result = inject_session_reader_path_for_command(
            commands_dir, command_markdown="continue.md", bin_dir=None, dry_run=False,
        )
        content = _read(commands_dir)
        # Placeholder still present, no cmd block added
        assert BIN_DIR_PLACEHOLDER in content
        assert "```cmd" not in content
        assert result["status"] == "skipped-no-placeholder"
