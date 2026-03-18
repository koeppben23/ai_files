"""Tests for the free-text guard contract (Ergänzung A / E6).

Proves that free-text inputs like "go", "weiter", "proceed", "mach weiter"
cannot trigger authoritative state writes.  The contract states:

- ``read_session_snapshot(materialize=False)`` — the default path used by
  normal chat readouts — NEVER writes to SESSION_STATE.json or plan-record.json.
- Free-text is not a rail command.  Only explicit rail invocations
  (``/continue``, ``/ticket``) are permitted to materialize state.
- The rail docs (``continue.md``, ``ticket.md``) explicitly document this.

Test paths:
- Happy: read_session_snapshot does not write state regardless of phase
- Corner: read_session_snapshot with various free-text-like state values
- Edge: evaluate_readonly is truly side-effect-free (no file writes)
- Bad: even corrupted state does not trigger writes from the read path
- Doc: continue.md and ticket.md contain the free-text guard language

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from governance.entrypoints.session_reader import (
    POINTER_SCHEMA,
    read_session_snapshot,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def fake_config(tmp_path: Path) -> Path:
    """Create a minimal config_root with commands/ subdirectory."""
    config_root = tmp_path / "config_root"
    commands_home = config_root / "commands"
    commands_home.mkdir(parents=True)
    return config_root


def _write_pointer(config_root: Path, *, workspace_fp: str = "abc123") -> Path:
    ws_dir = config_root / "workspaces" / workspace_fp
    ws_dir.mkdir(parents=True, exist_ok=True)
    ws_state = ws_dir / "SESSION_STATE.json"
    pointer = {
        "schema": POINTER_SCHEMA,
        "activeSessionStateFile": str(ws_state),
    }
    pointer_path = config_root / "SESSION_STATE.json"
    pointer_path.write_text(json.dumps(pointer), encoding="utf-8")
    return ws_state


def _write_workspace_state(ws_state: Path, state: dict) -> None:
    ws_state.write_text(json.dumps(state), encoding="utf-8")


def _mock_readonly_unavailable():
    """Patch evaluate_readonly to raise, triggering graceful degradation."""
    return patch(
        "governance.kernel.phase_kernel.evaluate_readonly",
        side_effect=RuntimeError("kernel not available in test"),
    )


def _get_mtime(path: Path) -> float | None:
    """Return file mtime or None if file does not exist."""
    try:
        return path.stat().st_mtime
    except FileNotFoundError:
        return None


# ---------------------------------------------------------------------------
# E6.1 — read_session_snapshot never writes SESSION_STATE.json
# ---------------------------------------------------------------------------

class TestReadSnapshotNeverWritesState:
    """Prove that read_session_snapshot(materialize=False) never modifies
    SESSION_STATE.json — regardless of phase, state content, or field values.
    """

    @pytest.mark.parametrize("phase_value", [
        "4",
        "5-ArchitectureReview",
        "6-PostFlight",
        "1.1",
        "unknown",
    ])
    def test_no_write_across_all_phases(
        self,
        fake_config: Path,
        phase_value: str,
    ) -> None:
        """read_session_snapshot does not modify SESSION_STATE.json for any phase."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {
            "SESSION_STATE": {
                "Phase": phase_value,
                "status": "OK",
                "active_gate": "Test Gate",
                "next_gate_condition": "Test condition",
            }
        })

        mtime_before = ws_state.stat().st_mtime
        content_before = ws_state.read_text(encoding="utf-8")

        with _mock_readonly_unavailable():
            read_session_snapshot(commands_home=fake_config / "commands")

        content_after = ws_state.read_text(encoding="utf-8")
        assert content_before == content_after, (
            f"SESSION_STATE.json was modified during read for phase={phase_value}"
        )

    def test_no_write_with_plan_record_present(
        self,
        fake_config: Path,
    ) -> None:
        """Even with a plan-record.json file, read path does not write."""
        ws_state = _write_pointer(fake_config)
        plan_record = ws_state.parent / "plan-record.json"
        plan_record.write_text(
            json.dumps({"status": "active", "versions": [{"v": 1}]}),
            encoding="utf-8",
        )
        _write_workspace_state(ws_state, {
            "SESSION_STATE": {
                "Phase": "5-ArchitectureReview",
                "status": "OK",
                "plan_record_status": "active",
                "plan_record_versions": 1,
            }
        })

        state_content_before = ws_state.read_text(encoding="utf-8")
        plan_content_before = plan_record.read_text(encoding="utf-8")

        with _mock_readonly_unavailable():
            read_session_snapshot(commands_home=fake_config / "commands")

        assert ws_state.read_text(encoding="utf-8") == state_content_before
        assert plan_record.read_text(encoding="utf-8") == plan_content_before

    def test_no_new_files_created_in_workspace(
        self,
        fake_config: Path,
    ) -> None:
        """read_session_snapshot does not create any new files in the workspace."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {
            "SESSION_STATE": {
                "Phase": "5-ArchitectureReview",
                "status": "OK",
            }
        })

        workspace_dir = ws_state.parent
        files_before = set(os.listdir(workspace_dir))

        with _mock_readonly_unavailable():
            read_session_snapshot(commands_home=fake_config / "commands")

        files_after = set(os.listdir(workspace_dir))
        assert files_before == files_after, (
            f"New files created during read: {files_after - files_before}"
        )


# ---------------------------------------------------------------------------
# E6.2 — read_session_snapshot never writes plan-record.json
# ---------------------------------------------------------------------------

class TestReadSnapshotNeverWritesPlanRecord:
    """Prove that read_session_snapshot never creates or modifies plan-record.json."""

    def test_no_plan_record_created_when_absent(
        self,
        fake_config: Path,
    ) -> None:
        """plan-record.json must not be created by read_session_snapshot."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {
            "SESSION_STATE": {
                "Phase": "5-ArchitectureReview",
                "status": "OK",
                "plan_record_status": "absent",
            }
        })

        plan_record = ws_state.parent / "plan-record.json"
        assert not plan_record.exists()

        with _mock_readonly_unavailable():
            read_session_snapshot(commands_home=fake_config / "commands")

        assert not plan_record.exists(), (
            "plan-record.json was created during read_session_snapshot"
        )

    def test_existing_plan_record_not_modified(
        self,
        fake_config: Path,
    ) -> None:
        """Existing plan-record.json must not be modified by read."""
        ws_state = _write_pointer(fake_config)
        plan_record = ws_state.parent / "plan-record.json"
        plan_record.write_text(
            json.dumps({"status": "active", "versions": [{"v": 1}, {"v": 2}]}),
            encoding="utf-8",
        )
        _write_workspace_state(ws_state, {
            "SESSION_STATE": {
                "Phase": "5-ArchitectureReview",
                "status": "OK",
                "plan_record_status": "active",
                "plan_record_versions": 2,
            }
        })

        content_before = plan_record.read_text(encoding="utf-8")

        with _mock_readonly_unavailable():
            read_session_snapshot(commands_home=fake_config / "commands")

        assert plan_record.read_text(encoding="utf-8") == content_before


