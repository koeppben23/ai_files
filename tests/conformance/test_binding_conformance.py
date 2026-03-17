"""Conformance tests for python-binding-contract.v1.

Tests validate the Single Python Binding Authority across all runtime
components: installer (binding writer), launcher (fail-closed consumer),
plugin (PYTHON_BINDING reader with degraded fallback), and rails
(stable launcher name, no embedded Python paths).

Paths:
  Happy  – nominal expectations hold on the current source tree
  Corner – boundary conditions (empty binding, stale path, edge formats)
  Edge   – cross-platform path separators, POSIX normalization
  Bad    – contract violations that MUST be detected
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from tests.util import REPO_ROOT, get_docs_path

CONTRACT_PATH = get_docs_path() / "contracts" / "python-binding-contract.v1.md"
INSTALL_PATH = REPO_ROOT / "install.py"
PLUGIN_PATH = (
    REPO_ROOT / "governance" / "artifacts" / "opencode-plugins" / "audit-new-session.mjs"
)
THIS_FILE_REL = "tests/conformance/test_binding_conformance.py"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_frontmatter(path: Path) -> dict:
    """Extract YAML frontmatter from a Markdown file."""
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?\n)---", text, re.DOTALL)
    assert m, f"No YAML frontmatter found in {path}"
    return yaml.safe_load(m.group(1))


def _read_source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Contract-Ref Validation
# ---------------------------------------------------------------------------


@pytest.mark.conformance
class TestContractRefValidation:
    """Validate that the contract document itself is well-formed."""

    def test_happy_contract_file_exists(self) -> None:
        """Happy: Contract document exists on disk."""
        assert CONTRACT_PATH.is_file(), f"Contract not found: {CONTRACT_PATH}"

    def test_happy_frontmatter_is_parseable(self) -> None:
        """Happy: YAML frontmatter can be parsed without errors."""
        fm = _parse_frontmatter(CONTRACT_PATH)
        assert isinstance(fm, dict)

    def test_happy_frontmatter_has_required_keys(self) -> None:
        """Happy: Frontmatter contains all standardised keys."""
        fm = _parse_frontmatter(CONTRACT_PATH)
        required = {
            "contract",
            "version",
            "status",
            "scope",
            "owner",
            "effective_version",
            "supersedes",
            "conformance_suite",
        }
        missing = required - set(fm.keys())
        assert not missing, f"Frontmatter missing keys: {missing}"

    def test_happy_conformance_suite_points_to_this_file(self) -> None:
        """Happy: conformance_suite frontmatter points to this test file."""
        fm = _parse_frontmatter(CONTRACT_PATH)
        assert fm["conformance_suite"] == THIS_FILE_REL

    def test_happy_contract_status_is_active(self) -> None:
        """Happy: Contract status is active."""
        fm = _parse_frontmatter(CONTRACT_PATH)
        assert fm["status"] == "active"

    def test_happy_contract_owner_is_install_py(self) -> None:
        """Happy: Contract owner is install.py."""
        fm = _parse_frontmatter(CONTRACT_PATH)
        assert fm["owner"] == "install.py"

    def test_happy_contract_version_v1(self) -> None:
        """Happy: Contract version is v1."""
        fm = _parse_frontmatter(CONTRACT_PATH)
        assert fm["version"] == "v1"


# ---------------------------------------------------------------------------
# §1 Core Policy: Single Binding Authority
# ---------------------------------------------------------------------------


@pytest.mark.conformance
class TestCorePolicySingleBinding:
    """Validate that the codebase enforces a single binding authority."""

    def test_happy_installer_is_sole_binding_writer(self) -> None:
        """Happy: Only install.py writes governance.paths.json and PYTHON_BINDING."""
        install_src = _read_source(INSTALL_PATH)
        assert "PYTHON_BINDING" in install_src
        assert "governance.paths.json" in install_src

    def test_happy_installer_writes_python_binding_file(self) -> None:
        """Happy: install.py defines _write_python_binding_file function."""
        install_src = _read_source(INSTALL_PATH)
        assert "def _write_python_binding_file(" in install_src

    def test_happy_installer_determination_cascade(self) -> None:
        """Happy: Installer uses OPENCODE_PYTHON → sys.executable cascade (§1.3)."""
        install_src = _read_source(INSTALL_PATH)
        assert "OPENCODE_PYTHON" in install_src
        assert "sys.executable" in install_src

    def test_bad_plugin_does_not_write_binding_files(self) -> None:
        """Bad: Plugin must NEVER write to PYTHON_BINDING or governance.paths.json."""
        plugin_src = _read_source(PLUGIN_PATH)
        assert "writeFileSync" not in plugin_src
        assert "writeFile" not in plugin_src


# ---------------------------------------------------------------------------
# §2 Binding Artifacts
# ---------------------------------------------------------------------------


@pytest.mark.conformance
class TestBindingArtifacts:
    """Validate binding artifact definitions and write semantics."""

    def test_happy_governance_paths_json_schema_constant(self) -> None:
        """Happy: install.py defines the governance.paths schema identifier."""
        install_src = _read_source(INSTALL_PATH)
        assert "opencode-governance.paths.v1" in install_src

    def test_happy_python_command_in_governance_paths(self) -> None:
        """Happy: build_governance_paths_payload includes pythonCommand field."""
        install_src = _read_source(INSTALL_PATH)
        assert '"pythonCommand"' in install_src

    def test_happy_python_binding_file_is_posix_path(self) -> None:
        """Happy: _write_python_binding_file uses .as_posix() for path format."""
        install_src = _read_source(INSTALL_PATH)
        # The function must normalize with .as_posix()
        fn_match = re.search(
            r"def _write_python_binding_file\(.*?\n(.*?)(?=\ndef |\Z)",
            install_src,
            re.DOTALL,
        )
        assert fn_match, "_write_python_binding_file function not found"
        fn_body = fn_match.group(1)
        assert ".as_posix()" in fn_body, "PYTHON_BINDING must use POSIX-normalized path"

    def test_happy_python_binding_file_single_line(self) -> None:
        """Happy: _write_python_binding_file writes content + newline (single line)."""
        install_src = _read_source(INSTALL_PATH)
        fn_match = re.search(
            r"def _write_python_binding_file\(.*?\n(.*?)(?=\ndef |\Z)",
            install_src,
            re.DOTALL,
        )
        assert fn_match
        fn_body = fn_match.group(1)
        # Should write posix_path + "\n" — one line with trailing newline
        assert '+ "\\n"' in fn_body or "+ '\\n'" in fn_body, (
            "PYTHON_BINDING must be written as single line with trailing newline"
        )


# ---------------------------------------------------------------------------
# §3 Launcher Python Resolution (fail-closed)
# ---------------------------------------------------------------------------


@pytest.mark.conformance
class TestLauncherResolution:
    """Validate launcher resolution cascade (§3): baked → PYTHON_BINDING → fail-closed."""

    def test_happy_unix_launcher_has_baked_python_bin(self) -> None:
        """Happy: Unix launcher template bakes PYTHON_BIN at install time."""
        install_src = _read_source(INSTALL_PATH)
        # In source, the f-string uses escaped quotes: PYTHON_BIN=\"{python_exe}\"
        assert "PYTHON_BIN" in install_src
        fn_match = re.search(
            r"def _launcher_template_unix\(.*?\n(.*?)(?=\ndef |\Z)",
            install_src,
            re.DOTALL,
        )
        assert fn_match, "_launcher_template_unix not found"
        fn_body = fn_match.group(1)
        assert "PYTHON_BIN" in fn_body, "Unix launcher must bake PYTHON_BIN"

    def test_happy_unix_launcher_reads_python_binding_fallback(self) -> None:
        """Happy: Unix launcher reads PYTHON_BINDING as secondary fallback."""
        install_src = _read_source(INSTALL_PATH)
        assert "PYTHON_BINDING" in install_src
        # Launcher reads the file with: read -r PYTHON_BIN < BINDING_FILE
        assert "read -r PYTHON_BIN" in install_src or "BINDING_FILE" in install_src

    def test_happy_unix_launcher_fail_closed(self) -> None:
        """Happy: Unix launcher exits 1 when both paths fail (no PATH probing)."""
        install_src = _read_source(INSTALL_PATH)
        # Must have exit 1 path, NOT a fallback to python3/python
        fn_match = re.search(
            r"def _launcher_template_unix\(.*?\n(.*?)(?=\ndef |\Z)",
            install_src,
            re.DOTALL,
        )
        assert fn_match, "_launcher_template_unix not found"
        fn_body = fn_match.group(1)
        assert "exit 1" in fn_body, "Unix launcher must fail-closed with exit 1"
        # Must NOT fall back to python3 or python probing
        assert "which python" not in fn_body, "Unix launcher must not probe python via which"

    def test_happy_windows_launcher_fail_closed(self) -> None:
        """Happy: Windows launcher exits /b 1 when both paths fail."""
        install_src = _read_source(INSTALL_PATH)
        fn_match = re.search(
            r"def _launcher_template_windows\(.*?\n(.*?)(?=\ndef |\Z)",
            install_src,
            re.DOTALL,
        )
        assert fn_match, "_launcher_template_windows not found"
        fn_body = fn_match.group(1)
        assert "exit /b 1" in fn_body, "Windows launcher must fail-closed with exit /b 1"

    def test_happy_launcher_exports_opencode_python(self) -> None:
        """Happy: Launcher exports OPENCODE_PYTHON on successful resolution (§3.3)."""
        install_src = _read_source(INSTALL_PATH)
        assert "OPENCODE_PYTHON" in install_src
        # Unix: export OPENCODE_PYTHON
        assert 'export OPENCODE_PYTHON' in install_src

    def test_bad_launcher_no_silent_path_probing(self) -> None:
        """Bad: Launcher must NEVER silently fall back to PATH-based probing."""
        install_src = _read_source(INSTALL_PATH)
        # Extract both launcher template functions
        for fn_name in ["_launcher_template_unix", "_launcher_template_windows"]:
            fn_match = re.search(
                rf"def {fn_name}\(.*?\n(.*?)(?=\ndef |\Z)",
                install_src,
                re.DOTALL,
            )
            assert fn_match, f"{fn_name} not found"
            fn_body = fn_match.group(1)
            # Should not contain python3/python probing
            assert "canRun" not in fn_body, f"{fn_name} must not probe python via canRun"
            assert "which python3" not in fn_body, f"{fn_name} must not probe via 'which'"


# ---------------------------------------------------------------------------
# §4.1/§4.2 Launcher Subcommands + Rails Invocation
# ---------------------------------------------------------------------------


@pytest.mark.conformance
class TestRailsBindingCompliance:
    """Validate rails invoke launcher by stable name, never embed Python paths (§4.2)."""

    RAIL_FILES = ["continue.md", "review.md", "audit-readout.md", "plan.md", "ticket.md", "review-decision.md", "implement.md"]

    def test_happy_rails_use_launcher_stable_name(self) -> None:
        """Happy: All rails reference opencode-governance-bootstrap."""
        for fname in self.RAIL_FILES:
            path = REPO_ROOT / fname
            if not path.exists():
                continue
            content = _read_source(path)
            assert "opencode-governance-bootstrap" in content, (
                f"{fname} must invoke launcher by stable name"
            )

    def test_happy_rails_use_bin_dir_placeholder_or_inline_path(self) -> None:
        """Happy: Rails use {{BIN_DIR}} placeholder or PATH= inline prefix."""
        for fname in self.RAIL_FILES:
            path = REPO_ROOT / fname
            if not path.exists():
                continue
            content = _read_source(path)
            has_placeholder = "{{BIN_DIR}}" in content
            has_inline_path = "PATH=" in content
            assert has_placeholder or has_inline_path, (
                f"{fname} must use BIN_DIR placeholder or inline PATH="
            )

    def test_bad_rails_do_not_embed_absolute_python_paths(self) -> None:
        """Bad: Rails must NOT contain absolute Python interpreter paths."""
        python_patterns = [
            r"/usr/bin/python",
            r"/usr/local/bin/python",
            r"C:\\Python",
            r"C:/Python",
            r"python3\.exe",
            r"python\.exe",
        ]
        for fname in self.RAIL_FILES:
            path = REPO_ROOT / fname
            if not path.exists():
                continue
            content = _read_source(path)
            for pattern in python_patterns:
                assert not re.search(pattern, content, re.IGNORECASE), (
                    f"{fname} embeds absolute Python path matching: {pattern}"
                )

    def test_bad_rails_do_not_use_python_m_directly(self) -> None:
        """Bad: Rails must invoke launcher, not 'python -m' directly."""
        for fname in self.RAIL_FILES:
            path = REPO_ROOT / fname
            if not path.exists():
                continue
            content = _read_source(path)
            # Should not have python -m or python3 -m (without being inside a comment)
            direct_python_m = re.search(
                r"(?:python3?|py)\s+-m\s+governance\.", content
            )
            assert not direct_python_m, (
                f"{fname} directly invokes 'python -m governance...'; "
                "must use launcher opencode-governance-bootstrap"
            )


# ---------------------------------------------------------------------------
# §4.3 Plugin Resolution Cascade
# ---------------------------------------------------------------------------


@pytest.mark.conformance
class TestPluginBindingCompliance:
    """Validate plugin follows python-binding-contract.v1 §4.3."""

    def test_happy_plugin_has_resolve_binding_file(self) -> None:
        """Happy: Plugin defines resolveBindingFile function."""
        src = _read_source(PLUGIN_PATH)
        assert "function resolveBindingFile()" in src

    def test_happy_plugin_reads_python_binding_file(self) -> None:
        """Happy: Plugin reads PYTHON_BINDING via readFileSync."""
        src = _read_source(PLUGIN_PATH)
        assert "readFileSync" in src
        assert "PYTHON_BINDING" in src

    def test_happy_plugin_resolution_order(self) -> None:
        """Happy: Plugin resolution order: OPENCODE_PYTHON → PYTHON_BINDING → PATH (§4.3)."""
        src = _read_source(PLUGIN_PATH)
        fn_start = src.find("function resolvePython()")
        assert fn_start > 0, "resolvePython function not found"

        # Search only within resolvePython function body
        env_pos = src.find("OPENCODE_PYTHON", fn_start)
        binding_pos = src.find("resolveBindingFile()", fn_start)
        # Use "degraded PATH probing" to avoid matching the 'degraded' field
        # in the resolveBindingFile helper that precedes resolvePython
        degraded_pos = src.find("degraded PATH probing", fn_start)

        assert env_pos > 0, "OPENCODE_PYTHON check must exist in resolvePython"
        assert binding_pos > 0, "resolveBindingFile() call must exist in resolvePython"
        assert degraded_pos > 0, "degraded PATH probing comment must exist in resolvePython"
        assert env_pos < binding_pos < degraded_pos, (
            "Plugin resolution must follow: OPENCODE_PYTHON → PYTHON_BINDING → degraded"
        )

    def test_happy_plugin_marks_degraded_fallback(self) -> None:
        """Happy: PATH probing results carry degraded=true flag."""
        src = _read_source(PLUGIN_PATH)
        assert "degraded: true" in src
        assert "degraded: false" in src

    def test_happy_plugin_logs_degraded_warning(self) -> None:
        """Happy: Plugin logs a warning when using degraded fallback (§4.3 note)."""
        src = _read_source(PLUGIN_PATH)
        assert "degraded PATH fallback" in src

    def test_corner_plugin_handles_empty_binding(self) -> None:
        """Corner: Plugin rejects empty PYTHON_BINDING files."""
        src = _read_source(PLUGIN_PATH)
        assert "PYTHON_BINDING empty" in src

    def test_corner_plugin_handles_multiline_binding(self) -> None:
        """Corner: Plugin rejects multi-line PYTHON_BINDING files."""
        src = _read_source(PLUGIN_PATH)
        assert "multi-line" in src

    def test_edge_plugin_converts_posix_to_native_on_windows(self) -> None:
        """Edge: Plugin converts POSIX slashes to backslashes on Windows."""
        src = _read_source(PLUGIN_PATH)
        fn_start = src.find("function resolvePython()")
        assert fn_start > 0
        fn_body = src[fn_start:]
        assert "win32" in fn_body
        assert "replace(" in fn_body

    def test_bad_plugin_never_writes_binding_artifacts(self) -> None:
        """Bad: Plugin must not write to filesystem (read-only consumer)."""
        src = _read_source(PLUGIN_PATH)
        # Only appendFileSync for debug logging is allowed
        assert "writeFileSync" not in src
        assert "writeFile(" not in src


# ---------------------------------------------------------------------------
# §5 Installer Responsibilities — Write Order + Consistency
# ---------------------------------------------------------------------------


@pytest.mark.conformance
class TestInstallerWriteOrder:
    """Validate installer write order and consistency invariants (§5)."""

    def test_happy_governance_paths_written_before_launcher(self) -> None:
        """Happy: governance.paths.json is written before launcher generation (§5.1)."""
        install_src = _read_source(INSTALL_PATH)
        # The install flow must write governance.paths.json SSOT before launchers
        paths_fn_pos = install_src.find("def install_governance_paths_file(")
        launcher_fn_pos = install_src.find("def _write_launcher_wrappers(")
        assert paths_fn_pos > 0, "install_governance_paths_file not found"
        assert launcher_fn_pos > 0, "_write_launcher_wrappers not found"

    def test_happy_python_binding_written_in_launcher_wrappers(self) -> None:
        """Happy: PYTHON_BINDING is written as part of launcher wrapper generation."""
        install_src = _read_source(INSTALL_PATH)
        fn_match = re.search(
            r"def _write_launcher_wrappers\(.*?\n(.*?)(?=\ndef |\Z)",
            install_src,
            re.DOTALL,
        )
        assert fn_match, "_write_launcher_wrappers not found"
        fn_body = fn_match.group(1)
        assert "_write_python_binding_file" in fn_body, (
            "PYTHON_BINDING must be written during launcher wrapper generation"
        )

    def test_happy_consistency_invariant_documented(self) -> None:
        """Happy: Contract documents the three-way consistency invariant (§5.2)."""
        contract_text = _read_source(CONTRACT_PATH)
        assert "governance.paths.json:paths.pythonCommand" in contract_text
        assert "PYTHON_BINDING" in contract_text
        assert "PYTHON_BIN" in contract_text


# ---------------------------------------------------------------------------
# §6 Path Format — POSIX Normalization
# ---------------------------------------------------------------------------


@pytest.mark.conformance
class TestPathFormat:
    """Validate POSIX-normalized path format across binding artifacts (§6)."""

    def test_happy_installer_uses_posix_for_binding_file(self) -> None:
        """Happy: _write_python_binding_file uses .as_posix() normalization."""
        install_src = _read_source(INSTALL_PATH)
        fn_match = re.search(
            r"def _write_python_binding_file\(.*?\n(.*?)(?=\ndef |\Z)",
            install_src,
            re.DOTALL,
        )
        assert fn_match
        fn_body = fn_match.group(1)
        assert "as_posix()" in fn_body

    def test_happy_installer_uses_path_for_json_normalization(self) -> None:
        """Happy: install.py defines _path_for_json for consistent path serialization."""
        install_src = _read_source(INSTALL_PATH)
        assert "def _path_for_json(" in install_src

    def test_happy_path_for_json_uses_posix(self) -> None:
        """Happy: _path_for_json outputs POSIX-normalized paths."""
        install_src = _read_source(INSTALL_PATH)
        fn_match = re.search(
            r"def _path_for_json\(.*?\n(.*?)(?=\ndef |\Z)",
            install_src,
            re.DOTALL,
        )
        assert fn_match
        fn_body = fn_match.group(1)
        assert "as_posix()" in fn_body


# ---------------------------------------------------------------------------
# §7 Failure Modes — Contract-documented error handling
# ---------------------------------------------------------------------------


@pytest.mark.conformance
class TestFailureModes:
    """Validate failure mode handling documented in §7."""

    def test_happy_launcher_has_clear_error_message(self) -> None:
        """Happy: Launcher outputs clear error when no interpreter found."""
        install_src = _read_source(INSTALL_PATH)
        assert "No valid Python interpreter found" in install_src or (
            "FATAL" in install_src and "Python" in install_src
        )

    def test_happy_plugin_skips_when_no_python(self) -> None:
        """Happy: Plugin logs and skips when no Python found (§7 row 4)."""
        src = _read_source(PLUGIN_PATH)
        assert "no python interpreter found" in src

    def test_happy_plugin_binding_empty_treated_as_missing(self) -> None:
        """Happy: Plugin treats empty PYTHON_BINDING as missing (§7 row 3)."""
        src = _read_source(PLUGIN_PATH)
        assert "PYTHON_BINDING empty" in src


# ---------------------------------------------------------------------------
# Cross-component consistency (integration)
# ---------------------------------------------------------------------------


@pytest.mark.conformance
class TestCrossComponentConsistency:
    """Validate cross-component wiring between all binding consumers."""

    def test_happy_all_consumers_reference_python_binding(self) -> None:
        """Happy: All 3 consumer types reference PYTHON_BINDING."""
        install_src = _read_source(INSTALL_PATH)
        plugin_src = _read_source(PLUGIN_PATH)

        assert "PYTHON_BINDING" in install_src, "Installer must reference PYTHON_BINDING"
        assert "PYTHON_BINDING" in plugin_src, "Plugin must reference PYTHON_BINDING"

    def test_happy_all_consumers_reference_opencode_python_env(self) -> None:
        """Happy: All consumers check OPENCODE_PYTHON env var."""
        install_src = _read_source(INSTALL_PATH)
        plugin_src = _read_source(PLUGIN_PATH)

        assert "OPENCODE_PYTHON" in install_src
        assert "OPENCODE_PYTHON" in plugin_src

    def test_happy_launcher_and_plugin_share_binding_file_name(self) -> None:
        """Happy: Launcher and plugin both use 'PYTHON_BINDING' as the file name."""
        install_src = _read_source(INSTALL_PATH)
        plugin_src = _read_source(PLUGIN_PATH)

        # Both should reference the exact string "PYTHON_BINDING" (the file name)
        assert '"PYTHON_BINDING"' in install_src or "'PYTHON_BINDING'" in install_src
        assert '"PYTHON_BINDING"' in plugin_src

    def test_happy_rails_use_launcher_not_python_directly(self) -> None:
        """Happy: All 5 rails invoke opencode-governance-bootstrap, not python."""
        rail_files = ["continue.md", "review.md", "audit-readout.md", "plan.md", "ticket.md", "review-decision.md", "implement.md"]
        for fname in rail_files:
            path = REPO_ROOT / fname
            if not path.exists():
                continue
            content = _read_source(path)
            assert "opencode-governance-bootstrap" in content, (
                f"{fname} must use stable launcher command"
            )

    def test_bad_no_independent_python_probing_in_rails(self) -> None:
        """Bad: Rails must never independently probe for Python interpreters."""
        rail_files = ["continue.md", "review.md", "audit-readout.md", "plan.md", "ticket.md", "review-decision.md", "implement.md"]
        for fname in rail_files:
            path = REPO_ROOT / fname
            if not path.exists():
                continue
            content = _read_source(path)
            assert "which python" not in content
            assert "where python" not in content
            assert "py -3" not in content
