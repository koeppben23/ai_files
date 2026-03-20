from __future__ import annotations

from pathlib import Path

import pytest

from governance_runtime.infrastructure.path_contract import PathTraversalError, normalize_absolute_path


@pytest.mark.governance
def test_validate_no_traversal_does_not_use_prefix_match(tmp_path: Path) -> None:
    with pytest.raises(PathTraversalError):
        normalize_absolute_path(str(tmp_path / "baseX" / ".." / "file.txt"), purpose="test-path")


@pytest.mark.governance
def test_ensure_absolute_no_traversal_rejects_parent_walk() -> None:
    with pytest.raises(PathTraversalError):
        normalize_absolute_path("/mock/a/../b", purpose="test-path")