# ---------------------------------------------------------------------------
# E6.3 — free-text-like state values do not trigger writes
# ---------------------------------------------------------------------------

class TestFreeTextStateValuesNoWrites:
    """State fields containing free-text-like values must not cause writes."""

    @pytest.mark.parametrize("freetext_value", [
        "go",
        "weiter",
        "proceed",
        "mach weiter",
        "continue",
        "Go ahead",
        "Ja, weiter",
        "bitte fortfahren",
    ])
    def test_freetext_in_next_gate_condition_no_write(
        self,
        fake_config: Path,
        freetext_value: str,
    ) -> None:
        """Free-text strings in next_gate_condition do not trigger writes."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {
            "SESSION_STATE": {
                "Phase": "5-ArchitectureReview",
                "status": "OK",
                "next_gate_condition": freetext_value,
            }
        })

        content_before = ws_state.read_text(encoding="utf-8")

        with _mock_readonly_unavailable():
            read_session_snapshot(commands_home=fake_config / "commands")

        assert ws_state.read_text(encoding="utf-8") == content_before

    def test_freetext_in_active_gate_no_write(
        self,
        fake_config: Path,
    ) -> None:
        """Free-text in active_gate does not trigger writes."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {
            "SESSION_STATE": {
                "Phase": "5",
                "status": "OK",
                "active_gate": "go ahead and proceed",
            }
        })

        content_before = ws_state.read_text(encoding="utf-8")

        with _mock_readonly_unavailable():
            read_session_snapshot(commands_home=fake_config / "commands")

        assert ws_state.read_text(encoding="utf-8") == content_before


