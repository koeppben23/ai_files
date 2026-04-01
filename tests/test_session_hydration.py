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

        def mock_get_session(project_path=None, **kwargs):
            return {
                "id": "ses_test123",
                "title": "Test Session",
                "directory": str(tmp_path / "repo"),
            }

        def mock_send_message(text, session_id, **kwargs):
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

        def mock_get_session(project_path=None, **kwargs):
            return {"id": "ses_test456", "title": "Test Session"}

        def mock_send_message(text, session_id, **kwargs):
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
        """Hydration fails when server is not reachable (managed mode)."""
        from governance_runtime.entrypoints import session_hydration as module
        from governance_runtime.infrastructure.opencode_server_client import ServerNotAvailableError

        session_path = _write_session_state(tmp_path, {"phase": "3", "repo_root": str(tmp_path / "repo")})
        _write_core_hydration_artifacts(tmp_path / "workspaces" / "testrepo")

        def mock_resolve_paths():
            return (session_path, "testrepo", tmp_path / "workspaces", tmp_path / "workspaces" / "testrepo")

        def mock_ensure_error():
            raise ServerNotAvailableError("Connection refused")

        monkeypatch.setattr(module, "resolve_active_session_paths", mock_resolve_paths)
        monkeypatch.setattr(module, "ensure_opencode_server_running", mock_ensure_error)

        result = module.main(["--quiet", "--server-mode", "managed"])

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

        def mock_no_session(project_path=None, **kwargs):
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
        """Hydration fails closed when /global/health reports unhealthy (managed mode)."""
        from governance_runtime.entrypoints import session_hydration as module

        session_path = _write_session_state(tmp_path, {"phase": "3", "repo_root": str(tmp_path / "repo")})
        _write_core_hydration_artifacts(tmp_path / "workspaces" / "testrepo")

        def mock_resolve_paths():
            return (session_path, "testrepo", tmp_path / "workspaces", tmp_path / "workspaces" / "testrepo")

        def mock_ensure_server_returns_unhealthy():
            return {"healthy": False, "version": "1.3.7"}

        monkeypatch.setattr(module, "resolve_active_session_paths", mock_resolve_paths)
        monkeypatch.setattr(module, "ensure_opencode_server_running", mock_ensure_server_returns_unhealthy)

        rc = module.main(["--quiet", "--server-mode", "managed"])
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
        """Hydration fails closed when /global/health payload is malformed (managed mode)."""
        from governance_runtime.entrypoints import session_hydration as module

        session_path = _write_session_state(tmp_path, {"phase": "3", "repo_root": str(tmp_path / "repo")})
        _write_core_hydration_artifacts(tmp_path / "workspaces" / "testrepo")

        def mock_resolve_paths():
            return (session_path, "testrepo", tmp_path / "workspaces", tmp_path / "workspaces" / "testrepo")

        def mock_health_malformed():
            return {"status": "ok"}

        monkeypatch.setattr(module, "resolve_active_session_paths", mock_resolve_paths)
        monkeypatch.setattr(module, "ensure_opencode_server_running", mock_health_malformed)

        rc = module.main(["--quiet", "--server-mode", "managed"])
        assert rc == 2
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["reason_code"] == "BLOCKED-SERVER-TARGET-UNHEALTHY"
        assert payload["reason"] == "server-unhealthy"


