"""Runtime import authority conformance (R3 hard guardrail)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GOVERNANCE_RUNTIME = REPO_ROOT / "governance_runtime"


def _scan_governance_runtime_legacy_imports() -> list[tuple[str, str]]:
    """Return all imports from governance.* inside governance_runtime/**."""
    matches: list[tuple[str, str]] = []
    pattern = re.compile(r"^(?:from|import)\s+(governance\.[^\s;]+)", re.MULTILINE)

    for py_file in GOVERNANCE_RUNTIME.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        content = py_file.read_text(encoding="utf-8")
        rel_path = str(py_file.relative_to(REPO_ROOT))
        for m in pattern.finditer(content):
            matches.append((rel_path, m.group(1)))
    return matches


@pytest.mark.conformance
class TestRuntimeImportAuthority:
    """R3 guardrails for runtime authority and decoupling."""

    def test_governance_runtime_exists(self) -> None:
        assert GOVERNANCE_RUNTIME.is_dir(), "governance_runtime/ must exist"

    def test_runtime_has_zero_legacy_governance_imports(self) -> None:
        legacy = _scan_governance_runtime_legacy_imports()
        assert not legacy, (
            "R3 requires zero governance.* imports from governance_runtime/**. "
            f"Found {len(legacy)} edges: {legacy[:20]}"
        )

    def test_runtime_canonical_modules_exist(self) -> None:
        required = [
            GOVERNANCE_RUNTIME / "paths.py",
            GOVERNANCE_RUNTIME / "infrastructure" / "plan_record_state.py",
            GOVERNANCE_RUNTIME / "infrastructure" / "write_policy.py",
            GOVERNANCE_RUNTIME / "infrastructure" / "repo_root_resolver.py",
            GOVERNANCE_RUNTIME / "infrastructure" / "pack_lock.py",
        ]
        missing = [str(p.relative_to(REPO_ROOT)) for p in required if not p.exists()]
        assert not missing, f"Missing canonical runtime modules: {missing}"
