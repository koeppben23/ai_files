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
    """Staging activation should keep rollbackable previous pointer and audit event."""

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
    assert lifecycle["previous"]["version"] == "1.1.0"
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
    assert lifecycle["previous"] == {}
    assert lifecycle["audit_trail"][-1]["type"] == "automatic_rollback_skipped"
