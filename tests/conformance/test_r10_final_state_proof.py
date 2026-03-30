"""R10 final state proof: explicit end-state invariants and compatibility surface."""

from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
LEGACY_ROOT = REPO_ROOT / "governance"
RUNTIME_ROOT = REPO_ROOT / "governance_runtime"
R10_PROOF_PATH = REPO_ROOT / "governance_spec" / "migrations" / "R10_Final_State_Proof.md"


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


def _legacy_classification() -> tuple[set[str], set[str], set[str]]:
    if not LEGACY_ROOT.exists():
        return set(), set(), set()
    runtime_import = re.compile(r"^\s*(?:from|import)\s+governance_runtime\.", re.MULTILINE)
    active_logic = re.compile(r"^\s*(?:def|class)\s+", re.MULTILINE)

    bridge_files: set[str] = set()
    active_files: set[str] = set()
    non_pure_bridges: set[str] = set()

    for py_file in LEGACY_ROOT.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        content = py_file.read_text(encoding="utf-8")
        rel = py_file.relative_to(REPO_ROOT).as_posix()
        if runtime_import.search(content):
            bridge_files.add(rel)
            if active_logic.search(content):
                non_pure_bridges.add(rel)
        else:
            active_files.add(rel)

    return bridge_files, active_files, non_pure_bridges


def _load_frozen_compatibility_surface() -> set[str]:
    text = R10_PROOF_PATH.read_text(encoding="utf-8")
    section_match = re.search(
        r"## Explicit Active Compatibility Surface\n(?P<section>.*?)(?:\n## |\Z)",
        text,
        re.DOTALL,
    )
    assert section_match, "R10 proof missing compatibility surface section"
    section = section_match.group("section")
    paths = set(re.findall(r"^- `([^`]+)`\s*$", section, re.MULTILINE))
    assert paths, "R10 proof compatibility surface section is empty"
    return paths


def _load_recorded_count(label: str) -> int:
    text = R10_PROOF_PATH.read_text(encoding="utf-8")
    m = re.search(rf"{re.escape(label)}: \*\*(\d+)\*\*", text)
    assert m, f"R10 proof missing count line for: {label}"
    return int(m.group(1))


@pytest.mark.conformance
class TestR10FinalStateProof:
    def test_runtime_has_zero_legacy_imports(self) -> None:
        edges = _runtime_legacy_import_edges()
        assert not edges, f"runtime must have zero governance.* imports, found: {edges[:20]}"

    def test_legacy_compatibility_surface_is_explicit_and_stable(self) -> None:
        if not LEGACY_ROOT.exists():
            assert not LEGACY_ROOT.exists()
            return
        _, active_files, _ = _legacy_classification()
        frozen = _load_frozen_compatibility_surface()
        assert active_files == frozen, (
            "Active compatibility surface drifted from frozen R10 proof. "
            f"unexpected={sorted(active_files - frozen)} "
            f"missing={sorted(frozen - active_files)}"
        )

    def test_frozen_surface_record_counts_match_current_snapshot(self) -> None:
        bridge_files, active_files, _ = _legacy_classification()
        runtime_edges = _runtime_legacy_import_edges()

        assert _load_recorded_count("governance_runtime/** legacy import edges") == len(runtime_edges)
        assert _load_recorded_count("governance/** bridge files (legacy -> runtime)") == len(bridge_files)
        assert _load_recorded_count("governance/** explicit active compatibility surface files") == len(active_files)

    def test_legacy_bridges_are_logic_free(self) -> None:
        if not LEGACY_ROOT.exists():
            assert not LEGACY_ROOT.exists()
            return
        _, _, non_pure = _legacy_classification()
        assert not non_pure, f"non-pure legacy bridges remain: {sorted(non_pure)}"

    def test_core_end_state_invariants(self) -> None:
        commands = REPO_ROOT / "opencode" / "commands"
        assert commands.is_dir()
        assert len(list(commands.glob("*.md"))) == 9

        assert (REPO_ROOT / "governance_content" / "reference" / "master.md").exists()
        assert (REPO_ROOT / "governance_spec" / "phase_api.yaml").exists()
        assert (REPO_ROOT / "governance_runtime" / "VERSION").exists()
        assert (REPO_ROOT / "governance_runtime" / "install" / "install.py").exists()

    def test_version_and_installer_contracts_are_hard(self) -> None:
        canonical_version = (REPO_ROOT / "governance_runtime" / "VERSION").read_text(encoding="utf-8").strip()
        assert re.fullmatch(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?", canonical_version)

        for candidate in [REPO_ROOT / "VERSION", REPO_ROOT / "governance_runtime" / "VERSION"]:
            if candidate.exists():
                assert candidate.read_text(encoding="utf-8").strip() == canonical_version

        root_install = (REPO_ROOT / "install.py").read_text(encoding="utf-8")
        runtime_install = (REPO_ROOT / "governance_runtime" / "install" / "install.py").read_text(encoding="utf-8")
        for token in ["import governance_runtime.install.install as _impl", "--source-dir"]:
            assert token in root_install
        for token in [
            "GOVERNANCE_PATHS_SCHEMA",
            "def _write_python_binding_file(",
            "OPENCODE_JSON_NAME",
            "PYTHON_BINDING",
            "opencode-governance.paths.v1",
            "def _launcher_template_unix(",
            "def _launcher_template_windows(",
        ]:
            assert token in runtime_install

    def test_workspace_logs_only_write_targets(self) -> None:
        handler = (REPO_ROOT / "governance_runtime" / "infrastructure" / "logging" / "global_error_handler.py").read_text(encoding="utf-8")
        assert "cmd_path / \"logs\"" not in handler

        runtime_installer = (REPO_ROOT / "governance_runtime" / "install" / "install.py").read_text(encoding="utf-8")
        assert "<config_root>/commands/logs" not in runtime_installer

    def test_no_planned_or_tbd_live_contracts(self) -> None:
        contracts_root = REPO_ROOT / "governance_content" / "docs" / "contracts"
        offenders: list[str] = []
        for md in contracts_root.rglob("*.md"):
            text = md.read_text(encoding="utf-8")
            if re.search(r"^status:\s*planned\b", text, re.MULTILINE | re.IGNORECASE):
                offenders.append(md.relative_to(REPO_ROOT).as_posix())
            if re.search(r"^effective_version:\s*TBD\b", text, re.MULTILINE | re.IGNORECASE):
                offenders.append(md.relative_to(REPO_ROOT).as_posix())
            if re.search(r"^conformance_suite:\s*TBD\b", text, re.MULTILINE | re.IGNORECASE):
                offenders.append(md.relative_to(REPO_ROOT).as_posix())
        assert not offenders, f"planned/TBD live contracts remain: {sorted(set(offenders))}"
