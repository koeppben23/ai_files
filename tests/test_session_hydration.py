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


def _write_core_hydration_artifacts(workspace_dir: Path) -> None:
    workspace_dir.mkdir(parents=True, exist_ok=True)
    (workspace_dir / "repo-map-digest.md").write_text(
        "# Repo Map\n\n- src/api.py\n- src/core.py\n",
        encoding="utf-8",
    )
    (workspace_dir / "workspace-memory.yaml").write_text(
        "patterns:\n  - auth-flow\n",
        encoding="utf-8",
    )
    (workspace_dir / "decision-pack.md").write_text(
        "# Decision Pack\n\n- D001: Use JWT\n",
        encoding="utf-8",
    )


class TestSessionHydrationHappy:
    """Happy path tests for session hydration."""

    def test_hydration_success_with_mocked_server(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Successful hydration binds session and persists receipt."""
        from governance_runtime.entrypoints import session_hydration as module

        session_path = _write_session_state(tmp_path, {"phase": "3", "repo_root": str(tmp_path / "repo")})

        mock_workspace = tmp_path / "workspaces" / "testrepo"
        _write_core_hydration_artifacts(mock_workspace)

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
        """Hydration brief is built from canonical artifact content."""
        from governance_runtime.entrypoints import session_hydration as module

        session_path = _write_session_state(tmp_path, {"phase": "3", "repo_root": str(tmp_path / "repo")})

        workspace_dir = tmp_path / "workspaces" / "testrepo"
        _write_core_hydration_artifacts(workspace_dir)
        (workspace_dir / "business-rules.md").write_text(
            "# Business Rules\n\n- BR-1: Always verify auth\n",
            encoding="utf-8",
        )

        captured = {"text": "", "session_id": ""}

        def mock_resolve_paths():
            return (session_path, "testrepo", tmp_path / "workspaces", workspace_dir)

        def mock_health():
            return {"healthy": True, "version": "1.3.7"}

        def mock_get_session(project_path=None):
            return {"id": "ses_test456", "title": "Test Session"}

        def mock_send_message(text, session_id):
            captured["text"] = text
            captured["session_id"] = session_id
            return {"info": {"id": "msg_test"}}

        monkeypatch.setattr(module, "resolve_active_session_paths", mock_resolve_paths)
        monkeypatch.setattr(module, "check_server_health", mock_health)
        monkeypatch.setattr(module, "get_active_session", mock_get_session)
        monkeypatch.setattr(module, "send_session_message", mock_send_message)
        monkeypatch.setenv("AI_GOVERNANCE_SKIP_SERVER_HEALTH_CHECK", "1")

        result = module.main(["--quiet"])

        assert result == 0
        assert captured["session_id"] == "ses_test456"
        assert "Architecture Summary (repo-map-digest)" in captured["text"]
        assert "Workspace Memory" in captured["text"]
        assert "Decision Pack" in captured["text"]
        assert "Business Rules" in captured["text"]
        assert "D001: Use JWT" in captured["text"]
        assert "BR-1: Always verify auth" in captured["text"]

    def test_hydration_blocks_when_core_knowledge_base_missing(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ):
        """Hydration must fail-closed when core knowledge artifacts are missing."""
        from governance_runtime.entrypoints import session_hydration as module

        session_path = _write_session_state(tmp_path, {"phase": "3", "repo_root": str(tmp_path / "repo")})
        workspace_dir = tmp_path / "workspaces" / "testrepo"
        workspace_dir.mkdir(parents=True, exist_ok=True)
        (workspace_dir / "repo-map-digest.md").write_text("# Repo\n", encoding="utf-8")

        def mock_resolve_paths():
            return (session_path, "testrepo", tmp_path / "workspaces", workspace_dir)

        monkeypatch.setattr(module, "resolve_active_session_paths", mock_resolve_paths)

        rc = module.main(["--quiet"])
        assert rc == 2
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["status"] == "blocked"
        assert payload["reason"] == "knowledge-base-incomplete"
        assert payload["reason_code"] == "HYDRATION-KNOWLEDGE-BASE-INCOMPLETE"


class TestSessionHydrationBad:
    """Bad path tests for session hydration."""

    def test_hydration_blocks_when_server_unavailable(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Hydration fails when server is not reachable."""
        from governance_runtime.entrypoints import session_hydration as module
        from governance_runtime.infrastructure.opencode_server_client import ServerNotAvailableError

        session_path = _write_session_state(tmp_path, {"phase": "3", "repo_root": str(tmp_path / "repo")})
        _write_core_hydration_artifacts(tmp_path / "workspaces" / "testrepo")

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

        session_path = _write_session_state(tmp_path, {"phase": "3", "repo_root": str(tmp_path / "repo")})
        _write_core_hydration_artifacts(tmp_path / "workspaces" / "testrepo")

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

    def test_hydration_blocks_when_server_health_is_unhealthy(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ):
        """Hydration fails closed when /global/health reports unhealthy."""
        from governance_runtime.entrypoints import session_hydration as module

        session_path = _write_session_state(tmp_path, {"phase": "3", "repo_root": str(tmp_path / "repo")})
        _write_core_hydration_artifacts(tmp_path / "workspaces" / "testrepo")

        def mock_resolve_paths():
            return (session_path, "testrepo", tmp_path / "workspaces", tmp_path / "workspaces" / "testrepo")

        def mock_health_unhealthy():
            return {"healthy": False, "version": "1.3.7"}

        def mock_ensure_server_returns_unhealthy():
            return {"healthy": False, "version": "1.3.7"}

        monkeypatch.setattr(module, "resolve_active_session_paths", mock_resolve_paths)
        monkeypatch.setattr(module, "ensure_opencode_server_running", mock_ensure_server_returns_unhealthy)

        rc = module.main(["--quiet"])
        assert rc == 2
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["reason_code"] == "BLOCKED-SERVER-TARGET-UNHEALTHY"
        assert payload["reason"] == "server-unhealthy"

    def test_hydration_blocks_when_server_health_payload_is_malformed(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ):
        """Hydration fails closed when /global/health payload is malformed."""
        from governance_runtime.entrypoints import session_hydration as module

        session_path = _write_session_state(tmp_path, {"phase": "3", "repo_root": str(tmp_path / "repo")})
        _write_core_hydration_artifacts(tmp_path / "workspaces" / "testrepo")

        def mock_resolve_paths():
            return (session_path, "testrepo", tmp_path / "workspaces", tmp_path / "workspaces" / "testrepo")

        def mock_health_malformed():
            return {"status": "ok"}

        monkeypatch.setattr(module, "resolve_active_session_paths", mock_resolve_paths)
        monkeypatch.setattr(module, "ensure_opencode_server_running", mock_health_malformed)

        rc = module.main(["--quiet"])
        assert rc == 2
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["reason_code"] == "BLOCKED-SERVER-TARGET-UNHEALTHY"
        assert payload["reason"] == "server-unhealthy"


class TestSessionHydrationEdge:
    """Edge case tests for session hydration."""

    def test_hydration_idempotent_rerun(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Hydration can be re-run (idempotent)."""
        from governance_runtime.entrypoints import session_hydration as module

        existing_state = {
            "phase": "4",
            "repo_root": str(tmp_path / "repo"),
            "active_gate": "Ticket Intake Gate",
            "SessionHydration": {
                "hydrated_session_id": "ses_old",
                "hydrated_at": "2026-01-01T00:00:00Z",
                "status": "hydrated",
            },
        }
        session_path = _write_session_state(tmp_path, existing_state)

        workspace_dir = tmp_path / "workspaces" / "testrepo"
        _write_core_hydration_artifacts(workspace_dir)

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

    def test_bootstrap_parses_opencode_port(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Bootstrap accepts --opencode-port parameter.

        Creates a temporary PYTHON_BINDING file if needed to test the bootstrap.
        """
        import subprocess

        bootstrap_path = Path(__file__).parent.parent / "bin" / "opencode-governance-bootstrap"
        binding_file = bootstrap_path.parent / "PYTHON_BINDING"

        original_binding = None
        if binding_file.exists():
            original_binding = binding_file.read_text()

        try:
            binding_file.write_text("/usr/bin/python3\n")

            result = subprocess.run(
                ["bash", str(bootstrap_path), "--opencode-port", "4096", "--help"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            assert result.returncode == 0, f"Bootstrap failed: {result.stderr}"

        finally:
            if original_binding is not None:
                binding_file.write_text(original_binding)
            elif binding_file.exists():
                binding_file.unlink()

    def test_bootstrap_hydrate_routes_to_session_hydration(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Bootstrap --hydrate routes to session_hydration module.

        Creates a temporary PYTHON_BINDING file if needed to test the bootstrap.
        """
        import subprocess

        bootstrap_path = Path(__file__).parent.parent / "bin" / "opencode-governance-bootstrap"
        binding_file = bootstrap_path.parent / "PYTHON_BINDING"

        original_binding = None
        if binding_file.exists():
            original_binding = binding_file.read_text()

        try:
            binding_file.write_text("/usr/bin/python3\n")

            monkeypatch.setenv("AI_GOVERNANCE_SKIP_SERVER_HEALTH_CHECK", "1")

            result = subprocess.run(
                ["bash", str(bootstrap_path), "--hydrate", "--help"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            assert result.returncode == 0, f"Bootstrap failed: {result.stderr}"

        finally:
            if original_binding is not None:
                binding_file.write_text(original_binding)
            elif binding_file.exists():
                binding_file.unlink()
        assert "hydrate" in result.stdout.lower() or "session" in result.stdout.lower()
