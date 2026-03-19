from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
F100_RECORD = REPO_ROOT / "governance_spec" / "migrations" / "F100_Completion_Gate.md"


def _record_text() -> str:
    assert F100_RECORD.exists(), "F100 completion record must exist"
    return F100_RECORD.read_text(encoding="utf-8")


@pytest.mark.conformance
class TestF100CompletionGate:
    def test_required_records_exist(self) -> None:
        required = [
            REPO_ROOT / "governance_spec" / "migrations" / "R4a_Legacy_Sunset_Readiness.md",
            REPO_ROOT / "governance_spec" / "migrations" / "R4b_Legacy_Sunset_Delete_Preparation.md",
            REPO_ROOT / "governance_spec" / "migrations" / "R5_R10_Hardening_and_Readiness.md",
            REPO_ROOT / "governance_spec" / "migrations" / "R10_Final_State_Proof.md",
            F100_RECORD,
        ]
        missing = [str(p.relative_to(REPO_ROOT)) for p in required if not p.exists()]
        assert not missing, f"Missing completion records: {missing}"

    def test_record_references_all_canonical_gate_suites(self) -> None:
        text = _record_text()
        required = [
            "tests/conformance/test_f100_runtime_purity_gate.py",
            "tests/conformance/test_f100_workspace_logs_only.py",
            "tests/conformance/test_contract_liveness_conformance.py",
            "tests/conformance/test_installer_ssot_conformance.py",
            "tests/conformance/test_r10_final_state_proof.py",
            "tests/conformance/test_r10_final_readiness_gate.py",
        ]
        missing = [suite for suite in required if suite not in text]
        assert not missing, f"F100 record missing canonical gate suites: {missing}"

    def test_runtime_has_zero_legacy_import_edges(self) -> None:
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
        assert not edges, f"F100 completion failed: runtime has legacy import edges: {edges[:20]}"

    def test_root_installer_is_thin_delegator(self) -> None:
        root_install = (REPO_ROOT / "install.py").read_text(encoding="utf-8")
        assert "import governance_runtime.install.install as _impl" in root_install
        assert "_runtime_main = _impl.main" in root_install
        assert "--source-dir" in root_install

    def test_no_planned_or_tbd_contract_frontmatter(self) -> None:
        contracts = REPO_ROOT / "governance_content" / "docs" / "contracts"
        offenders: list[str] = []
        for md in sorted(contracts.glob("*.md")):
            text = md.read_text(encoding="utf-8")
            rel = md.relative_to(REPO_ROOT).as_posix()
            if re.search(r"^status:\s*planned\b", text, re.MULTILINE | re.IGNORECASE):
                offenders.append(f"{rel}: status=planned")
            if re.search(r"^effective_version:\s*TBD\b", text, re.MULTILINE | re.IGNORECASE):
                offenders.append(f"{rel}: effective_version=TBD")
            if re.search(r"^conformance_suite:\s*TBD\b", text, re.MULTILINE | re.IGNORECASE):
                offenders.append(f"{rel}: conformance_suite=TBD")
        assert not offenders, f"F100 completion failed: live contract metadata drift: {offenders}"
