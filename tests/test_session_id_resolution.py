"""Tests for session ID resolution fallback and send_session_prompt session_id= parameter.

Patch 20 — Bug 2: resolve_session_id() now has a three-source chain:
    1. OPENCODE_SESSION_ID env var  (explicit, pipeline mode)
    2. SESSION_STATE.SessionHydration.hydrated_session_id  (direct/chat mode)
    3. Fail-closed with APIError

send_session_prompt() now accepts an optional session_id= parameter that
bypasses resolve_session_id() entirely when provided.

Coverage: happy path, bad path, corner cases, edge cases, performance.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from governance_runtime.infrastructure.opencode_server_client import (
    APIError,
    _read_hydrated_session_id_from_state,
    resolve_session_id,
    send_session_prompt,
)


# ── resolve_session_id: Source 1 — OPENCODE_SESSION_ID env var ───────

@pytest.mark.governance
class TestResolveSessionIdEnvVar:
    """Source 1: OPENCODE_SESSION_ID env var is the highest-priority source."""

    def test_happy_env_var_returns_id_and_source(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENCODE_SESSION_ID", "sess-env-1")
        session_id, evidence = resolve_session_id()
        assert session_id == "sess-env-1"
        assert evidence["session_id_source"] == "OPENCODE_SESSION_ID"

    def test_env_var_takes_precedence_over_state(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Even if SESSION_STATE has a hydrated session, env var wins."""
        monkeypatch.setenv("OPENCODE_SESSION_ID", "sess-env-1")
        with patch(
            "governance_runtime.infrastructure.opencode_server_client._read_hydrated_session_id_from_state",
            return_value="sess-from-state",
        ):
            session_id, evidence = resolve_session_id()
        assert session_id == "sess-env-1"
        assert evidence["session_id_source"] == "OPENCODE_SESSION_ID"

    def test_env_var_stripped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENCODE_SESSION_ID", "  sess-trimmed  ")
        session_id, _ = resolve_session_id()
        assert session_id == "sess-trimmed"

    def test_env_var_whitespace_only_falls_through(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Whitespace-only env var should NOT match source 1."""
        monkeypatch.setenv("OPENCODE_SESSION_ID", "   ")
        with patch(
            "governance_runtime.infrastructure.opencode_server_client._read_hydrated_session_id_from_state",
            return_value="sess-from-state",
        ):
            session_id, evidence = resolve_session_id()
        assert session_id == "sess-from-state"
        assert evidence["session_id_source"] == "SESSION_STATE.SessionHydration"

    def test_env_var_empty_falls_through(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENCODE_SESSION_ID", "")
        with patch(
            "governance_runtime.infrastructure.opencode_server_client._read_hydrated_session_id_from_state",
            return_value="sess-from-state",
        ):
            session_id, evidence = resolve_session_id()
        assert session_id == "sess-from-state"


# ── resolve_session_id: Source 2 — SESSION_STATE fallback ────────────

@pytest.mark.governance
class TestResolveSessionIdStateFallback:
    """Source 2: SESSION_STATE.SessionHydration.hydrated_session_id."""

    def test_happy_state_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENCODE_SESSION_ID", raising=False)
        with patch(
            "governance_runtime.infrastructure.opencode_server_client._read_hydrated_session_id_from_state",
            return_value="sess-hydrated-42",
        ):
            session_id, evidence = resolve_session_id()
        assert session_id == "sess-hydrated-42"
        assert evidence["session_id_source"] == "SESSION_STATE.SessionHydration"

    def test_state_fallback_none_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When both sources fail, APIError is raised."""
        monkeypatch.delenv("OPENCODE_SESSION_ID", raising=False)
        with patch(
            "governance_runtime.infrastructure.opencode_server_client._read_hydrated_session_id_from_state",
            return_value=None,
        ):
            with pytest.raises(APIError, match="No OpenCode session ID available"):
                resolve_session_id()

    def test_state_fallback_empty_string_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENCODE_SESSION_ID", raising=False)
        with patch(
            "governance_runtime.infrastructure.opencode_server_client._read_hydrated_session_id_from_state",
            return_value="",
        ):
            with pytest.raises(APIError):
                resolve_session_id()


# ── resolve_session_id: Source 3 — fail-closed ───────────────────────

@pytest.mark.governance
class TestResolveSessionIdFailClosed:
    """Source 3: Neither env var nor state → APIError."""

    def test_fail_closed_message_content(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENCODE_SESSION_ID", raising=False)
        with patch(
            "governance_runtime.infrastructure.opencode_server_client._read_hydrated_session_id_from_state",
            return_value=None,
        ):
            with pytest.raises(APIError) as exc_info:
                resolve_session_id()
            msg = str(exc_info.value)
            assert "OPENCODE_SESSION_ID" in msg
            assert "/hydrate" in msg

    def test_fail_closed_is_api_error_type(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENCODE_SESSION_ID", raising=False)
        with patch(
            "governance_runtime.infrastructure.opencode_server_client._read_hydrated_session_id_from_state",
            return_value=None,
        ):
            with pytest.raises(APIError):
                resolve_session_id()


# ── _read_hydrated_session_id_from_state ─────────────────────────────

# The helper uses lazy imports, so we mock on the source modules:
_LOCATOR = "governance_runtime.infrastructure.session_locator.resolve_active_session_paths"
_LOAD_JSON = "governance_runtime.infrastructure.json_store.load_json"


@pytest.mark.governance
class TestReadHydratedSessionIdFromState:
    """Unit tests for the SESSION_STATE file reader helper."""

    def test_happy_returns_hydrated_id(self) -> None:
        state_doc = {
            "SESSION_STATE": {
                "SessionHydration": {
                    "status": "hydrated",
                    "hydrated_session_id": "sess-abc",
                }
            }
        }
        with patch(_LOCATOR) as mock_paths, patch(_LOAD_JSON, return_value=state_doc):
            mock_paths.return_value = (Path("/fake/SESSION_STATE.json"), "fp", Path("/w"), Path("/wd"))
            result = _read_hydrated_session_id_from_state()
        assert result == "sess-abc"

    def test_not_hydrated_returns_none(self) -> None:
        state_doc = {
            "SESSION_STATE": {
                "SessionHydration": {
                    "status": "not_hydrated",
                    "source": "bootstrap",
                }
            }
        }
        with patch(_LOCATOR) as mock_paths, patch(_LOAD_JSON, return_value=state_doc):
            mock_paths.return_value = (Path("/fake"), "fp", Path("/w"), Path("/wd"))
            result = _read_hydrated_session_id_from_state()
        assert result is None

    def test_missing_session_state_key_returns_none(self) -> None:
        with patch(_LOCATOR) as mock_paths, patch(_LOAD_JSON, return_value={"other": "data"}):
            mock_paths.return_value = (Path("/fake"), "fp", Path("/w"), Path("/wd"))
            assert _read_hydrated_session_id_from_state() is None

    def test_session_state_not_dict_returns_none(self) -> None:
        with patch(_LOCATOR) as mock_paths, patch(
            _LOAD_JSON, return_value={"SESSION_STATE": "not_a_dict"}
        ):
            mock_paths.return_value = (Path("/fake"), "fp", Path("/w"), Path("/wd"))
            assert _read_hydrated_session_id_from_state() is None

    def test_session_hydration_not_dict_returns_none(self) -> None:
        with patch(_LOCATOR) as mock_paths, patch(
            _LOAD_JSON, return_value={"SESSION_STATE": {"SessionHydration": "broken"}}
        ):
            mock_paths.return_value = (Path("/fake"), "fp", Path("/w"), Path("/wd"))
            assert _read_hydrated_session_id_from_state() is None

    def test_empty_hydrated_session_id_returns_none(self) -> None:
        state_doc = {
            "SESSION_STATE": {
                "SessionHydration": {
                    "status": "hydrated",
                    "hydrated_session_id": "",
                }
            }
        }
        with patch(_LOCATOR) as mock_paths, patch(_LOAD_JSON, return_value=state_doc):
            mock_paths.return_value = (Path("/fake"), "fp", Path("/w"), Path("/wd"))
            assert _read_hydrated_session_id_from_state() is None

    def test_whitespace_only_hydrated_session_id_returns_none(self) -> None:
        state_doc = {
            "SESSION_STATE": {
                "SessionHydration": {
                    "status": "hydrated",
                    "hydrated_session_id": "   ",
                }
            }
        }
        with patch(_LOCATOR) as mock_paths, patch(_LOAD_JSON, return_value=state_doc):
            mock_paths.return_value = (Path("/fake"), "fp", Path("/w"), Path("/wd"))
            assert _read_hydrated_session_id_from_state() is None

    def test_missing_hydrated_session_id_key_returns_none(self) -> None:
        state_doc = {
            "SESSION_STATE": {
                "SessionHydration": {
                    "status": "hydrated",
                    # No hydrated_session_id key at all
                }
            }
        }
        with patch(_LOCATOR) as mock_paths, patch(_LOAD_JSON, return_value=state_doc):
            mock_paths.return_value = (Path("/fake"), "fp", Path("/w"), Path("/wd"))
            assert _read_hydrated_session_id_from_state() is None

    def test_resolve_paths_raises_returns_none(self) -> None:
        """If resolve_active_session_paths() fails, return None (fail-safe)."""
        with patch(_LOCATOR, side_effect=RuntimeError("binding unavailable")):
            assert _read_hydrated_session_id_from_state() is None

    def test_load_json_raises_returns_none(self) -> None:
        """If the SESSION_STATE file is corrupted, return None."""
        with patch(_LOCATOR) as mock_paths, patch(
            _LOAD_JSON, side_effect=json.JSONDecodeError("bad", "", 0)
        ):
            mock_paths.return_value = (Path("/fake"), "fp", Path("/w"), Path("/wd"))
            assert _read_hydrated_session_id_from_state() is None

    def test_status_case_insensitive(self) -> None:
        """Status comparison must be case-insensitive."""
        state_doc = {
            "SESSION_STATE": {
                "SessionHydration": {
                    "status": "HYDRATED",
                    "hydrated_session_id": "sess-upper",
                }
            }
        }
        with patch(_LOCATOR) as mock_paths, patch(_LOAD_JSON, return_value=state_doc):
            mock_paths.return_value = (Path("/fake"), "fp", Path("/w"), Path("/wd"))
            assert _read_hydrated_session_id_from_state() == "sess-upper"

    def test_status_with_whitespace(self) -> None:
        state_doc = {
            "SESSION_STATE": {
                "SessionHydration": {
                    "status": "  hydrated  ",
                    "hydrated_session_id": "sess-ws",
                }
            }
        }
        with patch(_LOCATOR) as mock_paths, patch(_LOAD_JSON, return_value=state_doc):
            mock_paths.return_value = (Path("/fake"), "fp", Path("/w"), Path("/wd"))
            assert _read_hydrated_session_id_from_state() == "sess-ws"

    def test_status_none_returns_none(self) -> None:
        state_doc = {
            "SESSION_STATE": {
                "SessionHydration": {
                    "status": None,
                    "hydrated_session_id": "sess-should-not-return",
                }
            }
        }
        with patch(_LOCATOR) as mock_paths, patch(_LOAD_JSON, return_value=state_doc):
            mock_paths.return_value = (Path("/fake"), "fp", Path("/w"), Path("/wd"))
            assert _read_hydrated_session_id_from_state() is None

    def test_hydrating_status_returns_none(self) -> None:
        """Only 'hydrated' is valid — 'hydrating' must not match."""
        state_doc = {
            "SESSION_STATE": {
                "SessionHydration": {
                    "status": "hydrating",
                    "hydrated_session_id": "sess-nope",
                }
            }
        }
        with patch(_LOCATOR) as mock_paths, patch(_LOAD_JSON, return_value=state_doc):
            mock_paths.return_value = (Path("/fake"), "fp", Path("/w"), Path("/wd"))
            assert _read_hydrated_session_id_from_state() is None


# ── send_session_prompt: explicit session_id= parameter ──────────────

@pytest.mark.governance
class TestSendSessionPromptExplicitSessionId:
    """send_session_prompt(session_id=...) bypasses resolve_session_id()."""

    def test_explicit_session_id_used_in_request(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENCODE_PORT", "4096")
        # Clear the autouse fixture env var to prove explicit param works alone
        monkeypatch.delenv("OPENCODE_SESSION_ID", raising=False)
        with patch("governance_runtime.infrastructure.opencode_server_client.post_json") as mock:
            mock.return_value = {"info": {"parts": []}}
            result = send_session_prompt("Hello", session_id="explicit-sess-1")
            call_url = mock.call_args[0][0]
            assert "/session/explicit-sess-1/message" in call_url
            assert result["resolved_session_id"] == "explicit-sess-1"
            assert result["session_evidence"]["session_id_source"] == "explicit_parameter"

    def test_explicit_session_id_overrides_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Explicit parameter wins over env var."""
        monkeypatch.setenv("OPENCODE_PORT", "4096")
        monkeypatch.setenv("OPENCODE_SESSION_ID", "env-sess")
        with patch("governance_runtime.infrastructure.opencode_server_client.post_json") as mock:
            mock.return_value = {"info": {}}
            send_session_prompt("Hello", session_id="explicit-sess-2")
            call_url = mock.call_args[0][0]
            assert "/session/explicit-sess-2/message" in call_url

    def test_explicit_session_id_skips_resolve(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """resolve_session_id() must NOT be called when session_id is provided."""
        monkeypatch.setenv("OPENCODE_PORT", "4096")
        with patch("governance_runtime.infrastructure.opencode_server_client.post_json") as mock_post, \
             patch("governance_runtime.infrastructure.opencode_server_client.resolve_session_id") as mock_resolve:
            mock_post.return_value = {"info": {}}
            send_session_prompt("Hello", session_id="explicit-sess-3")
            mock_resolve.assert_not_called()

    def test_none_session_id_falls_through_to_resolve(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """session_id=None (default) uses resolve_session_id()."""
        monkeypatch.setenv("OPENCODE_PORT", "4096")
        monkeypatch.setenv("OPENCODE_SESSION_ID", "from-resolve")
        with patch("governance_runtime.infrastructure.opencode_server_client.post_json") as mock:
            mock.return_value = {"info": {}}
            send_session_prompt("Hello")  # session_id not passed
            call_url = mock.call_args[0][0]
            assert "/session/from-resolve/message" in call_url

    def test_empty_string_session_id_falls_through(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """session_id='' (falsy) falls through to resolve_session_id()."""
        monkeypatch.setenv("OPENCODE_PORT", "4096")
        monkeypatch.setenv("OPENCODE_SESSION_ID", "from-resolve")
        with patch("governance_runtime.infrastructure.opencode_server_client.post_json") as mock:
            mock.return_value = {"info": {}}
            send_session_prompt("Hello", session_id="")
            call_url = mock.call_args[0][0]
            assert "/session/from-resolve/message" in call_url


# ── Performance: env var path should NOT trigger file I/O ────────────

@pytest.mark.governance
class TestResolveSessionIdPerformance:
    """When OPENCODE_SESSION_ID env var is set, resolve_session_id() must
    NOT call _read_hydrated_session_id_from_state() — no file I/O on the
    hot path."""

    def test_env_var_set_no_file_read(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENCODE_SESSION_ID", "fast-sess")
        with patch(
            "governance_runtime.infrastructure.opencode_server_client._read_hydrated_session_id_from_state"
        ) as mock_read:
            resolve_session_id()
            mock_read.assert_not_called()

    def test_env_var_unset_triggers_file_read(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Without env var, the fallback MUST be attempted."""
        monkeypatch.delenv("OPENCODE_SESSION_ID", raising=False)
        with patch(
            "governance_runtime.infrastructure.opencode_server_client._read_hydrated_session_id_from_state",
            return_value="fallback-sess",
        ) as mock_read:
            resolve_session_id()
            mock_read.assert_called_once()


# ── Integration-style: full chain from hydration through resolution ──

@pytest.mark.governance
class TestSessionIdResolutionChain:
    """Integration-style tests simulating the full resolution chain."""

    def test_chain_source_1_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Source 1 (env) → returns immediately, no fallback attempted."""
        monkeypatch.setenv("OPENCODE_SESSION_ID", "src1")
        sid, ev = resolve_session_id()
        assert sid == "src1"
        assert ev["session_id_source"] == "OPENCODE_SESSION_ID"

    def test_chain_source_2_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Source 1 empty → Source 2 (state) → returns."""
        monkeypatch.delenv("OPENCODE_SESSION_ID", raising=False)
        with patch(
            "governance_runtime.infrastructure.opencode_server_client._read_hydrated_session_id_from_state",
            return_value="src2",
        ):
            sid, ev = resolve_session_id()
        assert sid == "src2"
        assert ev["session_id_source"] == "SESSION_STATE.SessionHydration"

    def test_chain_all_fail_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """All sources empty → APIError."""
        monkeypatch.delenv("OPENCODE_SESSION_ID", raising=False)
        with patch(
            "governance_runtime.infrastructure.opencode_server_client._read_hydrated_session_id_from_state",
            return_value=None,
        ):
            with pytest.raises(APIError):
                resolve_session_id()

    def test_chain_state_exception_falls_to_source_3(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """If state read raises, _read_hydrated_session_id_from_state returns None,
        so resolve_session_id falls through to source 3 (fail-closed)."""
        monkeypatch.delenv("OPENCODE_SESSION_ID", raising=False)
        # Don't mock _read_hydrated_session_id_from_state — let it try to
        # resolve_active_session_paths which will fail in test env
        with pytest.raises(APIError):
            resolve_session_id()
