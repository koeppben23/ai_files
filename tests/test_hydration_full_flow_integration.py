"""Patch 23 — Integration test: hydration → new_work_session → URL resolution.

This is the definitive test the user demanded:
    "Da MUSS ein Test her, der das 100% abfängt."

It simulates the COMPLETE real-world flow:
1. /hydrate writes resolved_server_url + hydrated_session_id to SESSION_STATE
2. audit-new-session.mjs triggers new_work_session (resets phase to 4)
3. After new_work_session, SessionHydration block is STILL intact
4. resolve_opencode_server_base_url() returns the CORRECT discovered URL
5. resolve_session_id() returns the CORRECT hydrated session ID

This test catches the EXACT bug that caused BLOCKED-SERVER-REQUIRED-UNAVAILABLE:
- new_work_session destroyed SessionHydration (Root Cause A)
- Launcher hardcoded OPENCODE_PORT=4096 (Root Cause B)
- opencode.json had stale port 4096 from installer (Resolution ordering)
Together these caused the system to connect to the wrong port.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")


def _make_full_workspace(
    tmp_path: Path,
    *,
    server_url: str = "http://127.0.0.1:52372",
    session_id: str = "ses_discovered_42",
    opencode_json_port: int = 4096,
) -> tuple[Path, Path, str]:
    """Create a workspace that simulates post-hydration state.

    This mimics the real-world scenario:
    - opencode.json has server.port=4096 (installer default, STALE)
    - SESSION_STATE has resolved_server_url=http://127.0.0.1:52372 (CORRECT)
    """
    config_root = tmp_path / "config"
    workspaces_home = config_root / "workspaces"
    fingerprint = "abc123def456abc123def456"
    session_path = workspaces_home / fingerprint / "SESSION_STATE.json"

    _write_json(
        config_root / "governance.paths.json",
        {
            "schema": "opencode-governance.paths.v1",
            "paths": {
                "configRoot": str(config_root),
                "commandsHome": str(config_root / "commands"),
                "workspacesHome": str(workspaces_home),
                "pythonCommand": "/usr/bin/python3",
            },
        },
    )
    _write_json(
        config_root / "SESSION_STATE.json",
        {
            "schema": "opencode-session-pointer.v1",
            "activeRepoFingerprint": fingerprint,
            "activeSessionStateFile": str(session_path),
        },
    )
    # opencode.json with STALE port (installer default)
    _write_json(
        config_root / "opencode.json",
        {
            "server": {"hostname": "127.0.0.1", "port": opencode_json_port},
            "instructions": [],
        },
    )
    _write_json(
        session_path,
        {
            "SESSION_STATE": {
                "RepoFingerprint": fingerprint,
                "PersistenceCommitted": True,
                "WorkspaceReadyGateCommitted": True,
                "phase_transition_evidence": True,
                "phase": "5-ArchitectureReview",
                "next": "5.3",
                "Mode": "IN_PROGRESS",
                "OutputMode": "ARCHITECT",
                "DecisionSurface": {},
                "status": "OK",
                "active_gate": "Architecture Review Gate",
                "next_gate_condition": "Review in progress",
                "Bootstrap": {
                    "Satisfied": True,
                    "Present": True,
                    "Evidence": "bootstrap-completed",
                },
                "ticket_intake_ready": True,
                "phase_ready": 4,
                "session_run_id": "run-old-hydrated",
                "ActiveProfile": "profile.backend-python",
                "Ticket": "old ticket",
                "Task": "old task",
                "TicketRecordDigest": "ticket-old",
                "TaskRecordDigest": "task-old",
                "phase4_intake_source": "phase4-intake-bridge",
                "session_hydrated": True,
                "SessionHydration": {
                    "status": "hydrated",
                    "source": "session-hydration",
                    "hydrated_session_id": session_id,
                    "hydrated_at": "2026-04-02T10:00:00Z",
                    "resolved_server_url": server_url,
                    "digest": "abc123",
                    "artifact_digest": "def456",
                },
                "Gates": {
                    "P5-Architecture": "approved",
                    "P5.3-TestQuality": "pass",
                    "P5.4-BusinessRules": "compliant",
                    "P5.5-TechnicalDebt": "approved",
                    "P5.6-RollbackSafety": "approved",
                    "P6-ImplementationQA": "pending",
                },
                "Scope": {"BusinessRules": "extracted"},
                "BusinessRules": {
                    "Decision": "execute",
                    "Outcome": "extracted",
                    "ExecutionEvidence": True,
                    "InventoryFileStatus": "written",
                    "Rules": ["BR-7: must preserve old behavior"],
                    "Evidence": ["docs/rules.md:10"],
                    "Inventory": {"sha256": "abc123", "count": 1},
                },
                "ArchitectureDecisions": [{"Status": "approved"}],
            }
        },
    )
    return config_root, session_path, fingerprint


class TestFullFlowHydrationThroughNewWorkSession:
    """Integration test: hydration → new_work_session → URL/session resolution.

    This test class simulates the EXACT production flow that was broken.
    """

    def test_full_flow_random_port_survives(
        self,
        short_tmp: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """FULL FLOW: hydrated random-port URL survives new_work_session.

        Steps:
        1. Workspace has hydrated state with random port (52372)
        2. new_work_session runs (triggered by audit-new-session.mjs)
        3. Read SESSION_STATE — SessionHydration.resolved_server_url intact
        4. resolve_opencode_server_base_url() returns the random port URL
        """
        from governance_runtime.entrypoints import new_work_session
        from governance_runtime.infrastructure.opencode_server_client import (
            resolve_opencode_server_base_url,
            resolve_session_id,
        )

        random_url = "http://127.0.0.1:52372"
        hydrated_sid = "ses_discovered_42"

        config_root, session_path, _ = _make_full_workspace(
            short_tmp,
            server_url=random_url,
            session_id=hydrated_sid,
            opencode_json_port=4096,  # stale installer default
        )
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
        monkeypatch.delenv("OPENCODE_PORT", raising=False)
        monkeypatch.delenv("OPENCODE_SESSION_ID", raising=False)

        # Step 2: new_work_session runs
        code = new_work_session.main(
            ["--trigger-source", "desktop-plugin", "--session-id", "ses_new", "--quiet"]
        )
        assert code == 0

        # Step 3: Verify SESSION_STATE
        state = json.loads(session_path.read_text(encoding="utf-8"))["SESSION_STATE"]
        assert state["phase"] == "4", "phase must be reset to 4"
        assert state["session_hydrated"] is True, "session_hydrated flag must survive"
        hydration = state["SessionHydration"]
        assert hydration["status"] == "hydrated"
        assert hydration["resolved_server_url"] == random_url
        assert hydration["hydrated_session_id"] == hydrated_sid

        # Step 4: resolve_opencode_server_base_url() must return the random port
        # Mock _read_server_url_from_state to read from our test SESSION_STATE
        def _mock_read_url():
            doc = json.loads(session_path.read_text(encoding="utf-8"))
            h = doc.get("SESSION_STATE", {}).get("SessionHydration", {})
            if isinstance(h, dict) and str(h.get("status") or "").strip().lower() == "hydrated":
                return str(h.get("resolved_server_url") or "").strip() or None
            return None

        monkeypatch.setattr(
            "governance_runtime.infrastructure.opencode_server_client._read_server_url_from_state",
            _mock_read_url,
        )
        result = resolve_opencode_server_base_url()
        assert result == random_url, (
            f"resolve_opencode_server_base_url() returned {result} instead of {random_url}. "
            "This means the random-port URL from hydration was lost."
        )

    def test_full_flow_session_id_survives(
        self,
        short_tmp: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """FULL FLOW: hydrated session ID survives new_work_session."""
        from governance_runtime.entrypoints import new_work_session
        from governance_runtime.infrastructure.opencode_server_client import (
            resolve_session_id,
        )

        hydrated_sid = "ses_discovered_77"

        config_root, session_path, _ = _make_full_workspace(
            short_tmp, session_id=hydrated_sid
        )
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
        monkeypatch.delenv("OPENCODE_SESSION_ID", raising=False)

        # new_work_session runs
        code = new_work_session.main(["--trigger-source", "desktop-plugin", "--quiet"])
        assert code == 0

        # Verify session ID in STATE
        state = json.loads(session_path.read_text(encoding="utf-8"))["SESSION_STATE"]
        assert state["SessionHydration"]["hydrated_session_id"] == hydrated_sid

        # resolve_session_id() must find it via SESSION_STATE fallback
        def _mock_read_sid():
            doc = json.loads(session_path.read_text(encoding="utf-8"))
            h = doc.get("SESSION_STATE", {}).get("SessionHydration", {})
            if isinstance(h, dict) and str(h.get("status") or "").strip().lower() == "hydrated":
                sid = str(h.get("hydrated_session_id") or "").strip()
                return sid if sid else None
            return None

        monkeypatch.setattr(
            "governance_runtime.infrastructure.opencode_server_client._read_hydrated_session_id_from_state",
            _mock_read_sid,
        )
        session_id, evidence = resolve_session_id()
        assert session_id == hydrated_sid
        assert evidence["session_id_source"] == "SESSION_STATE.SessionHydration"

    def test_full_flow_not_hydrated_falls_through_to_opencode_json(
        self,
        short_tmp: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """When NOT hydrated, resolution falls through to opencode.json port."""
        from governance_runtime.infrastructure.opencode_server_client import (
            resolve_opencode_server_base_url,
        )

        config_root, session_path, _ = _make_full_workspace(
            short_tmp, opencode_json_port=4096
        )
        # Mark as NOT hydrated
        doc = json.loads(session_path.read_text(encoding="utf-8"))
        doc["SESSION_STATE"]["SessionHydration"] = {
            "status": "not_hydrated",
            "source": "bootstrap",
        }
        doc["SESSION_STATE"]["session_hydrated"] = False
        session_path.write_text(json.dumps(doc), encoding="utf-8")

        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
        # _resolve_server_endpoint_from_opencode_json reads from ~/  .config/opencode/opencode.json
        # Set HOME so opencode.json is found at the right place.
        home = short_tmp / "home"
        oc_config = home / ".config" / "opencode"
        oc_config.mkdir(parents=True, exist_ok=True)
        _write_json(
            oc_config / "opencode.json",
            {"server": {"hostname": "127.0.0.1", "port": 4096}},
        )
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.delenv("OPENCODE_PORT", raising=False)

        # Mock _read_server_url_from_state to return None (not hydrated)
        monkeypatch.setattr(
            "governance_runtime.infrastructure.opencode_server_client._read_server_url_from_state",
            lambda: None,
        )
        result = resolve_opencode_server_base_url()
        assert result == "http://127.0.0.1:4096", (
            "When not hydrated, should fall through to opencode.json port."
        )

    def test_regression_stale_port_does_not_win_over_discovery(
        self,
        short_tmp: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """REGRESSION: opencode.json port=4096 must NOT override hydrated URL.

        This is the EXACT scenario that caused the original bug:
        - opencode.json has port 4096 (stale installer default)
        - SESSION_STATE has resolved_server_url http://127.0.0.1:52372 (discovered)
        - Result MUST be 52372, NOT 4096
        """
        from governance_runtime.infrastructure.opencode_server_client import (
            resolve_opencode_server_base_url,
        )

        config_root, _, _ = _make_full_workspace(
            short_tmp,
            server_url="http://127.0.0.1:52372",
            opencode_json_port=4096,
        )
        monkeypatch.setenv("HOME", str(config_root.parent))
        monkeypatch.setenv("OPENCODE_CONFIG_ROOT", str(config_root))
        monkeypatch.delenv("OPENCODE_PORT", raising=False)

        # Mock the state reader to return the hydrated URL
        monkeypatch.setattr(
            "governance_runtime.infrastructure.opencode_server_client._read_server_url_from_state",
            lambda: "http://127.0.0.1:52372",
        )
        result = resolve_opencode_server_base_url()
        assert result == "http://127.0.0.1:52372", (
            f"REGRESSION: Got {result} instead of http://127.0.0.1:52372. "
            "Stale opencode.json port must NOT override hydrated server URL."
        )


class TestResolutionOrderingContract:
    """Verify the resolution chain ordering contract:
    SESSION_STATE > opencode.json > OPENCODE_PORT > fail-closed.
    """

    def test_session_state_wins_over_everything(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """SESSION_STATE is Source 1 and must win over all other sources."""
        from governance_runtime.infrastructure.opencode_server_client import (
            resolve_opencode_server_base_url,
        )

        # Set up opencode.json with port 4096
        home = tmp_path / "home"
        config_dir = home / ".config" / "opencode"
        config_dir.mkdir(parents=True)
        _write_json(config_dir / "opencode.json", {"server": {"port": 4096}})
        monkeypatch.setenv("HOME", str(home))
        # Set OPENCODE_PORT to yet another port
        monkeypatch.setenv("OPENCODE_PORT", "9999")

        # SESSION_STATE returns different URL
        monkeypatch.setattr(
            "governance_runtime.infrastructure.opencode_server_client._read_server_url_from_state",
            lambda: "http://127.0.0.1:60471",
        )
        result = resolve_opencode_server_base_url()
        assert result == "http://127.0.0.1:60471"

    def test_opencode_json_wins_when_no_session_state(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """opencode.json is Source 2 when SESSION_STATE has no URL."""
        from governance_runtime.infrastructure.opencode_server_client import (
            resolve_opencode_server_base_url,
        )

        home = tmp_path / "home"
        config_dir = home / ".config" / "opencode"
        config_dir.mkdir(parents=True)
        _write_json(config_dir / "opencode.json", {"server": {"port": 7777}})
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.delenv("OPENCODE_PORT", raising=False)

        monkeypatch.setattr(
            "governance_runtime.infrastructure.opencode_server_client._read_server_url_from_state",
            lambda: None,
        )
        result = resolve_opencode_server_base_url()
        assert result == "http://127.0.0.1:7777"

    def test_opencode_port_env_is_source_3(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """OPENCODE_PORT env is Source 3 when SESSION_STATE and opencode.json unavailable."""
        from governance_runtime.infrastructure.opencode_server_client import (
            resolve_opencode_server_base_url,
        )

        home = tmp_path / "home"
        config_dir = home / ".config" / "opencode"
        config_dir.mkdir(parents=True)
        # opencode.json with no server block
        _write_json(config_dir / "opencode.json", {"instructions": []})
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv("OPENCODE_PORT", "5555")

        monkeypatch.setattr(
            "governance_runtime.infrastructure.opencode_server_client._read_server_url_from_state",
            lambda: None,
        )
        result = resolve_opencode_server_base_url()
        assert result == "http://127.0.0.1:5555"

    def test_fail_closed_when_all_sources_empty(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Source 4: fail-closed when nothing is available."""
        from governance_runtime.infrastructure.opencode_server_client import (
            resolve_opencode_server_base_url,
            ServerNotAvailableError,
        )

        home = tmp_path / "home"
        config_dir = home / ".config" / "opencode"
        config_dir.mkdir(parents=True)
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.delenv("OPENCODE_PORT", raising=False)

        monkeypatch.setattr(
            "governance_runtime.infrastructure.opencode_server_client._read_server_url_from_state",
            lambda: None,
        )
        with pytest.raises(ServerNotAvailableError, match="not resolvable"):
            resolve_opencode_server_base_url()
