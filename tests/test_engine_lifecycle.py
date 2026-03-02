from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timezone

import pytest

from governance.engine.lifecycle import rollback_engine_activation, stage_engine_activation


def _load(path: Path) -> dict[str, object]:
    """Load JSON helper for lifecycle tests."""

    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.governance
def test_stage_engine_activation_records_previous_pointer_and_audit(tmp_path: Path):
    """Staging activation should keep rollbackable previous stack and audit event."""

    paths_file = tmp_path / "commands" / "governance.paths.json"
    stage_engine_activation(
        paths_file=paths_file,
        engine_version="1.1.0",
        engine_sha256="sha-1",
        ruleset_hash="ruleset-1",
        now_utc=datetime(2026, 2, 11, 10, 0, tzinfo=timezone.utc),
    )
    stage_engine_activation(
        paths_file=paths_file,
        engine_version="1.2.0",
        engine_sha256="sha-2",
        ruleset_hash="ruleset-2",
        now_utc=datetime(2026, 2, 11, 10, 5, tzinfo=timezone.utc),
    )

    payload = _load(paths_file)
    lifecycle = payload["engineLifecycle"]
    assert lifecycle["active"]["version"] == "1.2.0"
    assert len(lifecycle["previous_stack"]) == 1
    assert lifecycle["previous_stack"][0]["version"] == "1.1.0"
    assert lifecycle["audit_trail"][-1]["type"] == "activation_staged"


@pytest.mark.governance
def test_rollback_engine_activation_restores_previous_and_writes_deviation_audit(tmp_path: Path):
    """Automatic rollback should restore previous pointer and emit DEVIATION audit."""

    paths_file = tmp_path / "commands" / "governance.paths.json"
    stage_engine_activation(
        paths_file=paths_file,
        engine_version="1.1.0",
        engine_sha256="sha-1",
        ruleset_hash="ruleset-1",
        now_utc=datetime(2026, 2, 11, 10, 0, tzinfo=timezone.utc),
    )
    stage_engine_activation(
        paths_file=paths_file,
        engine_version="1.2.0",
        engine_sha256="sha-2",
        ruleset_hash="ruleset-2",
        now_utc=datetime(2026, 2, 11, 10, 5, tzinfo=timezone.utc),
    )

    rollback_engine_activation(
        paths_file=paths_file,
        trigger="hash/integrity mismatch",
        now_utc=datetime(2026, 2, 11, 10, 6, tzinfo=timezone.utc),
    )

    payload = _load(paths_file)
    lifecycle = payload["engineLifecycle"]
    assert lifecycle["active"]["version"] == "1.1.0"
    assert len(lifecycle["previous_stack"]) == 0
    audit = lifecycle["audit_trail"][-1]
    assert audit["type"] == "automatic_rollback"
    assert audit["trigger"] == "hash/integrity mismatch"
    assert audit["deviation"]["type"] == "DEVIATION"


@pytest.mark.governance
def test_rollback_without_previous_pointer_is_audited_and_non_destructive(tmp_path: Path):
    """Rollback without previous pointer should be audited and keep active pointer."""

    paths_file = tmp_path / "commands" / "governance.paths.json"
    stage_engine_activation(
        paths_file=paths_file,
        engine_version="1.1.0",
        engine_sha256="sha-1",
        ruleset_hash="ruleset-1",
        now_utc=datetime(2026, 2, 11, 10, 0, tzinfo=timezone.utc),
    )

    rollback_engine_activation(
        paths_file=paths_file,
        trigger="startup crash loop",
        now_utc=datetime(2026, 2, 11, 10, 1, tzinfo=timezone.utc),
    )

    payload = _load(paths_file)
    lifecycle = payload["engineLifecycle"]
    assert lifecycle["active"]["version"] == "1.1.0"
    assert lifecycle["previous_stack"] == []
    assert lifecycle["audit_trail"][-1]["type"] == "automatic_rollback_skipped"


