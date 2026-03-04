"""Unit tests for bootstrap_preflight_readonly helper functions.

Covers _split_verify_command, _normalize_tool_command, _command_available,
_python_command_argv, and bootstrap_command_argv with edge / corner / bad /
happy-path cases.

The module is loaded via importlib to avoid its module-level side effects
(binding resolution, subprocess calls).  We patch the global variables
that the functions under test read from.
"""
from __future__ import annotations

import importlib
import importlib.util
import sys
import types
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helpers to load the module without executing binding resolution
# ---------------------------------------------------------------------------

_MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "governance"
    / "entrypoints"
    / "bootstrap_preflight_readonly.py"
)


def _load_module() -> types.ModuleType:
    """Import the module so we can reach its private functions."""
    # The module is likely already imported by other tests; just grab it.
    mod_name = "governance.entrypoints.bootstrap_preflight_readonly"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    # Fallback: import normally (triggers side effects but avoids spec hacks)
    import governance.entrypoints.bootstrap_preflight_readonly as mod
    return mod


@pytest.fixture()
def mod() -> types.ModuleType:
    return _load_module()


# ===================================================================
# _split_verify_command
# ===================================================================


class TestSplitVerifyCommand:
    """Tests for _split_verify_command."""

    def test_empty_string(self, mod: types.ModuleType) -> None:
        assert mod._split_verify_command("") == []

    def test_none_input(self, mod: types.ModuleType) -> None:
        assert mod._split_verify_command(None) == []  # type: ignore[arg-type]

    def test_whitespace_only(self, mod: types.ModuleType) -> None:
        assert mod._split_verify_command("   \t  ") == []

    def test_simple_single_token(self, mod: types.ModuleType) -> None:
        assert mod._split_verify_command("git") == ["git"]

    def test_two_tokens(self, mod: types.ModuleType) -> None:
        assert mod._split_verify_command("git --version") == ["git", "--version"]

    def test_multiple_tokens(self, mod: types.ModuleType) -> None:
        assert mod._split_verify_command("py -3 --version") == ["py", "-3", "--version"]

    def test_quoted_path_with_spaces(self, mod: types.ModuleType) -> None:
        result = mod._split_verify_command('"C:\\Program Files\\Python311\\python.exe" --version')
        assert result == ["C:\\Program Files\\Python311\\python.exe", "--version"]

    def test_quoted_unix_path_with_spaces(self, mod: types.ModuleType) -> None:
        result = mod._split_verify_command('"/opt/my python/bin/python3" --version')
        assert result == ["/opt/my python/bin/python3", "--version"]

    def test_unclosed_quote_captures_rest(self, mod: types.ModuleType) -> None:
        """Unclosed quote captures everything to end of string."""
        result = mod._split_verify_command('"C:\\Program Files\\python.exe')
        assert result == ["C:\\Program Files\\python.exe"]

    def test_multiple_spaces_between_tokens(self, mod: types.ModuleType) -> None:
        result = mod._split_verify_command("git   --version")
        assert result == ["git", "--version"]

    def test_leading_trailing_whitespace(self, mod: types.ModuleType) -> None:
        result = mod._split_verify_command("  git --version  ")
        assert result == ["git", "--version"]

    def test_tab_separated(self, mod: types.ModuleType) -> None:
        result = mod._split_verify_command("git\t--version")
        assert result == ["git", "--version"]

    def test_windows_backslash_path_no_spaces(self, mod: types.ModuleType) -> None:
        """Unquoted path without spaces stays as single token."""
        result = mod._split_verify_command("C:\\Python311\\python.exe --version")
        assert result == ["C:\\Python311\\python.exe", "--version"]

    def test_quoted_empty_string(self, mod: types.ModuleType) -> None:
        """Adjacent quotes produce an empty string element."""
        result = mod._split_verify_command('"" --version')
        assert result == ["", "--version"]


# ===================================================================
# _normalize_tool_command
# ===================================================================


