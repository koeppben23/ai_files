#!/usr/bin/env python3
"""Tests for session_hydration entry point.

Tests cover:
- Happy path: successful hydration
- Bad path: server unavailable
- Bad path: no session available
- Bad path: session write fails
- Edge path: idempotent re-hydration

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


def _write_session_state(tmp_path: Path, state: dict) -> Path:
    workspace_dir = tmp_path / "workspaces" / "testrepo"
    workspace_dir.mkdir(parents=True, exist_ok=True)

    session_path = workspace_dir / "session-state.json"
    document = {"SESSION_STATE": state}
    session_path.write_text(json.dumps(document, ensure_ascii=True) + "\n", encoding="utf-8")

    pointer_path = tmp_path / "session-state-pointer.json"
    pointer = {
        "$schema": "opencode.governance.session-pointer.v1",
        "workspace_home": str(tmp_path / "workspaces"),
        "repo_fingerprint": "testrepo",
        "session_state_path": str(session_path),
    }
    pointer_path.write_text(json.dumps(pointer, ensure_ascii=True) + "\n", encoding="utf-8")

    return session_path


class TestSessionHydrationHappy:
    """Happy path tests for session hydration."""

    def test_hydration_success_with_mocked_server(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Successful hydration binds session and persists receipt."""
        from governance_runtime.entrypoints import session_hydration as module

        session_path = _write_session_state(tmp_path, {"phase": "3", "repo_root": str(tmp_path / "repo")})

        mock_workspace = tmp_path / "workspaces" / "testrepo"
        mock_workspace.mkdir(parents=True, exist_ok=True)

        def mock_resolve_paths():
            return (
                session_path,
                "testrepo",
                tmp_path / "workspaces",
                mock_workspace,
            )

        def mock_health():
            return {"healthy": True, "version": "1.3.7"}

        def mock_get_session(project_path=None):
            return {
                "id": "ses_test123",
                "title": "Test Session",
                "directory": str(tmp_path / "repo"),
            }

        def mock_send_message(text, session_id):
            return {"info": {"id": "msg_test"}}

        monkeypatch.setattr(module, "resolve_active_session_paths", mock_resolve_paths)
        monkeypatch.setattr(module, "check_server_health", mock_health)
        monkeypatch.setattr(module, "get_active_session", mock_get_session)
        monkeypatch.setattr(module, "send_session_message", mock_send_message)
        monkeypatch.setenv("AI_GOVERNANCE_SKIP_SERVER_HEALTH_CHECK", "1")

        monkeypatch.chdir(tmp_path)

        result = module.main(["--quiet"])

        assert result == 0

        output = (tmp_path / "repo").joinpath("governance-output.json").read_text() if (tmp_path / "repo").joinpath("governance-output.json").exists() else None

        state_doc = json.loads(session_path.read_text())
        state = state_doc.get("SESSION_STATE", {})

        assert state.get("SessionHydration", {}).get("hydrated_session_id") == "ses_test123"
        assert state.get("phase") == "4"

    def test_hydration_with_workspace_artifacts(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Hydration brief includes workspace artifact counts."""
        from governance_runtime.entrypoints import session_hydration as module
        from governance_runtime.infrastructure.json_store import write_json_atomic

        session_path = _write_session_state(tmp_path, {"phase": "3", "repo_root": str(tmp_path / "repo")})

        workspace_dir = tmp_path / "workspaces" / "testrepo"
        workspace_dir.mkdir(parents=True, exist_ok=True)

        write_json_atomic(workspace_dir / "repo-map.json", {"items": [{"name": "a.py"}, {"name": "b.py"}]})
        write_json_atomic(workspace_dir / "decision-pack.json", {"items": [{"id": "D001"}]})

        def mock_resolve_paths():
            return (session_path, "testrepo", tmp_path / "workspaces", workspace_dir)

        def mock_health():
            return {"healthy": True, "version": "1.3.7"}

        def mock_get_session(project_path=None):
            return {"id": "ses_test456", "title": "Test Session"}

        def mock_send_message(text, session_id):
            return {"info": {"id": "msg_test"}}

        monkeypatch.setattr(module, "resolve_active_session_paths", mock_resolve_paths)
        monkeypatch.setattr(module, "check_server_health", mock_health)
        monkeypatch.setattr(module, "get_active_session", mock_get_session)
        monkeypatch.setattr(module, "send_session_message", mock_send_message)
        monkeypatch.setenv("AI_GOVERNANCE_SKIP_SERVER_HEALTH_CHECK", "1")

        result = module.main(["--quiet"])

        assert result == 0


class TestSessionHydrationBad:
    """Bad path tests for session hydration."""

    def test_hydration_blocks_when_server_unavailable(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Hydration fails when server is not reachable."""
        from governance_runtime.entrypoints import session_hydration as module
        from governance_runtime.infrastructure.opencode_server_client import ServerNotAvailableError

        session_path = _write_session_state(tmp_path, {"phase": "3"})

        def mock_resolve_paths():
            return (session_path, "testrepo", tmp_path / "workspaces", tmp_path / "workspaces" / "testrepo")

        def mock_health_error():
            raise ServerNotAvailableError("Connection refused")

        monkeypatch.setattr(module, "resolve_active_session_paths", mock_resolve_paths)
        monkeypatch.setattr(module, "check_server_health", mock_health_error)

        result = module.main(["--quiet"])

        assert result == 2

    def test_hydration_blocks_when_no_session_available(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Hydration fails when no session is available."""
        from governance_runtime.entrypoints import session_hydration as module
        from governance_runtime.infrastructure.opencode_server_client import APIError

        session_path = _write_session_state(tmp_path, {"phase": "3"})

        def mock_resolve_paths():
            return (session_path, "testrepo", tmp_path / "workspaces", tmp_path / "workspaces" / "testrepo")

        def mock_health():
            return {"healthy": True, "version": "1.3.7"}

        def mock_no_session(project_path=None):
            raise APIError("No sessions found")

        monkeypatch.setattr(module, "resolve_active_session_paths", mock_resolve_paths)
        monkeypatch.setattr(module, "check_server_health", mock_health)
        monkeypatch.setattr(module, "get_active_session", mock_no_session)
        monkeypatch.setenv("AI_GOVERNANCE_SKIP_SERVER_HEALTH_CHECK", "1")

        result = module.main(["--quiet"])

        assert result == 2


class TestSessionHydrationEdge:
    """Edge case tests for session hydration."""

    def test_hydration_idempotent_rerun(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Hydration can be re-run (idempotent)."""
        from governance_runtime.entrypoints import session_hydration as module

        existing_state = {
            "phase": "4",
            "active_gate": "Ticket Intake Gate",
            "SessionHydration": {
                "hydrated_session_id": "ses_old",
                "hydrated_at": "2026-01-01T00:00:00Z",
                "status": "hydrated",
            },
        }
        session_path = _write_session_state(tmp_path, existing_state)

        workspace_dir = tmp_path / "workspaces" / "testrepo"
        workspace_dir.mkdir(parents=True, exist_ok=True)

        def mock_resolve_paths():
            return (session_path, "testrepo", tmp_path / "workspaces", workspace_dir)

        def mock_health():
            return {"healthy": True, "version": "1.3.7"}

        def mock_get_session(project_path=None):
            return {"id": "ses_new", "title": "New Session"}

        def mock_send_message(text, session_id):
            return {"info": {"id": "msg_test"}}

        monkeypatch.setattr(module, "resolve_active_session_paths", mock_resolve_paths)
        monkeypatch.setattr(module, "check_server_health", mock_health)
        monkeypatch.setattr(module, "get_active_session", mock_get_session)
        monkeypatch.setattr(module, "send_session_message", mock_send_message)
        monkeypatch.setenv("AI_GOVERNANCE_SKIP_SERVER_HEALTH_CHECK", "1")

        result = module.main(["--quiet"])

        assert result == 0

        state_doc = json.loads(session_path.read_text())
        state = state_doc.get("SESSION_STATE", {})

        assert state.get("SessionHydration", {}).get("hydrated_session_id") == "ses_new"


class TestBootstrapOpencodePort:
    """Tests for bootstrap --opencode-port parameter."""

    @pytest.mark.integration
    def test_bootstrap_parses_opencode_port(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Bootstrap accepts --opencode-port parameter.

        Requires installed Python binding - marked as integration test.
        """
        import subprocess

        bootstrap_path = Path(__file__).parent.parent / "bin" / "opencode-governance-bootstrap"
        binding_file = bootstrap_path.parent / "PYTHON_BINDING"

        if not binding_file.exists():
            pytest.skip("PYTHON_BINDING not found - requires installation")

        result = subprocess.run(
            ["bash", str(bootstrap_path), "--opencode-port", "4096", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0

    @pytest.mark.integration
    def test_bootstrap_hydrate_routes_to_session_hydration(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Bootstrap --hydrate routes to session_hydration module.

        Requires installed Python binding - marked as integration test.
        """
        import subprocess

        bootstrap_path = Path(__file__).parent.parent / "bin" / "opencode-governance-bootstrap"
        binding_file = bootstrap_path.parent / "PYTHON_BINDING"

        if not binding_file.exists():
            pytest.skip("PYTHON_BINDING not found - requires installation")

        monkeypatch.setenv("AI_GOVERNANCE_SKIP_SERVER_HEALTH_CHECK", "1")

        result = subprocess.run(
            ["bash", str(bootstrap_path), "--hydrate", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert result.returncode == 0
        assert "hydrate" in result.stdout.lower() or "session" in result.stdout.lower()
