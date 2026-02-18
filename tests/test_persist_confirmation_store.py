from __future__ import annotations

from pathlib import Path

import pytest

from governance.infrastructure.persist_confirmation_store import (
    has_persist_confirmation,
    load_persist_confirmation_evidence,
    record_persist_confirmation,
)


@pytest.mark.governance
def test_persist_confirmation_store_records_and_loads_user_confirmation(tmp_path: Path):
    evidence = tmp_path / "workspaces" / "abc" / "evidence" / "persist_confirmations.json"
    result = record_persist_confirmation(
        evidence_path=evidence,
        scope="workspace-memory",
        gate="phase5",
        value="YES",
        mode="user",
        reason="operator-confirmed",
    )
    assert result.ok is True

    payload = load_persist_confirmation_evidence(evidence_path=evidence)
    assert has_persist_confirmation(payload, scope="workspace-memory", gate="phase5", value="YES") is True


@pytest.mark.governance
def test_persist_confirmation_store_blocks_pipeline_recording(tmp_path: Path):
    evidence = tmp_path / "workspaces" / "abc" / "evidence" / "persist_confirmations.json"
    result = record_persist_confirmation(
        evidence_path=evidence,
        scope="workspace-memory",
        gate="phase5",
        value="YES",
        mode="pipeline",
        reason="pipeline-run",
    )
    assert result.ok is False
    assert result.reason_code == "PERSIST_DISALLOWED_IN_PIPELINE"