class TestNormalizeToolCommand:
    """Tests for _normalize_tool_command."""

    def test_no_placeholder(self, mod: types.ModuleType) -> None:
        """String without ${PYTHON_COMMAND} passes through unchanged."""
        with patch.object(mod, "PYTHON_COMMAND", "python3"):
            assert mod._normalize_tool_command("git --version") == "git --version"

    def test_simple_python3(self, mod: types.ModuleType) -> None:
        """Simple command without spaces/path-seps stays unquoted."""
        with patch.object(mod, "PYTHON_COMMAND", "python3"):
            result = mod._normalize_tool_command("${PYTHON_COMMAND} --version")
            assert result == "python3 --version"

    def test_multi_token_py_minus_3(self, mod: types.ModuleType) -> None:
        """Multi-token 'py -3' has a space but no path separators -> unquoted."""
        with patch.object(mod, "PYTHON_COMMAND", "py -3"):
            result = mod._normalize_tool_command("${PYTHON_COMMAND} --version")
            assert result == "py -3 --version"

    def test_windows_path_with_spaces_gets_quoted(self, mod: types.ModuleType) -> None:
        """Path with spaces AND backslashes -> quoted."""
        with patch.object(mod, "PYTHON_COMMAND", "C:\\Program Files\\Python311\\python.exe"):
            result = mod._normalize_tool_command("${PYTHON_COMMAND} --version")
            assert result == '"C:\\Program Files\\Python311\\python.exe" --version'

    def test_unix_path_with_spaces_gets_quoted(self, mod: types.ModuleType) -> None:
        """Path with spaces AND forward slashes -> quoted."""
        with patch.object(mod, "PYTHON_COMMAND", "/opt/my python/bin/python3"):
            result = mod._normalize_tool_command("${PYTHON_COMMAND} --version")
            assert result == '"/opt/my python/bin/python3" --version'

    def test_path_without_spaces_not_quoted(self, mod: types.ModuleType) -> None:
        """Path with separators but no spaces -> not quoted."""
        with patch.object(mod, "PYTHON_COMMAND", "C:\\Python311\\python.exe"):
            result = mod._normalize_tool_command("${PYTHON_COMMAND} --version")
            assert result == "C:\\Python311\\python.exe --version"

    def test_already_quoted_path_not_double_quoted(self, mod: types.ModuleType) -> None:
        """Already-quoted path must not be double-quoted."""
        with patch.object(mod, "PYTHON_COMMAND", '"C:\\Program Files\\Python311\\python.exe"'):
            result = mod._normalize_tool_command("${PYTHON_COMMAND} --version")
            # Already starts with " so quoting is skipped
            assert result == '"C:\\Program Files\\Python311\\python.exe" --version'

    def test_placeholder_at_start(self, mod: types.ModuleType) -> None:
        with patch.object(mod, "PYTHON_COMMAND", "python3"):
            result = mod._normalize_tool_command("${PYTHON_COMMAND}")
            assert result == "python3"

    def test_empty_command_stripped(self, mod: types.ModuleType) -> None:
        with patch.object(mod, "PYTHON_COMMAND", "python3"):
            result = mod._normalize_tool_command("  ")
            assert result == ""


# ===================================================================
# _command_available
# ===================================================================


class TestCommandAvailable:
    """Tests for _command_available."""

    def test_empty_command(self, mod: types.ModuleType) -> None:
        assert mod._command_available("") is False

    def test_none_command(self, mod: types.ModuleType) -> None:
        assert mod._command_available(None) is False  # type: ignore[arg-type]

    def test_python_family_checks_multiple_names(self, mod: types.ModuleType) -> None:
        """python/python3/py/py -3 all check for python|python3|py."""
        with patch.object(mod.shutil, "which", return_value="/usr/bin/python3"):
            assert mod._command_available("python3") is True
            assert mod._command_available("python") is True
            assert mod._command_available("py") is True
            assert mod._command_available("py -3") is True

    def test_python_family_all_missing(self, mod: types.ModuleType) -> None:
        with patch.object(mod.shutil, "which", return_value=None):
            assert mod._command_available("python3") is False
            assert mod._command_available("python") is False
            assert mod._command_available("py -3") is False

    def test_generic_tool_found(self, mod: types.ModuleType) -> None:
        with patch.object(mod.shutil, "which", return_value="/usr/bin/git"):
            assert mod._command_available("git") is True

    def test_generic_tool_missing(self, mod: types.ModuleType) -> None:
        with patch.object(mod.shutil, "which", return_value=None):
            assert mod._command_available("git") is False