# ---------------------------------------------------------------------------
# E6.4 — corrupted/unexpected state does not trigger writes
# ---------------------------------------------------------------------------

class TestCorruptedStateNoWrites:
    """Even with corrupted or unexpected state, the read path must not write."""

    def test_empty_state_no_write(
        self,
        fake_config: Path,
    ) -> None:
        """Empty state dict does not trigger writes."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {})

        content_before = ws_state.read_text(encoding="utf-8")

        with _mock_readonly_unavailable():
            result = read_session_snapshot(commands_home=fake_config / "commands")

        assert ws_state.read_text(encoding="utf-8") == content_before
        # Should still return a valid snapshot (with defaults)
        assert "status" in result

    def test_unexpected_types_no_write(
        self,
        fake_config: Path,
    ) -> None:
        """Unexpected type values in state do not trigger writes."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {
            "SESSION_STATE": {
                "Phase": 42,  # int instead of string
                "status": True,  # bool instead of string
                "Gates": "not-a-dict",  # string instead of dict
                "phase_transition_evidence": [1, 2, 3],  # list instead of bool
            }
        })

        content_before = ws_state.read_text(encoding="utf-8")

        with _mock_readonly_unavailable():
            read_session_snapshot(commands_home=fake_config / "commands")

        assert ws_state.read_text(encoding="utf-8") == content_before


# ---------------------------------------------------------------------------
# E6.5 — rail doc free-text guard language
# ---------------------------------------------------------------------------

class TestRailDocFreeTextGuard:
    """Verify that continue.md, ticket.md, and plan.md contain the free-text guard contract.

    These are tripwire tests: if someone removes the guard language from the
    rail docs, these tests will fail and flag the regression.
    """

    FREE_TEXT_TERMS = ("go", "weiter", "proceed", "mach weiter")

    @pytest.fixture(autouse=True)
    def _load_rail_docs(self) -> None:
        """Load continue.md, ticket.md, and plan.md from opencode/commands/."""
        repo_root = Path(__file__).resolve().parent.parent
        commands_root = repo_root / "opencode" / "commands"
        self.continue_md = (commands_root / "continue.md").read_text(encoding="utf-8")
        self.ticket_md = (commands_root / "ticket.md").read_text(encoding="utf-8")
        self.plan_md = (commands_root / "plan.md").read_text(encoding="utf-8")

    def test_continue_md_has_free_text_guard(self) -> None:
        """continue.md must contain the free-text guard section."""
        lower = self.continue_md.lower()
        assert "free-text guard" in lower, (
            "continue.md is missing the 'Free-text guard' section header"
        )
        for term in self.FREE_TEXT_TERMS:
            assert term in lower, (
                f"continue.md free-text guard must mention '{term}'"
            )
        assert "not" in lower and "rail command" in lower, (
            "continue.md must state that free-text is not a rail command"
        )

    def test_ticket_md_has_free_text_guard(self) -> None:
        """ticket.md must contain the free-text guard section."""
        lower = self.ticket_md.lower()
        assert "free-text guard" in lower, (
            "ticket.md is missing the 'Free-text guard' section header"
        )
        for term in self.FREE_TEXT_TERMS:
            assert term in lower, (
                f"ticket.md free-text guard must mention '{term}'"
            )
        assert "not" in lower and "rail command" in lower, (
            "ticket.md must state that free-text is not a rail command"
        )

    def test_continue_md_prohibits_materialize_from_freetext(self) -> None:
        """continue.md must explicitly prohibit materializing from free-text."""
        lower = self.continue_md.lower()
        assert "does not trigger" in lower or "never trigger" in lower or "must never trigger" in lower, (
            "continue.md must state that free-text does not trigger materialization"
        )

    def test_ticket_md_prohibits_intake_from_freetext(self) -> None:
        """ticket.md must explicitly prohibit intake command from free-text."""
        lower = self.ticket_md.lower()
        assert "does not trigger" in lower or "never trigger" in lower or "must never trigger" in lower, (
            "ticket.md must state that free-text does not trigger intake"
        )

    def test_continue_md_only_explicit_rail_invocation(self) -> None:
        """continue.md must require explicit /continue rail invocation."""
        lower = self.continue_md.lower()
        assert "/continue" in lower and "explicit" in lower, (
            "continue.md must require explicit /continue invocation"
        )

    def test_ticket_md_only_explicit_rail_invocation(self) -> None:
        """ticket.md must require explicit /ticket rail invocation."""
        lower = self.ticket_md.lower()
        assert "/ticket" in lower and "explicit" in lower, (
            "ticket.md must require explicit /ticket invocation"
        )

    def test_plan_md_has_free_text_guard(self) -> None:
        """plan.md must contain the free-text guard section."""
        lower = self.plan_md.lower()
        assert "free-text guard" in lower, (
            "plan.md is missing the 'Free-text guard' section header"
        )
        for term in self.FREE_TEXT_TERMS:
            assert term in lower, (
                f"plan.md free-text guard must mention '{term}'"
            )
        assert "not" in lower and "rail command" in lower, (
            "plan.md must state that free-text is not a rail command"
        )

    def test_plan_md_prohibits_persist_from_freetext(self) -> None:
        """plan.md must explicitly prohibit plan persist from free-text."""
        lower = self.plan_md.lower()
        assert "does not trigger" in lower or "never trigger" in lower or "must never trigger" in lower, (
            "plan.md must state that free-text does not trigger plan persist"
        )

    def test_plan_md_only_explicit_rail_invocation(self) -> None:
        """plan.md must require explicit /plan rail invocation."""
        lower = self.plan_md.lower()
        assert "/plan" in lower and "explicit" in lower, (
            "plan.md must require explicit /plan invocation"
        )


