from __future__ import annotations

import errno
from pathlib import Path

import pytest

from governance.engine.reason_codes import BLOCKED_STATE_OUTDATED, REASON_CODE_NONE
from governance.engine import session_state_repository as session_repo_module
from governance.engine.session_state_repository import (
    CURRENT_SESSION_STATE_VERSION,
    ROLLOUT_PHASE_DUAL_READ,
    SessionStateRepository,
    migrate_session_state_document,
    session_state_hash,
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
    assert loaded is not None
    assert loaded["SESSION_STATE"]["ruleset_hash"] == doc["SESSION_STATE"]["ruleset_hash"]


@pytest.mark.governance
def test_session_state_repository_load_returns_none_when_missing(tmp_path: Path):
    """Missing session files should return None instead of raising."""

    repo = SessionStateRepository(tmp_path / "missing" / "SESSION_STATE.json")
    assert repo.load() is None


@pytest.mark.governance
def test_session_state_repository_save_is_atomic_and_replaces_existing_file(tmp_path: Path):
    """Atomic save should replace existing file content in one final write step."""

    path = tmp_path / "workspaces" / "abc" / "SESSION_STATE.json"
    repo = SessionStateRepository(path)
    repo.save(_session_state_doc(ruleset_hash="hash-a"))
    repo.save(_session_state_doc(ruleset_hash="hash-b"))
    loaded = repo.load()
    assert loaded is not None
    assert loaded["SESSION_STATE"]["ruleset_hash"] == "hash-b"
    leftover = list(path.parent.glob("SESSION_STATE.json.*.tmp"))
    assert leftover == []


@pytest.mark.governance
def test_session_state_repository_retries_replace_on_transient_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Atomic save should retry replace on retryable transient filesystem errors."""

    path = tmp_path / "workspaces" / "abc" / "SESSION_STATE.json"
    repo = SessionStateRepository(path)
    original_replace = session_repo_module.os.replace
    calls = {"count": 0}

    def flaky_replace(src: str, dst: str) -> None:
        calls["count"] += 1
        if calls["count"] == 1:
            raise OSError(errno.EACCES, "transient lock")
        original_replace(src, dst)

    monkeypatch.setattr(session_repo_module.os, "replace", flaky_replace)
    repo.save(_session_state_doc(ruleset_hash="hash-retry"))
    loaded = repo.load()
    assert loaded is not None
    assert loaded["SESSION_STATE"]["ruleset_hash"] == "hash-retry"
    assert calls["count"] >= 2


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


@pytest.mark.governance
def test_dual_read_maps_legacy_repo_model_into_canonical_repo_map_digest(tmp_path: Path):
    """Dual-read should map legacy RepoModel alias to canonical RepoMapDigest."""

    path = tmp_path / "workspaces" / "abc" / "SESSION_STATE.json"
    repo = SessionStateRepository(path)
    legacy = _session_state_doc()
    legacy["SESSION_STATE"]["RepoModel"] = {"components": ["engine", "packs"]}
    repo.save(legacy)
    loaded = repo.load()
    assert loaded is not None
    assert loaded["SESSION_STATE"]["RepoMapDigest"] == {"components": ["engine", "packs"]}
    assert "migration_events" in loaded["SESSION_STATE"]


@pytest.mark.governance
def test_dual_read_maps_legacy_fast_path_aliases_into_fast_path_evaluation(tmp_path: Path):
    """Dual-read should synthesize canonical FastPathEvaluation from legacy fields."""

    path = tmp_path / "workspaces" / "abc" / "SESSION_STATE.json"
    repo = SessionStateRepository(path)
    legacy = _session_state_doc()
    legacy["SESSION_STATE"]["FastPath"] = True
    legacy["SESSION_STATE"]["FastPathReason"] = "legacy reason"
    repo.save(legacy)
    loaded = repo.load()
    assert loaded is not None
    evaluation = loaded["SESSION_STATE"]["FastPathEvaluation"]
    assert evaluation["Evaluated"] is True
    assert evaluation["Eligible"] is True
    assert evaluation["Applied"] is True
    assert evaluation["Reason"] == "legacy reason"


@pytest.mark.governance
def test_write_only_new_drops_legacy_alias_fields(tmp_path: Path):
    """Repository writes should keep canonical fields and drop legacy aliases."""

    path = tmp_path / "workspaces" / "abc" / "SESSION_STATE.json"
    repo = SessionStateRepository(path)
    legacy = _session_state_doc()
    legacy["SESSION_STATE"]["RepoModel"] = {"legacy": True}
    legacy["SESSION_STATE"]["FastPath"] = False
    legacy["SESSION_STATE"]["FastPathReason"] = "legacy"
    repo.save(legacy)

    persisted = session_repo_module.json.loads(path.read_text(encoding="utf-8"))
    state = persisted["SESSION_STATE"]
    assert "RepoModel" not in state
    assert "FastPath" not in state
    assert "FastPathReason" not in state
    assert "RepoMapDigest" in state
    assert "FastPathEvaluation" in state
    assert isinstance(state.get("migration_events"), list) and state["migration_events"]


@pytest.mark.governance
def test_dual_read_keeps_canonical_repo_map_digest_when_legacy_alias_also_present(tmp_path: Path):
    """Canonical RepoMapDigest should win if both legacy and canonical fields exist."""

    path = tmp_path / "workspaces" / "abc" / "SESSION_STATE.json"
    repo = SessionStateRepository(path)
    doc = _session_state_doc()
    doc["SESSION_STATE"]["RepoModel"] = {"legacy": True}
    doc["SESSION_STATE"]["RepoMapDigest"] = {"canonical": True}
    repo.save(doc)
    loaded = repo.load()
    assert loaded is not None
    assert loaded["SESSION_STATE"]["RepoMapDigest"] == {"canonical": True}


@pytest.mark.governance
def test_session_state_hash_is_equal_for_legacy_and_canonical_equivalent_documents():
    """Legacy aliases and canonical equivalents should hash identically."""

    legacy = _session_state_doc()
    legacy["SESSION_STATE"]["RepoModel"] = {"components": ["a"]}
    legacy["SESSION_STATE"]["FastPath"] = True
    legacy["SESSION_STATE"]["FastPathReason"] = "legacy"

    canonical = _session_state_doc()
    canonical["SESSION_STATE"]["RepoMapDigest"] = {"components": ["a"]}
    canonical["SESSION_STATE"]["FastPathEvaluation"] = {
        "Evaluated": True,
        "Eligible": True,
        "Applied": True,
        "Reason": "legacy",
        "Preconditions": {},
        "DenyReasons": [],
        "ReducedDiscoveryScope": {"PathsScanned": [], "Skipped": []},
        "EvidenceRefs": [],
    }

    assert session_state_hash(legacy) == session_state_hash(canonical)


@pytest.mark.governance
def test_dual_read_save_then_load_is_idempotent_for_legacy_input(tmp_path: Path):
    """Legacy input should converge to a stable canonical representation."""

    path = tmp_path / "workspaces" / "abc" / "SESSION_STATE.json"
    repo = SessionStateRepository(path, rollout_phase=ROLLOUT_PHASE_DUAL_READ)
    legacy = _session_state_doc()
    legacy["SESSION_STATE"]["RepoModel"] = {"x": 1}
    legacy["SESSION_STATE"]["FastPath"] = False
    legacy["SESSION_STATE"]["FastPathReason"] = "legacy"

    repo.save(legacy)
    first = repo.load()
    assert first is not None
    repo.save(first)
    second = repo.load()
    assert second is not None
    # ignore appended migration event timestamps for idempotence comparison
    first_state = session_repo_module.json.loads(session_repo_module.json.dumps(first["SESSION_STATE"]))
    second_state = session_repo_module.json.loads(session_repo_module.json.dumps(second["SESSION_STATE"]))
    first_state["migration_events"] = []
    second_state["migration_events"] = []
    assert first_state == second_state


@pytest.mark.governance
def test_rollout_phase_flag_can_disable_dual_read_normalization(tmp_path: Path):
    """Rollout phase guardrail keeps phase-1 behavior explicit and opt-in."""

    path = tmp_path / "workspaces" / "abc" / "SESSION_STATE.json"
    repo = SessionStateRepository(path, rollout_phase=2)
    legacy = _session_state_doc()
    legacy["SESSION_STATE"]["RepoModel"] = {"legacy": True}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(session_repo_module.json.dumps(legacy), encoding="utf-8")
    loaded = repo.load()
    assert loaded is not None
    assert "RepoMapDigest" not in loaded["SESSION_STATE"]
    assert loaded["SESSION_STATE"]["RepoModel"] == {"legacy": True}
