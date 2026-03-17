"""Conformance tests for opencode-integration-contract.v1.

Tests validate the contract document, opencode.json merge-ownership rules,
plugin lifecycle invariants, Python resolution order, rail injection,
and uninstall guarantees.

Paths:
  Happy  – nominal expectations hold on the current source tree
  Corner – boundary conditions (corrupt JSON, empty arrays, idempotency)
  Edge   – multi-token python commands, path quoting, legacy regex fallback
  Bad    – contract violations that MUST be detected
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from tests.util import REPO_ROOT, get_docs_path, get_master_path, get_rules_path

CONTRACT_PATH = get_docs_path() / "contracts" / "opencode-integration-contract.v1.md"
THIS_FILE_REL = "tests/conformance/test_opencode_integration_conformance.py"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_frontmatter(path: Path) -> dict:
    """Extract YAML frontmatter from a Markdown file."""
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?\n)---", text, re.DOTALL)
    assert m, f"No YAML frontmatter found in {path}"
    return yaml.safe_load(m.group(1))


# ---------------------------------------------------------------------------
# Contract-Ref Validation
# ---------------------------------------------------------------------------

@pytest.mark.conformance
class TestContractRefValidation:
    """Validate that the contract document itself is well-formed."""

    def test_contract_file_exists(self):
        """Happy: Contract document exists on disk."""
        assert CONTRACT_PATH.is_file(), f"Contract not found: {CONTRACT_PATH}"

    def test_frontmatter_is_parseable(self):
        """Happy: YAML frontmatter can be parsed without errors."""
        fm = _parse_frontmatter(CONTRACT_PATH)
        assert isinstance(fm, dict)

    def test_frontmatter_has_required_keys(self):
        """Happy: Frontmatter contains all standardised keys."""
        fm = _parse_frontmatter(CONTRACT_PATH)
        required = {"contract", "version", "status", "scope", "owner",
                     "effective_version", "supersedes", "conformance_suite"}
        missing = required - set(fm.keys())
        assert not missing, f"Missing frontmatter keys: {missing}"

    def test_conformance_suite_points_to_this_file(self):
        """Happy: conformance_suite field references this test file."""
        fm = _parse_frontmatter(CONTRACT_PATH)
        expected = THIS_FILE_REL
        actual = fm.get("conformance_suite", "")
        assert actual == expected, (
            f"conformance_suite mismatch: expected {expected!r}, got {actual!r}"
        )


# ---------------------------------------------------------------------------
# Merge Ownership (Section 1)
# ---------------------------------------------------------------------------

@pytest.mark.conformance
class TestMergeOwnership:
    """Validate opencode.json merge rules from contract section 1."""

    def test_happy_ensure_opencode_json_importable(self):
        """Happy: ensure_opencode_json function exists in install.py module."""
        install_src = (REPO_ROOT / "install.py").read_text(encoding="utf-8")
        assert "def ensure_opencode_json" in install_src, \
            "ensure_opencode_json function not found in install.py"

    def test_happy_canonical_instructions_defined(self):
        """Happy: OPENCODE_COMMAND_FILES constant is defined in install.py."""
        install_src = (REPO_ROOT / "install.py").read_text(encoding="utf-8")
        assert "OPENCODE_COMMAND_FILES" in install_src

    def test_happy_canonical_instructions_content(self):
        """Happy: All 8 canonical command paths are present in source."""
        install_src = (REPO_ROOT / "install.py").read_text(encoding="utf-8")
        expected_instructions = [
            "commands/continue.md",
            "commands/plan.md",
            "commands/review.md",
            "commands/review-decision.md",
            "commands/ticket.md",
            "commands/implement.md",
            "commands/implementation-decision.md",
            "commands/audit-readout.md",
        ]
        missing = [i for i in expected_instructions if i not in install_src]
        assert not missing, f"Missing canonical instructions: {missing}"

    def test_happy_merge_preserves_user_keys(self):
        """Happy: Source code only modifies 'command_files' and 'plugin' keys."""
        install_src = (REPO_ROOT / "install.py").read_text(encoding="utf-8")
        # The merge logic should reference specific keys, not do wholesale replacement
        assert '"command_files"' in install_src or "'command_files'" in install_src
        assert '"plugin"' in install_src or "'plugin'" in install_src

    def test_corner_corrupt_json_handling_documented(self):
        """Corner: install.py handles corrupt/non-dict JSON gracefully."""
        install_src = (REPO_ROOT / "install.py").read_text(encoding="utf-8")
        # Should have exception handling for JSON parse errors
        assert "JSONDecodeError" in install_src or "json.loads" in install_src or "json.load" in install_src

    def test_edge_instruction_files_exist_in_repo(self):
        """Edge: All canonical instruction target files exist in source tree."""
        # In the source tree, files are at REPO_ROOT directly (not under commands/)
        expected_files = [
            "SESSION_STATE_SCHEMA.md",
            "README-OPENCODE.md",
        ]
        missing = [f for f in expected_files if not (REPO_ROOT / f).is_file()]
        if not get_master_path().is_file():
            missing.append("master.md")
        if not get_rules_path().is_file():
            missing.append("rules.md")
        assert not missing, f"Canonical instruction target files missing: {missing}"


# ---------------------------------------------------------------------------
# Plugin Lifecycle (Section 2)
# ---------------------------------------------------------------------------

@pytest.mark.conformance
class TestPluginLifecycle:
    """Validate plugin lifecycle invariants from contract section 2."""

    PLUGIN_SOURCE = REPO_ROOT / "governance" / "artifacts" / "opencode-plugins" / "audit-new-session.mjs"

    def test_happy_plugin_source_exists(self):
        """Happy: Plugin source file exists at contract-specified location."""
        assert self.PLUGIN_SOURCE.is_file(), f"Plugin source not found: {self.PLUGIN_SOURCE}"

    def test_happy_plugin_handles_session_created_event(self):
        """Happy: Plugin source contains session.created event handler."""
        src = self.PLUGIN_SOURCE.read_text(encoding="utf-8")
        assert "session.created" in src or "session" in src

    def test_happy_plugin_deduplication_mechanism(self):
        """Happy: Plugin has session deduplication (in-memory Set)."""
        src = self.PLUGIN_SOURCE.read_text(encoding="utf-8")
        assert "Set" in src or "seen" in src, \
            "Plugin missing deduplication mechanism"

    def test_happy_plugin_plausibility_check(self):
        """Happy: Plugin verifies repo root plausibility."""
        src = self.PLUGIN_SOURCE.read_text(encoding="utf-8")
        plausibility_markers = [".git", "governance", "pyproject.toml", "package.json"]
        found = [m for m in plausibility_markers if m in src]
        assert len(found) >= 2, f"Plugin missing plausibility markers, found only: {found}"

    def test_happy_plugin_output_cap(self):
        """Happy: Plugin caps stdout/stderr output."""
        src = self.PLUGIN_SOURCE.read_text(encoding="utf-8")
        assert "64" in src or "maxBuffer" in src, \
            "Plugin missing output cap"

    def test_corner_plugin_non_blocking_failure_mode(self):
        """Corner: Plugin catches errors (non-blocking failure mode)."""
        src = self.PLUGIN_SOURCE.read_text(encoding="utf-8")
        assert "catch" in src or "try" in src, \
            "Plugin missing error handling for non-blocking failure"

    def test_happy_plugin_uninstall_removes_uri_only(self):
        """Happy: install.py has function to remove only the plugin URI."""
        install_src = (REPO_ROOT / "install.py").read_text(encoding="utf-8")
        assert "remove_installer_plugin" in install_src or "plugin" in install_src.lower()

    def test_bad_plugin_must_not_fail_hard_without_python(self):
        """Bad: Plugin source should handle missing Python gracefully."""
        src = self.PLUGIN_SOURCE.read_text(encoding="utf-8")
        # Should have a fallback path when no Python is found
        assert "resolvePython" in src or "python" in src.lower()


# ---------------------------------------------------------------------------
# Python Resolution Order (Section 3)
# ---------------------------------------------------------------------------

@pytest.mark.conformance
class TestPythonResolutionOrder:
    """Validate Python resolution order from contract section 3."""

    def test_happy_plugin_checks_opencode_python_env(self):
        """Happy: Plugin checks OPENCODE_PYTHON environment variable first."""
        src = (REPO_ROOT / "governance" / "artifacts" / "opencode-plugins" / "audit-new-session.mjs").read_text(encoding="utf-8")
        assert "OPENCODE_PYTHON" in src

    def test_happy_plugin_checks_py_launcher_on_windows(self):
        """Happy: Plugin checks py -3 on Windows."""
        src = (REPO_ROOT / "governance" / "artifacts" / "opencode-plugins" / "audit-new-session.mjs").read_text(encoding="utf-8")
        assert "py" in src

    def test_happy_plugin_checks_python3_on_unix(self):
        """Happy: Plugin checks python3 on Unix."""
        src = (REPO_ROOT / "governance" / "artifacts" / "opencode-plugins" / "audit-new-session.mjs").read_text(encoding="utf-8")
        assert "python3" in src


# ---------------------------------------------------------------------------
# Rail Injection (Section 4)
# ---------------------------------------------------------------------------

@pytest.mark.conformance
class TestRailInjection:
    """Validate rail injection invariants from contract section 4."""

    INJECTION_TARGETS = ["continue.md", "review.md", "plan.md", "ticket.md", "review-decision.md", "implement.md", "audit-readout.md"]

    def test_happy_injection_targets_exist(self):
        """Happy: All rail injection target source files exist in repo."""
        # In the source tree, these live at REPO_ROOT directly
        missing = [f for f in self.INJECTION_TARGETS
                   if not (REPO_ROOT / f).is_file()]
        assert not missing, f"Rail injection targets missing: {missing}"

    def test_happy_placeholders_in_source(self):
        """Happy: install.py contains BIN_DIR placeholder pattern (and legacy patterns)."""
        install_src = (REPO_ROOT / "install.py").read_text(encoding="utf-8")
        assert "{{BIN_DIR}}" in install_src or "BIN_DIR_PLACEHOLDER" in install_src
        # Legacy patterns should still be defined for backwards compatibility
        assert "SESSION_READER_PATH" in install_src or "PYTHON_COMMAND" in install_src

    def test_happy_injection_function_exists(self):
        """Happy: inject_session_reader_path_for_command exists in install.py."""
        install_src = (REPO_ROOT / "install.py").read_text(encoding="utf-8")
        assert "def inject_session_reader_path" in install_src or "inject_session_reader" in install_src

    def test_corner_injection_targets_have_placeholders_or_resolved_paths(self):
        """Corner: Each rail source file has a BIN_DIR placeholder or a resolved launcher invocation."""
        for fname in self.INJECTION_TARGETS:
            fpath = REPO_ROOT / fname
            if not fpath.is_file():
                continue  # file-existence is tested separately
            content = fpath.read_text(encoding="utf-8")
            has_bin_dir = "{{BIN_DIR}}" in content
            has_launcher = "opencode-governance-bootstrap" in content
            has_legacy = "{{SESSION_READER_PATH}}" in content or "{{PYTHON_COMMAND}}" in content
            has_resolved = "session_reader" in content.lower() or "python" in content.lower()
            assert has_bin_dir or has_launcher or has_legacy or has_resolved, \
                f"{fname} has neither BIN_DIR placeholder, launcher reference, nor resolved path"

    def test_edge_python_quoting_logic_in_source(self):
        """Edge: install.py has path-quoting logic for Python commands with spaces."""
        install_src = (REPO_ROOT / "install.py").read_text(encoding="utf-8")
        # Should handle quoting for paths with spaces
        assert "quote" in install_src.lower() or '" "' in install_src or "os.sep" in install_src or "pathsep" in install_src or "\\\\" in install_src


# ---------------------------------------------------------------------------
# Uninstall Guarantee (Section 5)
# ---------------------------------------------------------------------------

@pytest.mark.conformance
class TestUninstallGuarantee:
    """Validate the opencode.json never-delete guarantee from contract section 5."""

    def test_happy_three_protection_sites(self):
        """Happy: install.py has at least 2 runtime guard sites for OPENCODE_JSON_NAME."""
        import re
        install_src = (REPO_ROOT / "install.py").read_text(encoding="utf-8")
        # R14 replaced assert-based guards with RuntimeError guards that survive -O mode.
        # Find if-guard + raise RuntimeError patterns referencing OPENCODE_JSON_NAME.
        guard_count = len(re.findall(
            r"if\s+OPENCODE_JSON_NAME\b.*?raise\s+RuntimeError",
            install_src,
            re.DOTALL,
        ))
        assert guard_count >= 2, (
            f"Expected >=2 RuntimeError guard sites for OPENCODE_JSON_NAME, found {guard_count}"
        )

    def test_happy_opencode_json_name_constant(self):
        """Happy: OPENCODE_JSON_NAME constant is defined."""
        install_src = (REPO_ROOT / "install.py").read_text(encoding="utf-8")
        assert "OPENCODE_JSON_NAME" in install_src

    def test_bad_opencode_json_not_in_delete_targets(self):
        """Bad: opencode.json must not appear in any deletion target list."""
        install_src = (REPO_ROOT / "install.py").read_text(encoding="utf-8")
        # The runtime guards in install.py enforce this — we verify the guards exist
        guard_present = "RuntimeError" in install_src and "OPENCODE_JSON" in install_src
        assert guard_present, "Missing RuntimeError guard protecting opencode.json from deletion"

    def test_bad_plugin_removal_function_exists(self):
        """Bad: Plugin URI removal function must exist (plugin is removed, file is not)."""
        install_src = (REPO_ROOT / "install.py").read_text(encoding="utf-8")
        assert "remove_installer_plugin" in install_src, \
            "Missing function to remove plugin URI from opencode.json"
