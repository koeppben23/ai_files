"""R10 final completion gate for restplan closure."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.conformance
class TestR10FinalCompletionGate:
    def test_required_migration_records_exist(self) -> None:
        required = [
            REPO_ROOT / "governance_spec" / "migrations" / "R4a_Legacy_Sunset_Readiness.md",
            REPO_ROOT / "governance_spec" / "migrations" / "R4b_Legacy_Sunset_Delete_Preparation.md",
            REPO_ROOT / "governance_spec" / "migrations" / "R5_R10_Completion.md",
        ]
        missing = [str(p.relative_to(REPO_ROOT)) for p in required if not p.exists()]
        assert not missing, f"Missing required migration records: {missing}"

    def test_canonical_runtime_roots_exist(self) -> None:
        required_dirs = [
            REPO_ROOT / "governance_runtime" / "application",
            REPO_ROOT / "governance_runtime" / "domain",
            REPO_ROOT / "governance_runtime" / "engine",
            REPO_ROOT / "governance_runtime" / "infrastructure",
            REPO_ROOT / "governance_runtime" / "kernel",
        ]
        missing = [str(p.relative_to(REPO_ROOT)) for p in required_dirs if not p.is_dir()]
        assert not missing, f"Missing canonical runtime roots: {missing}"