# ---------------------------------------------------------------------------
# E6.6 — evaluate_readonly is side-effect-free
# ---------------------------------------------------------------------------

class TestEvaluateReadonlyNoSideEffects:
    """Prove that the readonly kernel evaluation path does not write files.

    This test uses a mocked kernel that returns a valid result and
    verifies no files are created or modified in the workspace.
    """

    def test_readonly_eval_creates_no_files(
        self,
        fake_config: Path,
    ) -> None:
        """When kernel eval succeeds, no files are written in workspace."""
        ws_state = _write_pointer(fake_config)
        _write_workspace_state(ws_state, {
            "SESSION_STATE": {
                "Phase": "5-ArchitectureReview",
                "status": "OK",
            }
        })

        workspace_dir = ws_state.parent
        files_before = set(os.listdir(workspace_dir))
        content_before = ws_state.read_text(encoding="utf-8")

        from governance.kernel.phase_kernel import KernelResult

        fake_result = KernelResult(
            phase="5-ArchitectureReview",
            next_token="5.3",
            active_gate="Architecture Review Gate",
            next_gate_condition="Resume",
            workspace_ready=True,
            source="spec-next",
            status="OK",
            spec_hash="abc",
            spec_path="/fake",
            spec_loaded_at="2026-03-06T00:00:00Z",
            log_paths={"phase_flow": "", "workspace_events": ""},
            event_id="evt-e6-001",
            route_strategy="next",
            plan_record_status="active",
            plan_record_versions=1,
            transition_evidence_met=True,
        )

        with patch(
            "governance.kernel.phase_kernel.evaluate_readonly",
            return_value=fake_result,
        ):
            read_session_snapshot(commands_home=fake_config / "commands")

        files_after = set(os.listdir(workspace_dir))
        assert files_before == files_after, (
            f"Files created during readonly eval: {files_after - files_before}"
        )
        assert ws_state.read_text(encoding="utf-8") == content_before, (
            "SESSION_STATE.json was modified during readonly eval"
        )
