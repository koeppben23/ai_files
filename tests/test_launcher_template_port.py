"""Patch 23 — Launcher template must NOT hardcode OPENCODE_PORT.

Root Cause B: The installed launcher had
    OPENCODE_PORT="${OPENCODE_PORT:-4096}"
which always set OPENCODE_PORT to 4096 when the user didn't explicitly
provide one.  Since OpenCode Desktop starts on random ports (e.g. 52372),
this caused resolve_opencode_server_base_url() Source 3 to always return
http://127.0.0.1:4096 — the wrong port.

The fix: Only export OPENCODE_PORT if the user has explicitly set it.
The resolution chain (SESSION_STATE > opencode.json > OPENCODE_PORT > fail)
handles the absent env var correctly via hydration discovery.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from governance_runtime.install.install import (
    _launcher_template_unix,
    _launcher_template_windows,
)


class TestLauncherTemplateUnix:
    """Unix launcher must not hardcode OPENCODE_PORT."""

    def _render(self, **kwargs) -> str:
        defaults = {
            "python_exe": "/usr/bin/python3",
            "config_root": Path("/home/test/.config/opencode"),
            "local_root": Path("/home/test/.local/share/opencode"),
        }
        defaults.update(kwargs)
        return _launcher_template_unix(**defaults)

    def test_no_hardcoded_port_default(self):
        """CRITICAL: Launcher must NOT contain OPENCODE_PORT=4096 default."""
        script = self._render()
        # Must NOT set a default port value
        assert ':-4096' not in script, (
            "Launcher hardcodes OPENCODE_PORT=4096 default — this breaks "
            "random-port servers (OpenCode Desktop)."
        )
        assert ':-8192' not in script

    def test_no_unconditional_port_export(self):
        """Launcher must NOT unconditionally export OPENCODE_PORT."""
        script = self._render()
        lines = script.splitlines()
        # Find all lines that export OPENCODE_PORT
        export_lines = [l.strip() for l in lines if 'export OPENCODE_PORT' in l]
        # If there are export lines, they must be inside a conditional
        for line in export_lines:
            # Bare 'export OPENCODE_PORT' without a preceding guard is wrong
            assert line != 'export OPENCODE_PORT' or any(
                'if' in lines[max(0, i - 1)] or 'then' in lines[max(0, i - 1)]
                for i, l in enumerate(lines)
                if l.strip() == line
            ), f"Unconditional OPENCODE_PORT export found: {line}"

    def test_conditional_export_present(self):
        """Launcher should only export OPENCODE_PORT when user-set."""
        script = self._render()
        # The pattern: only export if already set
        assert 'if [ -n "${OPENCODE_PORT:-}"' in script or 'OPENCODE_PORT' not in script, (
            "Launcher must conditionally export OPENCODE_PORT or not reference it at all."
        )

    def test_port_param_does_not_appear_in_template(self):
        """Even when opencode_port=9999 is passed, it must NOT appear in the script."""
        script = self._render(opencode_port=9999)
        assert '9999' not in script, (
            "opencode_port parameter value leaked into launcher template."
        )

    def test_standard_subcommands_present(self):
        """Verify core subcommand routing is intact (regression check)."""
        script = self._render()
        for cmd in ("--hydrate", "--plan-persist", "--review-pr", "--verify-contracts"):
            assert cmd in script, f"Subcommand {cmd} missing from launcher"

    def test_python_resolution_intact(self):
        """Python resolution cascade must still work."""
        script = self._render(python_exe="/opt/python/bin/python3")
        assert 'PYTHON_BIN="/opt/python/bin/python3"' in script
        assert 'PYTHON_BINDING' in script


class TestLauncherTemplateWindows:
    """Windows launcher must not hardcode OPENCODE_PORT."""

    def _render(self, **kwargs) -> str:
        defaults = {
            "python_exe": r"C:\Python39\python.exe",
            "config_root": Path(r"C:\Users\test\.config\opencode"),
            "local_root": Path(r"C:\Users\test\.local\share\opencode"),
        }
        defaults.update(kwargs)
        return _launcher_template_windows(**defaults)

    def test_no_hardcoded_port_default(self):
        """CRITICAL: Windows launcher must NOT contain default port assignment."""
        script = self._render()
        # Must NOT have: set "OPENCODE_PORT=4096"
        assert '"OPENCODE_PORT=4096"' not in script, (
            "Windows launcher hardcodes OPENCODE_PORT=4096 default."
        )
        # Must NOT have: set "OPENCODE_PORT=8192"
        assert '"OPENCODE_PORT=8192"' not in script

    def test_no_conditional_port_set(self):
        """Windows launcher must NOT set a default port under any condition."""
        script = self._render()
        # Pattern: "if not defined OPENCODE_PORT ( set "OPENCODE_PORT=...")"
        # This was the old pattern that hardcoded 4096.
        assert not re.search(
            r'if not defined OPENCODE_PORT.*set.*OPENCODE_PORT', script, re.DOTALL
        ), "Windows launcher has conditional default port assignment."

    def test_port_param_does_not_appear_in_template(self):
        """Even when opencode_port=9999 is passed, it must NOT appear in the script."""
        script = self._render(opencode_port=9999)
        assert '9999' not in script, (
            "opencode_port parameter value leaked into Windows launcher template."
        )

    def test_standard_subcommands_present(self):
        """Verify core subcommand routing is intact (regression check)."""
        script = self._render()
        for cmd in ("--hydrate", "--plan-persist", "--review-pr", "--verify-contracts"):
            assert cmd in script, f"Subcommand {cmd} missing from Windows launcher"
