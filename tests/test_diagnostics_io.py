from __future__ import annotations

from diagnostics.io.actions import WriteAction, derive_file_status
from diagnostics.io.atomic_write import atomic_write_text
from routing.gates import check_persistence_gate


def test_atomic_write_text_reports_create_then_overwrite(tmp_path):
    target = tmp_path / "example.txt"

    first = atomic_write_text(target, "first\n")
    second = atomic_write_text(target, "second\n")

    assert first.success is True
    assert first.action == WriteAction.CREATE
    assert derive_file_status(first) == "created"

    assert second.success is True
    assert second.action == WriteAction.OVERWRITE
    assert derive_file_status(second) == "overwritten"


def test_persistence_gate_accepts_top_level_state_flags():
    result = check_persistence_gate(
        {
            "PersistenceCommitted": True,
            "WorkspaceReadyGateCommitted": True,
            "WorkspaceArtifactsCommitted": True,
            "PointerVerified": True,
        }
    )

    assert result.passed is True


def test_persistence_gate_accepts_commitflags_state_shape():
    result = check_persistence_gate(
        {
            "CommitFlags": {
                "PersistenceCommitted": True,
                "WorkspaceReadyGateCommitted": True,
                "WorkspaceArtifactsCommitted": True,
                "PointerVerified": True,
            }
        }
    )

    assert result.passed is True