class TestSessionHydrationServerMode:
    """Tests for /hydrate --server-mode dual-mode behavior.

    Happy: attach_existing discovers server, managed starts server
    Bad: Discovery failures produce correct blocked codes
    Corner: Invalid mode, skip flag interaction
    Edge: Platform error on Windows
    """

    def _setup_hydration_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Common setup for hydration tests: session + artifacts + mocks."""
        from governance_runtime.entrypoints import session_hydration as module

        session_path = _write_session_state(tmp_path, {"phase": "3", "repo_root": str(tmp_path / "repo")})
        workspace_dir = tmp_path / "workspaces" / "testrepo"
        _write_core_hydration_artifacts(workspace_dir)

        def mock_resolve_paths():
            return (session_path, "testrepo", tmp_path / "workspaces", workspace_dir)

        monkeypatch.setattr(module, "resolve_active_session_paths", mock_resolve_paths)
        return module, session_path

    def test_happy_attach_existing_discovers_server(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
    ):
        """Happy: attach_existing discovers healthy server → hydration succeeds."""
        module, session_path = self._setup_hydration_env(tmp_path, monkeypatch)

        discovered_url = "http://127.0.0.1:52372"

        def mock_discover():
            return (discovered_url, {"healthy": True, "version": "1.3.7"})

        captured_urls = {"get_session": None, "send_message": None}

        def mock_get_session(project_path=None, **kwargs):
            captured_urls["get_session"] = kwargs.get("base_url")
            return {"id": "ses_disc", "title": "Discovered Session"}

        def mock_send_message(text, session_id, **kwargs):
            captured_urls["send_message"] = kwargs.get("base_url")
            return {"info": {"id": "msg_test"}}

        monkeypatch.setattr(module, "discover_local_opencode_server", mock_discover)
        monkeypatch.setattr(module, "get_active_session", mock_get_session)
        monkeypatch.setattr(module, "send_session_message", mock_send_message)

        rc = module.main(["--quiet", "--server-mode", "attach_existing"])
        assert rc == 0
        state = json.loads(session_path.read_text())["SESSION_STATE"]
        assert state["SessionHydration"]["hydrated_session_id"] == "ses_disc"
        # Critical: verify the discovered URL was threaded through to API calls
        assert captured_urls["get_session"] == discovered_url, (
            f"get_active_session did not receive discovered URL: got {captured_urls['get_session']}"
        )
        assert captured_urls["send_message"] == discovered_url, (
            f"send_session_message did not receive discovered URL: got {captured_urls['send_message']}"
        )

    def test_happy_managed_mode_uses_ensure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ):
        """Happy: managed mode calls ensure_opencode_server_running and threads URL."""
        module, session_path = self._setup_hydration_env(tmp_path, monkeypatch)

        managed_url = "http://127.0.0.1:4096"

        def mock_ensure():
            return {"healthy": True, "version": "1.3.7", "started": False, "target_url": managed_url}

        captured_urls = {"get_session": None, "send_message": None}

        def mock_get_session(project_path=None, **kwargs):
            captured_urls["get_session"] = kwargs.get("base_url")
            return {"id": "ses_managed", "title": "Managed Session"}

        def mock_send_message(text, session_id, **kwargs):
            captured_urls["send_message"] = kwargs.get("base_url")
            return {"info": {"id": "msg_test"}}

        monkeypatch.setattr(module, "ensure_opencode_server_running", mock_ensure)
        monkeypatch.setattr(module, "get_active_session", mock_get_session)
        monkeypatch.setattr(module, "send_session_message", mock_send_message)

        rc = module.main(["--quiet", "--server-mode", "managed"])
        assert rc == 0
        # Critical: verify the managed URL was threaded through to API calls
        assert captured_urls["get_session"] == managed_url, (
            f"get_active_session did not receive managed URL: got {captured_urls['get_session']}"
        )
        assert captured_urls["send_message"] == managed_url, (
            f"send_session_message did not receive managed URL: got {captured_urls['send_message']}"
        )

    def test_happy_default_mode_is_attach_existing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
    ):
        """Happy: No --server-mode defaults to attach_existing, URL is threaded."""
        module, session_path = self._setup_hydration_env(tmp_path, monkeypatch)

        discovered_url = "http://127.0.0.1:52372"

        def mock_discover():
            return (discovered_url, {"healthy": True, "version": "1.3.7"})

        captured_urls = {"get_session": None, "send_message": None}

        def mock_get_session(project_path=None, **kwargs):
            captured_urls["get_session"] = kwargs.get("base_url")
            return {"id": "ses_default", "title": "Default Session"}

        def mock_send_message(text, session_id, **kwargs):
            captured_urls["send_message"] = kwargs.get("base_url")
            return {"info": {"id": "msg_test"}}

        monkeypatch.setattr(module, "discover_local_opencode_server", mock_discover)
        monkeypatch.setattr(module, "get_active_session", mock_get_session)
        monkeypatch.setattr(module, "send_session_message", mock_send_message)
        monkeypatch.delenv("OPENCODE_SERVER_MODE", raising=False)

        rc = module.main(["--quiet"])
        assert rc == 0
        # Default mode is attach_existing → discovered URL must be threaded
        assert captured_urls["get_session"] == discovered_url
        assert captured_urls["send_message"] == discovered_url

    def test_bad_attach_existing_not_found(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
    ):
        """Bad: attach_existing with no servers → BLOCKED-SERVER-DISCOVERY-NOT-FOUND."""
        from governance_runtime.infrastructure.opencode_server_client import ServerDiscoveryNotFoundError

        module, _ = self._setup_hydration_env(tmp_path, monkeypatch)

        def mock_discover():
            raise ServerDiscoveryNotFoundError("No server found", candidates_scanned=0)

        monkeypatch.setattr(module, "discover_local_opencode_server", mock_discover)

        rc = module.main(["--quiet", "--server-mode", "attach_existing"])
        assert rc == 2
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["reason_code"] == "BLOCKED-SERVER-DISCOVERY-NOT-FOUND"
        assert payload["blocked"] is True

    def test_bad_attach_existing_ambiguous(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
    ):
        """Bad: attach_existing with multiple servers → BLOCKED-SERVER-DISCOVERY-AMBIGUOUS."""
        from governance_runtime.infrastructure.opencode_server_client import ServerDiscoveryAmbiguousError

        module, _ = self._setup_hydration_env(tmp_path, monkeypatch)

        def mock_discover():
            raise ServerDiscoveryAmbiguousError(
                "Multiple servers", healthy_endpoints=["http://127.0.0.1:52372", "http://127.0.0.1:52373"]
            )

        monkeypatch.setattr(module, "discover_local_opencode_server", mock_discover)

        rc = module.main(["--quiet", "--server-mode", "attach_existing"])
        assert rc == 2
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["reason_code"] == "BLOCKED-SERVER-DISCOVERY-AMBIGUOUS"

    def test_bad_attach_existing_auth_required(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
    ):
        """Bad: attach_existing with auth-required → BLOCKED-SERVER-AUTH-REQUIRED."""
        from governance_runtime.infrastructure.opencode_server_client import ServerAuthRequiredError

        module, _ = self._setup_hydration_env(tmp_path, monkeypatch)

        def mock_discover():
            raise ServerAuthRequiredError("Auth required", target_url="http://127.0.0.1:52372")

        monkeypatch.setattr(module, "discover_local_opencode_server", mock_discover)

        rc = module.main(["--quiet", "--server-mode", "attach_existing"])
        assert rc == 2
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["reason_code"] == "BLOCKED-SERVER-AUTH-REQUIRED"

    def test_edge_attach_existing_unsupported_platform(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
    ):
        """Edge: attach_existing on Windows → BLOCKED-SERVER-DISCOVERY-UNSUPPORTED-PLATFORM."""
        from governance_runtime.infrastructure.opencode_server_client import (
            ServerDiscoveryUnsupportedPlatformError,
        )

        module, _ = self._setup_hydration_env(tmp_path, monkeypatch)

        def mock_discover():
            raise ServerDiscoveryUnsupportedPlatformError(
                "attach_existing discovery is not implemented on Windows yet; "
                "use --server-mode managed",
                platform="win32",
            )

        monkeypatch.setattr(module, "discover_local_opencode_server", mock_discover)

        rc = module.main(["--quiet", "--server-mode", "attach_existing"])
        assert rc == 2
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["reason_code"] == "BLOCKED-SERVER-DISCOVERY-UNSUPPORTED-PLATFORM"
        assert "--server-mode managed" in payload["recovery_action"]

    def test_corner_invalid_server_mode(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
    ):
        """Corner: Invalid --server-mode value → blocked with clear message."""
        module, _ = self._setup_hydration_env(tmp_path, monkeypatch)

        rc = module.main(["--quiet", "--server-mode", "auto_discover"])
        assert rc == 2
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["reason_code"] == "BLOCKED-UNSPECIFIED"
        assert "Invalid server mode" in payload["observed"]

    def test_corner_skip_health_check_bypasses_mode(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ):
        """Corner: AI_GOVERNANCE_SKIP_SERVER_HEALTH_CHECK=1 skips mode resolution entirely."""
        module, session_path = self._setup_hydration_env(tmp_path, monkeypatch)

        captured_urls = {"get_session": None, "send_message": None}

        def mock_get_session(project_path=None, **kwargs):
            captured_urls["get_session"] = kwargs.get("base_url")
            return {"id": "ses_skip", "title": "Skip Session"}

        def mock_send_message(text, session_id, **kwargs):
            captured_urls["send_message"] = kwargs.get("base_url")
            return {"info": {"id": "msg_test"}}

        monkeypatch.setattr(module, "get_active_session", mock_get_session)
        monkeypatch.setattr(module, "send_session_message", mock_send_message)
        monkeypatch.setenv("AI_GOVERNANCE_SKIP_SERVER_HEALTH_CHECK", "1")

        # No discovery or ensure mocks — they should never be called
        rc = module.main(["--quiet"])
        assert rc == 0
        # Skip mode: no URL resolved, falls back to None (old resolution path)
        assert captured_urls["get_session"] is None
        assert captured_urls["send_message"] is None

    def test_edge_env_server_mode_managed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ):
        """Edge: OPENCODE_SERVER_MODE=managed env var activates managed mode."""
        module, session_path = self._setup_hydration_env(tmp_path, monkeypatch)

        managed_url = "http://127.0.0.1:4096"

        def mock_ensure():
            return {"healthy": True, "version": "1.3.7", "started": False, "target_url": managed_url}

        def mock_get_session(project_path=None, **kwargs):
            return {"id": "ses_env_managed", "title": "Env Managed"}

        def mock_send_message(text, session_id, **kwargs):
            return {"info": {"id": "msg_test"}}

        monkeypatch.setenv("OPENCODE_SERVER_MODE", "managed")
        monkeypatch.setattr(module, "ensure_opencode_server_running", mock_ensure)
        monkeypatch.setattr(module, "get_active_session", mock_get_session)
        monkeypatch.setattr(module, "send_session_message", mock_send_message)

        rc = module.main(["--quiet"])
        assert rc == 0

    def test_edge_cli_overrides_env_server_mode(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
    ):
        """Edge: CLI --server-mode overrides OPENCODE_SERVER_MODE env."""
        from governance_runtime.infrastructure.opencode_server_client import ServerDiscoveryNotFoundError

        module, _ = self._setup_hydration_env(tmp_path, monkeypatch)

        # ENV says managed, but CLI says attach_existing → discovery is called
        monkeypatch.setenv("OPENCODE_SERVER_MODE", "managed")

        def mock_discover():
            raise ServerDiscoveryNotFoundError("No server found", candidates_scanned=0)

        monkeypatch.setattr(module, "discover_local_opencode_server", mock_discover)

        rc = module.main(["--quiet", "--server-mode", "attach_existing"])
        assert rc == 2
        payload = json.loads(capsys.readouterr().out.strip())
        assert payload["reason_code"] == "BLOCKED-SERVER-DISCOVERY-NOT-FOUND"
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

        def mock_get_session(project_path=None, **kwargs):
            return {"id": "ses_new", "title": "New Session"}

        def mock_send_message(text, session_id, **kwargs):
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
