"""R4b conformance: legacy bridge purity and runtime authority."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LEGACY_ROOT = REPO_ROOT / "governance"
RUNTIME_ROOT = REPO_ROOT / "governance_runtime"


def _runtime_legacy_import_edges() -> list[tuple[str, str]]:
    edges: list[tuple[str, str]] = []
    pat = re.compile(r"^(?:from|import)\s+(governance\.[^\s;]+)", re.MULTILINE)
    for py_file in RUNTIME_ROOT.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        content = py_file.read_text(encoding="utf-8")
        rel = py_file.relative_to(REPO_ROOT).as_posix()
        for m in pat.finditer(content):
            edges.append((rel, m.group(1)))
    return edges


def _non_pure_legacy_bridges() -> list[str]:
    runtime_import = re.compile(r"^\s*(?:from|import)\s+governance_runtime\.", re.MULTILINE)
    active_logic = re.compile(r"^\s*(?:def|class)\s+", re.MULTILINE)

    offenders: list[str] = []
    for py_file in LEGACY_ROOT.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        content = py_file.read_text(encoding="utf-8")
        if runtime_import.search(content) and active_logic.search(content):
            offenders.append(py_file.relative_to(REPO_ROOT).as_posix())
    return sorted(offenders)


@pytest.mark.conformance
class TestR4bLegacyBridgePurity:
    def test_runtime_has_zero_legacy_imports(self) -> None:
        edges = _runtime_legacy_import_edges()
        assert not edges, (
            "R4b requires governance_runtime/** to stay fully decoupled from governance_runtime.*. "
            f"Found {len(edges)} edges: {edges[:20]}"
        )

    def test_legacy_bridges_are_logic_free(self) -> None:
        offenders = _non_pure_legacy_bridges()
        assert not offenders, (
            "Legacy bridge files must not contain active logic. "
            f"Offenders: {offenders}"
        )

    def test_r4b_delete_preparation_report_exists(self) -> None:
        report = REPO_ROOT / "governance_spec" / "migrations" / "R4b_Legacy_Sunset_Delete_Preparation.md"
        assert report.exists(), "R4b delete-preparation report must exist"
