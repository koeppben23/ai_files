from __future__ import annotations

from pathlib import Path

import pytest

from governance.engine.reason_codes import BLOCKED_STATE_OUTDATED, REASON_CODE_NONE
from governance.engine.session_state_repository import (
    CURRENT_SESSION_STATE_VERSION,
    SessionStateRepository,
    migrate_session_state_document,
)


def _session_state_doc(*, version: int = CURRENT_SESSION_STATE_VERSION, ruleset_hash: str = "hash-a") -> dict:
    """Build a minimal valid SESSION_STATE document for repository tests."""

    return {
        "SESSION_STATE": {
            "session_state_version": version,
            "ruleset_hash": ruleset_hash,
            "Phase": "1.1-Bootstrap",
            "Mode": "OK",
            "Next": "none",
        }
    }


@pytest.mark.governance
def test_session_state_repository_roundtrip(tmp_path: Path):
    """Repository should persist and load JSON deterministically."""

    path = tmp_path / "workspaces" / "abc" / "SESSION_STATE.json"
    repo = SessionStateRepository(path)
    doc = _session_state_doc()
    repo.save(doc)
    loaded = repo.load()
    assert loaded == doc


@pytest.mark.governance
def test_session_state_repository_load_returns_none_when_missing(tmp_path: Path):
    """Missing session files should return None instead of raising."""

    repo = SessionStateRepository(tmp_path / "missing" / "SESSION_STATE.json")
    assert repo.load() is None


@pytest.mark.governance
def test_migration_stub_updates_ruleset_hash_and_records_metadata():
    """Current-version documents should accept deterministic hash refresh migration."""

    doc = _session_state_doc(version=CURRENT_SESSION_STATE_VERSION, ruleset_hash="hash-old")
    result = migrate_session_state_document(
        doc,
        target_version=CURRENT_SESSION_STATE_VERSION,
        target_ruleset_hash="hash-new",
    )
    assert result.success is True
    assert result.reason_code == REASON_CODE_NONE
    migrated = result.document["SESSION_STATE"]
    assert migrated["ruleset_hash"] == "hash-new"
    assert migrated["Migration"]["fromVersion"] == CURRENT_SESSION_STATE_VERSION
    assert migrated["Migration"]["toVersion"] == CURRENT_SESSION_STATE_VERSION
    assert migrated["Migration"]["rollbackAvailable"] is True


@pytest.mark.governance
def test_migration_stub_is_noop_when_hash_is_already_current():
    """Migration should be a no-op when version and ruleset hash are current."""

    doc = _session_state_doc(version=CURRENT_SESSION_STATE_VERSION, ruleset_hash="hash-current")
    result = migrate_session_state_document(
        doc,
        target_version=CURRENT_SESSION_STATE_VERSION,
        target_ruleset_hash="hash-current",
    )
    assert result.success is True
    assert result.reason_code == REASON_CODE_NONE
    assert result.document == doc


@pytest.mark.governance
def test_migration_stub_fails_closed_for_unsupported_version():
    """Outdated versions should fail closed until explicit migrations exist."""

    doc = _session_state_doc(version=CURRENT_SESSION_STATE_VERSION - 1)
    result = migrate_session_state_document(
        doc,
        target_version=CURRENT_SESSION_STATE_VERSION,
        target_ruleset_hash="hash-current",
    )
    assert result.success is False
    assert result.reason_code == BLOCKED_STATE_OUTDATED
    assert "unsupported session_state_version" in result.detail


@pytest.mark.governance
def test_migration_stub_fails_closed_for_missing_session_state_object():
    """Malformed documents should fail closed with outdated-state reason."""

    result = migrate_session_state_document(
        {},
        target_version=CURRENT_SESSION_STATE_VERSION,
        target_ruleset_hash="hash-current",
    )
    assert result.success is False
    assert result.reason_code == BLOCKED_STATE_OUTDATED