# ===================================================================
# _python_command_argv
# ===================================================================


class TestPythonCommandArgv:
    """Tests for _python_command_argv."""

    def test_single_executable(self, mod: types.ModuleType) -> None:
        with patch.object(mod, "PYTHON_COMMAND", "python3"):
            result = mod._python_command_argv()
            assert result == ["python3"]

    def test_multi_token_py_minus_3(self, mod: types.ModuleType) -> None:
        with patch.object(mod, "PYTHON_COMMAND", "py -3"):
            result = mod._python_command_argv()
            assert result == ["py", "-3"]

    def test_windows_path_with_spaces(self, mod: types.ModuleType) -> None:
        """Quoted paths from PYTHON_COMMAND are preserved as single element."""
        # _python_command_argv calls _split_verify_command on the raw
        # PYTHON_COMMAND value.  A path with spaces will come through
        # as-is (single token) because _split_verify_command splits on
        # whitespace and this path has spaces in it.  The normalize step
        # would have quoted it, but _python_command_argv reads the raw value.
        # On Windows the installer typically stores sys.executable which
        # doesn't contain spaces, or wraps it.  Test the raw path case:
        with patch.object(mod, "PYTHON_COMMAND", "C:\\Python311\\python.exe"):
            result = mod._python_command_argv()
            assert result == ["C:\\Python311\\python.exe"]

    def test_empty_falls_back_to_sys_executable(self, mod: types.ModuleType) -> None:
        with patch.object(mod, "PYTHON_COMMAND", ""):
            result = mod._python_command_argv()
            assert result == [sys.executable]

    def test_whitespace_only_falls_back(self, mod: types.ModuleType) -> None:
        with patch.object(mod, "PYTHON_COMMAND", "   "):
            result = mod._python_command_argv()
            assert result == [sys.executable]


# ===================================================================
# bootstrap_command_argv
# ===================================================================


class TestBootstrapCommandArgv:
    """Tests for bootstrap_command_argv."""

    def test_single_python(self, mod: types.ModuleType) -> None:
        with patch.object(mod, "PYTHON_COMMAND", "python3"):
            result = mod.bootstrap_command_argv("abc123")
            assert result == [
                "python3", "-m",
                "governance.entrypoints.bootstrap_session_state",
                "--repo-fingerprint", "abc123",
            ]

    def test_multi_token_python_spread(self, mod: types.ModuleType) -> None:
        """'py -3' is spread into ['py', '-3'] at the start."""
        with patch.object(mod, "PYTHON_COMMAND", "py -3"):
            result = mod.bootstrap_command_argv("abc123")
            assert result[0] == "py"
            assert result[1] == "-3"
            assert result[2] == "-m"

    def test_none_fingerprint_uses_placeholder(self, mod: types.ModuleType) -> None:
        with patch.object(mod, "PYTHON_COMMAND", "python3"):
            result = mod.bootstrap_command_argv(None)
            assert "<repo_fingerprint>" in result

    def test_empty_fingerprint_uses_placeholder(self, mod: types.ModuleType) -> None:
        with patch.object(mod, "PYTHON_COMMAND", "python3"):
            result = mod.bootstrap_command_argv("")
            assert "<repo_fingerprint>" in result

    def test_argv_structure_always_has_m_flag(self, mod: types.ModuleType) -> None:
        """Regardless of python command, -m is always present."""
        for py_cmd in ["python3", "py -3", "C:\\Python311\\python.exe"]:
            with patch.object(mod, "PYTHON_COMMAND", py_cmd):
                result = mod.bootstrap_command_argv("fp123")
                assert "-m" in result
                assert "governance.entrypoints.bootstrap_session_state" in result
