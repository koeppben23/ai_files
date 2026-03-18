"""R10 final readiness gate for restplan closure."""

from __future__ import annotations

from pathlib import Path
import re

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.conformance
class TestR10FinalReadinessGate:
    def test_required_migration_records_exist(self) -> None:
        required = [
            REPO_ROOT / "governance_spec" / "migrations" / "R4a_Legacy_Sunset_Readiness.md",
            REPO_ROOT / "governance_spec" / "migrations" / "R4b_Legacy_Sunset_Delete_Preparation.md",
            REPO_ROOT / "governance_spec" / "migrations" / "R5_R10_Hardening_and_Readiness.md",
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

    def test_runtime_imports_have_no_legacy_governance_edges(self) -> None:
        pat = re.compile(r"^(?:from|import)\s+(governance\.[^\s;]+)", re.MULTILINE)
        edges: list[tuple[str, str]] = []
        runtime = REPO_ROOT / "governance_runtime"
        for py_file in runtime.rglob("*.py"):
            if py_file.name == "__init__.py":
                continue
            text = py_file.read_text(encoding="utf-8")
            rel = py_file.relative_to(REPO_ROOT).as_posix()
            for m in pat.finditer(text):
                edges.append((rel, m.group(1)))
        assert not edges, f"R10 gate failed: runtime contains governance.* imports: {edges[:20]}"

    def test_legacy_runtime_bridges_are_logic_free(self) -> None:
        runtime_bridge_pat = re.compile(r"^\s*(?:from|import)\s+governance_runtime\.", re.MULTILINE)
        active_logic_pat = re.compile(r"^\s*(?:def|class)\s+", re.MULTILINE)
        offenders: list[str] = []
        for py_file in (REPO_ROOT / "governance").rglob("*.py"):
            if py_file.name == "__init__.py":
                continue
            text = py_file.read_text(encoding="utf-8")
            if runtime_bridge_pat.search(text) and active_logic_pat.search(text):
                offenders.append(py_file.relative_to(REPO_ROOT).as_posix())
        assert not offenders, f"R10 gate failed: non-pure legacy bridges remain: {offenders}"

    def test_root_installer_and_canonical_keep_critical_contracts(self) -> None:
        root_install = REPO_ROOT / "install.py"
        canonical_install = REPO_ROOT / "governance_runtime" / "install" / "install.py"
        assert root_install.exists(), "install.py compatibility installer must exist"
        assert canonical_install.exists(), "canonical runtime installer must exist"
        content = root_install.read_text(encoding="utf-8")
        canonical = canonical_install.read_text(encoding="utf-8")
        for token in [
            "OPENCODE_JSON_NAME",
            "PYTHON_BINDING",
            "def _write_python_binding_file(",
            "def _launcher_template_unix(",
            "def _launcher_template_windows(",
        ]:
            assert token in content, f"Root installer missing critical contract token: {token}"
            assert token in canonical, f"Canonical installer missing critical contract token: {token}"
