from __future__ import annotations

from pathlib import Path

import pytest

from governance_runtime.paths.canonical import ensure_absolute_no_traversal, validate_no_traversal


@pytest.mark.governance
def test_validate_no_traversal_does_not_use_prefix_match(tmp_path: Path) -> None:
    base = tmp_path / "base"
    candidate = tmp_path / "baseX" / "file.txt"
    assert validate_no_traversal(candidate, base) is False


@pytest.mark.governance
def test_ensure_absolute_no_traversal_rejects_parent_walk() -> None:
    with pytest.raises(ValueError):
        ensure_absolute_no_traversal(Path("/mock/a/../b"))
