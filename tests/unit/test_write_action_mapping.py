from pathlib import Path

from governance.domain.models.write_action import WriteAction, is_written, to_file_status
from governance.infrastructure.adapters.filesystem.atomic_write import atomic_write_action


def test_write_action_not_written_for_read_only() -> None:
    action = atomic_write_action(Path("/mock/x"), "x", read_only=True)
    assert is_written(action) is False


def test_write_action_not_written_for_dry_run() -> None:
    action = atomic_write_action(Path("/mock/x"), "x", dry_run=True)
    assert is_written(action) is False


def test_write_action_status_mapping_covers_all_outcomes() -> None:
    assert to_file_status(WriteAction(path="/mock/a", outcome="written", bytes_written=1)) == "written"
    assert to_file_status(WriteAction(path="/mock/a", outcome="overwritten", bytes_written=1)) == "written"
    assert to_file_status(WriteAction(path="/mock/a", outcome="appended", bytes_written=1)) == "written"
    assert to_file_status(WriteAction(path="/mock/a", outcome="kept", bytes_written=0)) == "unchanged"
    assert to_file_status(WriteAction(path="/mock/a", outcome="normalized", bytes_written=0)) == "unchanged"
    assert to_file_status(WriteAction(path="/mock/a", outcome="skipped_read_only", bytes_written=0)) == "blocked-read-only"
    assert to_file_status(WriteAction(path="/mock/a", outcome="blocked-read-only", bytes_written=0)) == "blocked-read-only"
    assert to_file_status(WriteAction(path="/mock/a", outcome="skipped_dry_run", bytes_written=0)) == "write-requested"
    assert to_file_status(WriteAction(path="/mock/a", outcome="error", bytes_written=0)) == "failed"
    assert to_file_status(WriteAction(path="/mock/a", outcome="failed", bytes_written=0)) == "failed"
    assert to_file_status(WriteAction(path="/mock/a", outcome="unmapped", bytes_written=0)) == "unknown"
