"""R4a hard verification for legacy sunset readiness."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LEGACY_ROOT = REPO_ROOT / "governance"
RUNTIME_ROOT = REPO_ROOT / "governance_runtime"


def _runtime_legacy_import_edges() -> list[tuple[str, str]]:
    edges: list[tuple[str, str]] = []
    pattern = re.compile(r"^(?:from|import)\s+(governance\.[^\s;]+)", re.MULTILINE)
    for py_file in RUNTIME_ROOT.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        content = py_file.read_text(encoding="utf-8")
        rel = py_file.relative_to(REPO_ROOT).as_posix()
        for m in pattern.finditer(content):
            edges.append((rel, m.group(1)))
    return edges


def _legacy_bridge_only_files() -> list[str]:
    """Return governance/*.py files that are strict runtime compatibility bridges.

    Bridge-only file criteria:
    - has at least one import from governance_runtime.*
    - contains no active logic (`def` / `class`) in file body
    """
    out: list[str] = []
    runtime_import = re.compile(r"^\s*(?:from|import)\s+governance_runtime\.", re.MULTILINE)
    active_logic = re.compile(r"^\s*(?:def|class)\s+", re.MULTILINE)
    for py_file in LEGACY_ROOT.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        content = py_file.read_text(encoding="utf-8")
        if runtime_import.search(content) and not active_logic.search(content):
            out.append(py_file.relative_to(REPO_ROOT).as_posix())
    return sorted(out)


@pytest.mark.conformance
class TestR4aLegacySunsetReadiness:
    def test_runtime_has_zero_legacy_imports(self) -> None:
        edges = _runtime_legacy_import_edges()
        assert not edges, (
            "R4a hard verification failed: governance_runtime/** must not import governance.*. "
            f"Found {len(edges)} edges: {edges[:20]}"
        )

    def test_legacy_has_bridge_only_surface(self) -> None:
        bridges = _legacy_bridge_only_files()
        assert bridges, "Expected at least one bridge-only file under governance/**"

    def test_r4a_readiness_report_exists(self) -> None:
        report = REPO_ROOT / "governance_spec" / "migrations" / "R4a_Legacy_Sunset_Readiness.md"
        assert report.exists(), "R4a readiness report must exist"
