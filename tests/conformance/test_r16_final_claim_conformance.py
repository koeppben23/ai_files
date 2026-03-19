from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.mark.conformance
class TestR16FinalClaimConformance:
    def test_architecture_runtime_is_canonical_and_legacy_is_passive(self) -> None:
        runtime_root = REPO_ROOT / "governance_runtime"
        legacy_import = re.compile(r"^(?:from|import)\s+(governance\.[^\s;]+)", re.MULTILINE)
        legacy_dynamic_import = re.compile(r"importlib\.import_module\(\s*[\"']governance\.")
        legacy_module_launcher = re.compile(r"-m\s+governance\.")
        offenders: list[str] = []
        for py in runtime_root.rglob("*.py"):
            if py.name == "__init__.py":
                continue
            text = _read(py)
            if legacy_import.search(text):
                offenders.append(py.relative_to(REPO_ROOT).as_posix())
            if legacy_dynamic_import.search(text):
                offenders.append(py.relative_to(REPO_ROOT).as_posix())
            if legacy_module_launcher.search(text):
                offenders.append(py.relative_to(REPO_ROOT).as_posix())
        assert not offenders, f"runtime canonicality broken by legacy import edges: {offenders}"

        plugin = _read(REPO_ROOT / "governance" / "artifacts" / "opencode-plugins" / "audit-new-session.mjs")
        assert "governance_runtime.entrypoints.new_work_session" in plugin
        assert "governance.entrypoints.new_work_session" not in plugin

        bootstrap_surfaces = [
            REPO_ROOT / "governance" / "artifacts" / "opencode-plugins" / "audit-new-session.mjs",
            REPO_ROOT / "governance_runtime" / "bin" / "opencode-governance-bootstrap",
            REPO_ROOT / "governance_runtime" / "bin" / "opencode-governance-bootstrap.cmd",
        ]
        for surface in bootstrap_surfaces:
            text = _read(surface)
            assert "-m governance." not in text, (
                f"legacy module launcher must not appear in active bootstrap surface: {surface.relative_to(REPO_ROOT)}"
            )

    def test_command_surface_has_exact_rail_count(self) -> None:
        rails_dir = REPO_ROOT / "opencode" / "commands"
        rails = sorted(p.name for p in rails_dir.glob("*.md"))
        assert len(rails) == 8, f"expected 8 rails, found {len(rails)}: {rails}"

    def test_install_layout_split_is_present_and_forbidden_command_targets_removed(self) -> None:
        installer = _read(REPO_ROOT / "governance_runtime" / "install" / "install.py")

        required_tokens = [
            'config_root / "commands"',
            'config_root / OPENCODE_PLUGINS_DIR_NAME',
            'config_root / "workspaces"',
            'config_root / "bin"',
            'local_root / "governance_runtime"',
            'local_root / "governance_content"',
            'local_root / "governance_spec"',
            'local_root / "governance"',
            'plan.local_root / "VERSION"',
        ]
        for token in required_tokens:
            assert token in installer, f"installer missing layout token: {token}"

        forbidden_active_targets = [
            'config_root / "commands" / "governance"',
            'config_root / "commands" / "cli"',
            'config_root / "commands" / "docs"',
            'config_root / "commands" / "scripts"',
            'config_root / "commands" / "templates"',
        ]
        for token in forbidden_active_targets:
            assert token not in installer, f"forbidden commands payload target still active in installer: {token}"

        strict_allowlist_tokens = [
            "CANONICAL_RAIL_FILENAMES",
            'GOVERNANCE_PATHS_NAME',
            'MANIFEST_NAME',
            'allowed_names = set(CANONICAL_RAIL_FILENAMES) | {GOVERNANCE_PATHS_NAME, MANIFEST_NAME}',
        ]
        for token in strict_allowlist_tokens:
            assert token in installer, f"installer missing strict commands allowlist token: {token}"

    def test_logs_are_workspace_only_and_not_commands_logs(self) -> None:
        global_handler = _read(REPO_ROOT / "governance_runtime" / "infrastructure" / "logging" / "global_error_handler.py")
        kernel = _read(REPO_ROOT / "governance_runtime" / "kernel" / "phase_kernel.py")

        assert 'cmd_path / "logs"' not in global_handler
        assert "commands_flow" not in kernel
        assert "commands_boot" not in kernel

    def test_contract_liveness_no_planned_or_tbd_live_metadata(self) -> None:
        contracts_root = REPO_ROOT / "governance_content" / "docs" / "contracts"
        offenders: list[str] = []
        for md in sorted(contracts_root.glob("*.md")):
            text = _read(md)
            rel = md.relative_to(REPO_ROOT).as_posix()
            if re.search(r"^status:\s*planned\b", text, re.MULTILINE | re.IGNORECASE):
                offenders.append(f"{rel}: status=planned")
            if re.search(r"^effective_version:\s*TBD\b", text, re.MULTILINE | re.IGNORECASE):
                offenders.append(f"{rel}: effective_version=TBD")
            if re.search(r"^conformance_suite:\s*TBD\b", text, re.MULTILINE | re.IGNORECASE):
                offenders.append(f"{rel}: conformance_suite=TBD")
        assert not offenders, f"live contract metadata drift detected: {offenders}"

    def test_ux_bootstrap_truth_is_consistent(self) -> None:
        docs = [
            REPO_ROOT / "README.md",
            REPO_ROOT / "README-OPENCODE.md",
            REPO_ROOT / "QUICKSTART.md",
            REPO_ROOT / "BOOTSTRAP.md",
            REPO_ROOT / "governance_content" / "README.md",
            REPO_ROOT / "governance_content" / "README-OPENCODE.md",
            REPO_ROOT / "governance_content" / "QUICKSTART.md",
        ]

        for path in docs:
            text = _read(path)
            assert "opencode-governance-bootstrap init --profile" in text, (
                f"canonical bootstrap command missing in {path.relative_to(REPO_ROOT)}"
            )
            assert "python -m governance" not in text
            assert "python -m governance_runtime" not in text
            assert ".config/opencode" in text
            assert ".local/opencode" in text
            assert ("~/.config/opencode/bin" in text) or ("${CONFIG_ROOT}/bin" in text), (
                f"canonical bin truth missing in {path.relative_to(REPO_ROOT)}"
            )

    def test_hygiene_no_cache_bytecode_or_pytest_cache_artifacts(self) -> None:
        result = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=str(REPO_ROOT),
            check=True,
            text=False,
            capture_output=True,
        )
        entries = [p.decode("utf-8", errors="replace") for p in result.stdout.split(b"\x00") if p]

        offenders = [
            rel
            for rel in entries
            if "__pycache__/" in rel or rel.endswith(".pyc") or "/.pytest_cache/" in rel or rel.startswith(".pytest_cache/")
        ]
        assert not offenders, f"cache/bytecode artifacts must not exist in repo paths: {sorted(offenders)}"
