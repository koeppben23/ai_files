"""Defect 5 — Log-routing: workspace-scoped error logs when repo_fingerprint
is known via _ERROR_CONTEXT.

Root cause: ``_candidate_log_paths()`` in ``global_error_handler.py`` previously
had a guard that *ignored* ``_ERROR_CONTEXT["repo_fingerprint"]`` whenever
``commands_home`` or ``workspaces_home`` were explicitly passed.  Since the
structured write path (``write_error_event`` → ``resolve_paths_full``) always
resolves explicit paths, the workspace-scoped log target was never selected.

Test matrix
-----------
Happy   – _ERROR_CONTEXT has fingerprint, explicit paths passed → workspace log
Bad     – _ERROR_CONTEXT has no fingerprint, explicit paths passed → commands/logs
Corner  – explicit repo_fingerprint arg overrides _ERROR_CONTEXT fingerprint
Edge    – _ERROR_CONTEXT has fingerprint but workspaces_home is None → commands/logs
"""
from __future__ import annotations

from pathlib import Path

import pytest

import governance.infrastructure.logging.global_error_handler as geh
from governance.infrastructure.logging.global_error_handler import (
    ErrorContext,
    _candidate_log_paths,
    emit_error_event,
    resolve_log_path,
    set_error_context,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_error_context():
    """Snapshot and restore _ERROR_CONTEXT around every test.

    Uses a *local* copy so that state from earlier tests (or the
    conftest-level ``_isolate_error_context`` fixture) is never
    accidentally persisted across tests via a module-level dict.
    """
    snapshot = geh._ERROR_CONTEXT.copy()
    yield
    geh._ERROR_CONTEXT.clear()
    geh._ERROR_CONTEXT.update(snapshot)


def _set_ctx(*, fp: str | None = None, ws: Path | None = None, cmd: Path | None = None) -> None:
    set_error_context(ErrorContext(
        repo_fingerprint=fp,
        workspaces_home=ws,
        commands_home=cmd,
    ))


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestHappyPath:
    """When _ERROR_CONTEXT has a valid repo_fingerprint and the caller passes
    explicit commands_home/workspaces_home (as resolve_paths_full always does),
    the first candidate must be the workspace-scoped log."""

    def test_context_fingerprint_used_when_paths_explicit(self, tmp_path: Path) -> None:
        fp = "aabbcc112233445566778899"
        ws = tmp_path / "workspaces"
        cmd = tmp_path / "commands"
        _set_ctx(fp=fp, ws=ws, cmd=cmd)

        candidates = _candidate_log_paths(
            commands_home=cmd,
            workspaces_home=ws,
            repo_fingerprint=None,  # caller does NOT pass fp explicitly
        )
        assert len(candidates) == 2
        assert candidates[0] == ws / fp / "logs" / "error.log.jsonl"
        assert candidates[1] == cmd / "logs" / "error.log.jsonl"

    def test_resolve_log_path_returns_workspace_path(self, tmp_path: Path) -> None:
        fp = "aabbcc112233445566778899"
        ws = tmp_path / "workspaces"
        cmd = tmp_path / "commands"
        _set_ctx(fp=fp, ws=ws, cmd=cmd)

        path = resolve_log_path(
            commands_home=cmd,
            workspaces_home=ws,
            repo_fingerprint=None,
        )
        assert path == ws / fp / "logs" / "error.log.jsonl"

    def test_emit_error_event_writes_to_workspace(self, tmp_path: Path) -> None:
        fp = "aabbcc112233445566778899"
        ws = tmp_path / "workspaces"
        cmd = tmp_path / "commands"
        _set_ctx(fp=fp, ws=ws, cmd=cmd)

        ok = emit_error_event(
            severity="HIGH",
            code="TEST-EVENT",
            message="test workspace routing",
            commands_home=cmd,
            workspaces_home=ws,
            repo_fingerprint=None,
        )
        assert ok is True
        ws_log = ws / fp / "logs" / "error.log.jsonl"
        cmd_log = cmd / "logs" / "error.log.jsonl"
        assert ws_log.exists(), "workspace log must be written"
        assert not cmd_log.exists(), "commands/logs must NOT be written when workspace succeeds"


# ---------------------------------------------------------------------------
# Bad path — fingerprint not yet known
# ---------------------------------------------------------------------------

class TestBadPath:
    """When _ERROR_CONTEXT has no fingerprint (e.g. early bootstrap error
    before set_error_context is called), logs must fall back to commands/logs."""

    def test_no_context_fingerprint_falls_back_to_commands(self, tmp_path: Path) -> None:
        ws = tmp_path / "workspaces"
        cmd = tmp_path / "commands"
        # _ERROR_CONTEXT.repo_fingerprint is None (default)

        candidates = _candidate_log_paths(
            commands_home=cmd,
            workspaces_home=ws,
            repo_fingerprint=None,
        )
        assert len(candidates) == 1
        assert candidates[0] == cmd / "logs" / "error.log.jsonl"

    def test_emit_writes_to_commands_when_no_fingerprint(self, tmp_path: Path) -> None:
        ws = tmp_path / "workspaces"
        cmd = tmp_path / "commands"
        # No fingerprint in context

        ok = emit_error_event(
            severity="CRITICAL",
            code="ERR-BOOTSTRAP",
            message="early bootstrap failure",
            commands_home=cmd,
            workspaces_home=ws,
            repo_fingerprint=None,
        )
        assert ok is True
        cmd_log = cmd / "logs" / "error.log.jsonl"
        assert cmd_log.exists()


# ---------------------------------------------------------------------------
# Corner cases
# ---------------------------------------------------------------------------

class TestCornerCases:
    """Explicit repo_fingerprint arg overrides _ERROR_CONTEXT fingerprint;
    context fingerprint used even when only one of commands_home/workspaces_home
    is explicit."""

    def test_explicit_fingerprint_overrides_context(self, tmp_path: Path) -> None:
        """If caller passes repo_fingerprint explicitly, that wins over
        _ERROR_CONTEXT, even if context has a different fingerprint."""
        ctx_fp = "aaaa11112222333344445555"
        arg_fp = "bbbb66667777888899990000"
        ws = tmp_path / "workspaces"
        cmd = tmp_path / "commands"
        _set_ctx(fp=ctx_fp, ws=ws, cmd=cmd)

        candidates = _candidate_log_paths(
            commands_home=cmd,
            workspaces_home=ws,
            repo_fingerprint=arg_fp,
        )
        assert candidates[0] == ws / arg_fp / "logs" / "error.log.jsonl"

    def test_context_fingerprint_used_with_only_commands_home(self, tmp_path: Path) -> None:
        """Even when only commands_home is passed (no workspaces_home), the
        context fingerprint is still resolved — but without ws the workspace
        candidate is skipped, falling back to commands/logs."""
        fp = "aabbcc112233445566778899"
        cmd = tmp_path / "commands"
        _set_ctx(fp=fp, cmd=cmd)

        candidates = _candidate_log_paths(
            commands_home=cmd,
            workspaces_home=None,
            repo_fingerprint=None,
        )
        # fp is set but ws is None → no workspace candidate
        assert len(candidates) == 1
        assert candidates[0] == cmd / "logs" / "error.log.jsonl"

    def test_context_fingerprint_used_with_only_workspaces_home(self, tmp_path: Path) -> None:
        """When only workspaces_home is passed (no commands_home), workspace
        candidate is generated from context fingerprint."""
        fp = "aabbcc112233445566778899"
        ws = tmp_path / "workspaces"
        _set_ctx(fp=fp, ws=ws)

        candidates = _candidate_log_paths(
            commands_home=None,
            workspaces_home=ws,
            repo_fingerprint=None,
        )
        assert len(candidates) == 1
        assert candidates[0] == ws / fp / "logs" / "error.log.jsonl"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Boundary conditions: empty fingerprint string, context has ws but caller
    overrides to None, etc."""

    def test_empty_string_fingerprint_in_context_falls_back(self, tmp_path: Path) -> None:
        """An empty string fingerprint is falsy → should not generate a
        workspace candidate."""
        ws = tmp_path / "workspaces"
        cmd = tmp_path / "commands"
        _set_ctx(fp="", ws=ws, cmd=cmd)

        candidates = _candidate_log_paths(
            commands_home=cmd,
            workspaces_home=ws,
            repo_fingerprint=None,
        )
        # fp is "" which is falsy → workspace candidate skipped
        assert len(candidates) == 1
        assert candidates[0] == cmd / "logs" / "error.log.jsonl"

    def test_context_workspaces_none_but_fingerprint_set(self, tmp_path: Path) -> None:
        """If _ERROR_CONTEXT has fingerprint but workspaces_home is None in
        both context and args, workspace candidate cannot be built."""
        fp = "aabbcc112233445566778899"
        cmd = tmp_path / "commands"
        _set_ctx(fp=fp, cmd=cmd)
        # workspaces_home not set in context, not passed as arg

        candidates = _candidate_log_paths(
            commands_home=cmd,
            workspaces_home=None,
            repo_fingerprint=None,
        )
        assert len(candidates) == 1
        assert candidates[0] == cmd / "logs" / "error.log.jsonl"

    def test_workspace_log_is_first_candidate_commands_is_fallback(self, tmp_path: Path) -> None:
        """Verify ordering: workspace is candidates[0], commands is candidates[1]."""
        fp = "aabbcc112233445566778899"
        ws = tmp_path / "workspaces"
        cmd = tmp_path / "commands"
        _set_ctx(fp=fp, ws=ws, cmd=cmd)

        candidates = _candidate_log_paths(
            commands_home=cmd,
            workspaces_home=ws,
            repo_fingerprint=None,
        )
        assert len(candidates) == 2
        assert "workspaces" in str(candidates[0])
        assert "commands" in str(candidates[1])

    def test_no_paths_at_all_raises(self) -> None:
        """With no paths available at all, resolve_log_path must raise."""
        # Clear context
        geh._ERROR_CONTEXT.update({
            "repo_fingerprint": None,
            "commands_home": None,
            "workspaces_home": None,
        })
        with pytest.raises(RuntimeError, match="no writable error log target"):
            resolve_log_path(
                commands_home=None,
                workspaces_home=None,
                repo_fingerprint=None,
            )