@pytest.mark.governance
def test_rollback_depth_three_push_three_pop_three(tmp_path: Path):
    """Stack depth=3: push 3 activations, then pop 2 rollbacks (third has empty stack)."""

    paths_file = tmp_path / "commands" / "governance.paths.json"

    for i in range(3):
        stage_engine_activation(
            paths_file=paths_file,
            engine_version=f"1.{i}.0",
            engine_sha256=f"sha-{i}",
            ruleset_hash=f"ruleset-{i}",
            now_utc=datetime(2026, 2, 11, 10, i, tzinfo=timezone.utc),
        )

    payload = _load(paths_file)
    lifecycle = payload["engineLifecycle"]
    assert lifecycle["active"]["version"] == "1.2.0"
    assert len(lifecycle["previous_stack"]) == 2

    for i in range(3):
        rollback_engine_activation(
            paths_file=paths_file,
            trigger=f"rollback-{i}",
            now_utc=datetime(2026, 2, 11, 11, i, tzinfo=timezone.utc),
        )

    payload = _load(paths_file)
    lifecycle = payload["engineLifecycle"]
    assert lifecycle["active"]["version"] == "1.0.0"
    assert len(lifecycle["previous_stack"]) == 0


@pytest.mark.governance
def test_rollback_depth_overflow_drops_oldest(tmp_path: Path):
    """Stack beyond MAX_ROLLBACK_DEPTH drops oldest entry."""

    from governance.engine.lifecycle import MAX_ROLLBACK_DEPTH

    paths_file = tmp_path / "commands" / "governance.paths.json"

    for i in range(MAX_ROLLBACK_DEPTH + 2):
        stage_engine_activation(
            paths_file=paths_file,
            engine_version=f"1.{i}.0",
            engine_sha256=f"sha-{i}",
            ruleset_hash=f"ruleset-{i}",
            now_utc=datetime(2026, 2, 11, 10, i, tzinfo=timezone.utc),
        )

    payload = _load(paths_file)
    lifecycle = payload["engineLifecycle"]
    assert len(lifecycle["previous_stack"]) == MAX_ROLLBACK_DEPTH


@pytest.mark.governance
def test_audit_trail_records_all_rollbacks(tmp_path: Path):
    """Audit trail records all successful rollbacks (skips when stack empty)."""

    paths_file = tmp_path / "commands" / "governance.paths.json"

    for i in range(3):
        stage_engine_activation(
            paths_file=paths_file,
            engine_version=f"1.{i}.0",
            engine_sha256=f"sha-{i}",
            ruleset_hash=f"ruleset-{i}",
            now_utc=datetime(2026, 2, 11, 10, i, tzinfo=timezone.utc),
        )

    for i in range(3):
        rollback_engine_activation(
            paths_file=paths_file,
            trigger=f"trigger-{i}",
            now_utc=datetime(2026, 2, 11, 11, i, tzinfo=timezone.utc),
        )

    payload = _load(paths_file)
    lifecycle = payload["engineLifecycle"]
    rollbacks = [e for e in lifecycle["audit_trail"] if e["type"] == "automatic_rollback"]
    assert len(rollbacks) == 2
    assert rollbacks[0]["trigger"] == "trigger-0"
    assert rollbacks[1]["trigger"] == "trigger-1"
    skipped = [e for e in lifecycle["audit_trail"] if e["type"] == "automatic_rollback_skipped"]
    assert len(skipped) == 1
    assert skipped[0]["trigger"] == "trigger-2"


@pytest.mark.governance
def test_legacy_previous_dict_converts_to_stack(tmp_path: Path):
    """Legacy 'previous' dict auto-converts to stack on first load."""

    paths_file = tmp_path / "commands" / "governance.paths.json"
    paths_file.parent.mkdir(parents=True)

    paths_file.write_text(
        json.dumps({
            "paths": {},
            "engineLifecycle": {
                "active": {"version": "2.0.0", "sha256": "new-sha", "ruleset_hash": "new-hash"},
                "previous": {"version": "1.0.0", "sha256": "old-sha", "ruleset_hash": "old-hash"},
                "audit_trail": []
            }
        })
    )

    stage_engine_activation(
        paths_file=paths_file,
        engine_version="3.0.0",
        engine_sha256="newest-sha",
        ruleset_hash="newest-hash",
        now_utc=datetime(2026, 2, 11, 12, 0, tzinfo=timezone.utc),
    )

    payload = _load(paths_file)
    lifecycle = payload["engineLifecycle"]
    assert "previous_stack" in lifecycle
    assert len(lifecycle["previous_stack"]) == 2
    assert lifecycle["previous_stack"][0]["version"] == "1.0.0"
    assert lifecycle["previous_stack"][1]["version"] == "2.0.0"
    assert "previous" not in lifecycle
