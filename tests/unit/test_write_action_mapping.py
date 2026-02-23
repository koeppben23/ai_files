from pathlib import Path

from adapters.filesystem.atomic_write import atomic_write_action
from kernel.domain.models.write_action import is_written


def test_write_action_not_written_for_read_only() -> None:
    action = atomic_write_action(Path("/tmp/x"), "x", read_only=True)
    assert is_written(action) is False


def test_write_action_not_written_for_dry_run() -> None:
    action = atomic_write_action(Path("/tmp/x"), "x", dry_run=True)
    assert is_written(action) is False
