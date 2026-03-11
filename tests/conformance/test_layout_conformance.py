"""Conformance tests for install-layout-contract.v_current.

Tests validate the contract document, real path resolution, installed tree
shape, workspace artifact layout, per-artifact ownership, uninstall/retention
behaviour, pointer architecture and config-root safety invariants.

Paths:
  Happy  – nominal expectations hold on the current repo tree
  Corner – boundary conditions (e.g. empty workspace, fingerprint edge lengths)
  Edge   – cross-platform path separators, long paths, special characters
  Bad    – contract violations that MUST be detected
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from tests.util import REPO_ROOT

CONTRACT_PATH = REPO_ROOT / "docs" / "contracts" / "install-layout-contract.v_current.md"
THIS_FILE_REL = "tests/conformance/test_layout_conformance.py"

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
# Contract-Ref Validation (required by sharpening decision)
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
# Installed Tree Shape (Section 2)
# ---------------------------------------------------------------------------

@pytest.mark.conformance
class TestInstalledTreeShape:
    """Validate that the contract-specified tree shape matches the repo."""

    # Files that MUST exist at REPO_ROOT (= source of commands/ in a dev checkout)
    # In the source tree, command files live at REPO_ROOT directly; the installer
    # copies them to ${CONFIG_ROOT}/commands/ on install.
    EXPECTED_SOURCE_FILES = [
        "master.md",
        "rules.md",
        "BOOTSTRAP.md",
        "continue.md",
        "review.md",
        "review-decision.md",
        "implement.md",
        "plan.md",
        "ticket.md",
        "README.md",
        "README-RULES.md",
        "README-OPENCODE.md",
        "SESSION_STATE_SCHEMA.md",
    ]

    def test_happy_command_files_exist(self):
        """Happy: All contract-listed command source files exist in the repo."""
        missing = []
        for rel in self.EXPECTED_SOURCE_FILES:
            if not (REPO_ROOT / rel).is_file():
                missing.append(rel)
        assert not missing, f"Missing command source files: {missing}"

    def test_happy_governance_dir_exists(self):
        """Happy: governance/ directory exists at repo root."""
        assert (REPO_ROOT / "governance").is_dir()

    def test_happy_install_script_exists(self):
        """Happy: install.py exists at repo root."""
        assert (REPO_ROOT / "install.py").is_file()

    def test_happy_plugin_source_exists(self):
        """Happy: audit-new-session.mjs plugin source exists."""
        assert (REPO_ROOT / "governance" / "artifacts" / "opencode-plugins" / "audit-new-session.mjs").is_file()

    def test_corner_profiles_dir_exists(self):
        """Corner: profiles/ directory exists (may be empty in some configs)."""
        profiles = REPO_ROOT / "profiles"
        assert profiles.is_dir(), f"profiles/ directory missing at {profiles}"

    def test_edge_no_path_traversal_in_commands(self):
        """Edge: No command file path contains '..' traversal."""
        # In the source tree, command files are at REPO_ROOT; check .md files
        for p in REPO_ROOT.glob("*.md"):
            assert ".." not in p.name, f"Path traversal in command file: {p.name}"


# ---------------------------------------------------------------------------
# Workspace Artifact Layout (Section 3)
# ---------------------------------------------------------------------------

@pytest.mark.conformance
class TestWorkspaceArtifactLayout:
    """Validate workspace_paths.py against contract section 3."""

    def test_happy_all_contract_artifacts_have_path_functions(self):
        """Happy: Every artifact in the contract has a path function in workspace_paths.py."""
        from governance.infrastructure import workspace_paths as wp

        # Artifact names from contract section 3 → expected function names
        expected_functions = {
            "session_state_path",
            "repo_cache_path",
            "repo_map_digest_path",
            "workspace_memory_path",
            "decision_pack_path",
            "business_rules_path",
            "business_rules_status_path",
            "plan_record_path",
            "plan_record_archive_dir",
            "repo_identity_map_path",
            "current_run_path",
            "evidence_dir",
            "locks_dir",
            "runs_dir",
        }
        missing = expected_functions - {name for name in dir(wp) if callable(getattr(wp, name, None))}
        assert not missing, f"Missing path functions in workspace_paths.py: {missing}"

    def test_happy_path_functions_return_under_workspace_or_audit_root(self, tmp_path):
        """Happy: Runtime paths resolve under workspace, audit paths under governance-records."""
        from governance.infrastructure import workspace_paths as wp

        ws_home = tmp_path / "workspaces"
        fp = "a" * 24
        root = wp.workspace_root(ws_home, fp)

        runtime_artifact_fns = [
            wp.session_state_path,
            wp.repo_cache_path,
            wp.repo_map_digest_path,
            wp.workspace_memory_path,
            wp.decision_pack_path,
            wp.business_rules_path,
            wp.business_rules_status_path,
            wp.plan_record_path,
            wp.plan_record_archive_dir,
            wp.repo_identity_map_path,
            wp.current_run_path,
            wp.evidence_dir,
            wp.locks_dir,
        ]
        escaped = []
        for fn in runtime_artifact_fns:
            p = fn(ws_home, fp)
            try:
                p.relative_to(root)
            except ValueError:
                escaped.append(f"{fn.__name__} -> {p}")
        assert not escaped, f"Artifacts escape workspace root: {escaped}"

        audit_root = ws_home / "governance-records" / fp
        runs = wp.runs_dir(ws_home, fp)
        assert runs.relative_to(audit_root)

    def test_happy_global_pointer_at_config_root(self, tmp_path):
        """Happy: global_pointer_path resolves directly under config root."""
        from governance.infrastructure import workspace_paths as wp

        config_root = tmp_path / "opencode-home"
        ptr = wp.global_pointer_path(config_root)
        assert ptr.parent == config_root, f"Pointer not at config root: {ptr}"
        assert ptr.name == "SESSION_STATE.json"

    def test_corner_fingerprint_24_hex_boundary(self, tmp_path):
        """Corner: Fingerprint at exactly 24 hex chars is accepted."""
        from governance.infrastructure import workspace_paths as wp

        fp_min = "0" * 24
        fp_max = "f" * 24
        ws_home = tmp_path / "ws"
        # Should not raise
        wp.workspace_root(ws_home, fp_min)
        wp.workspace_root(ws_home, fp_max)

    def test_edge_workspace_root_path_segments(self, tmp_path):
        """Edge: workspace_root produces exactly workspaces_home / fingerprint."""
        from governance.infrastructure import workspace_paths as wp

        ws_home = tmp_path / "workspaces"
        fp = "ab" * 12
        root = wp.workspace_root(ws_home, fp)
        assert root == ws_home / fp

    def test_bad_artifact_names_match_contract(self, tmp_path):
        """Bad path detection: artifact filename constants match contract specification."""
        from governance.infrastructure import workspace_paths as wp

        ws_home = tmp_path / "ws"
        fp = "c" * 24
        # Expected filenames from contract section 3
        expected_names = {
            "SESSION_STATE.json",
            "repo-cache.yaml",
            "repo-map-digest.md",
            "workspace-memory.yaml",
            "decision-pack.md",
            "business-rules.md",
            "business-rules-status.md",
            "plan-record.json",
            "plan-record-archive",
            "repo-identity-map.yaml",
            "current_run.json",
            "evidence",
            "locks",
            "runs",
        }
        actual_names = set()
        for fn_name in [
            "session_state_path", "repo_cache_path", "repo_map_digest_path",
            "workspace_memory_path", "decision_pack_path", "business_rules_path",
            "business_rules_status_path", "plan_record_path", "plan_record_archive_dir",
            "repo_identity_map_path", "current_run_path", "evidence_dir",
            "locks_dir", "runs_dir",
        ]:
            fn = getattr(wp, fn_name)
            actual_names.add(fn(ws_home, fp).name)
        drift = expected_names - actual_names
        assert not drift, f"Contract artifact names not produced by workspace_paths: {drift}"


# ---------------------------------------------------------------------------
# Pointer Architecture (Section 6)
# ---------------------------------------------------------------------------

@pytest.mark.conformance
class TestPointerArchitecture:
    """Validate pointer semantics from contract section 6."""

    def test_happy_canonical_pointer_schema(self):
        """Happy: CANONICAL_POINTER_SCHEMA matches contract."""
        from governance.infrastructure.session_pointer import CANONICAL_POINTER_SCHEMA
        assert CANONICAL_POINTER_SCHEMA == "opencode-session-pointer.v1"

    def test_happy_pointer_payload_has_required_keys(self, tmp_path):
        """Happy: build_pointer_payload produces the three canonical keys."""
        from governance.infrastructure.session_pointer import build_pointer_payload

        fp = "a" * 24
        config_root = tmp_path / "config"
        ws_home = config_root / "workspaces"
        ss = ws_home / fp / "SESSION_STATE.json"
        payload = build_pointer_payload(fp, session_state_file=ss, config_root=config_root)
        for key in ("schema", "activeRepoFingerprint", "activeSessionStateRelativePath"):
            assert key in payload, f"Missing pointer key: {key}"

    def test_happy_pointer_is_not_state(self, tmp_path):
        """Happy: Global pointer is named SESSION_STATE.json but is a routing pointer."""
        from governance.infrastructure.workspace_paths import global_pointer_path
        ptr = global_pointer_path(tmp_path / "cfg")
        assert ptr.name == "SESSION_STATE.json", "Global pointer filename changed"

    def test_corner_legacy_pointer_schema_recognized(self):
        """Corner: Legacy schema 'active-session-pointer.v1' is in LEGACY set."""
        from governance.infrastructure.session_pointer import LEGACY_POINTER_SCHEMAS
        assert "active-session-pointer.v1" in LEGACY_POINTER_SCHEMAS

    def test_bad_invalid_fingerprint_rejected(self):
        """Bad: Non-24-hex fingerprint is rejected by validate_fingerprint."""
        from governance.infrastructure.session_pointer import validate_fingerprint

        for bad_fp in ["", "abc", "g" * 24, "a" * 23, "a" * 25, "zzzz" * 6]:
            with pytest.raises(ValueError):
                validate_fingerprint(bad_fp)

    def test_bad_pointer_without_schema_is_invalid(self):
        """Bad: Pointer payload without schema field is rejected."""
        from governance.infrastructure.session_pointer import is_valid_pointer
        assert not is_valid_pointer({"activeRepoFingerprint": "a" * 24})

    def test_bad_pointer_with_wrong_rel_path_is_invalid(self, tmp_path):
        """Bad: Pointer with incorrect relative path is rejected."""
        from governance.infrastructure.session_pointer import is_valid_pointer

        fp = "a" * 24
        payload = {
            "schema": "opencode-session-pointer.v1",
            "activeRepoFingerprint": fp,
            "activeSessionStateFile": str(tmp_path / "config" / "workspaces" / fp / "SESSION_STATE.json"),
            "activeSessionStateRelativePath": "wrong/path/SESSION_STATE.json",
        }
        assert not is_valid_pointer(payload)


# ---------------------------------------------------------------------------
# Uninstall Retention (Section 5) — structural invariant checks
# ---------------------------------------------------------------------------

@pytest.mark.conformance
class TestUninstallRetention:
    """Validate uninstall/retention invariants from contract section 5."""

    def test_happy_opencode_json_never_delete_assertions_in_source(self):
        """Happy: install.py contains runtime guards protecting opencode.json from deletion."""
        install_src = (REPO_ROOT / "install.py").read_text(encoding="utf-8")
        # Contract says protection sites guard opencode.json
        assert "OPENCODE_JSON_NAME" in install_src, "OPENCODE_JSON_NAME constant missing"
        # At least 2 runtime guard sites (raise RuntimeError) mentioning OPENCODE_JSON_NAME
        # (R14 replaced assert-based guards with runtime guards that survive -O mode)
        import re
        guard_count = len(re.findall(
            r"if\s+OPENCODE_JSON_NAME\b.*?raise\s+RuntimeError",
            install_src,
            re.DOTALL,
        ))
        assert guard_count >= 2, f"Expected >=2 RuntimeError guard sites for OPENCODE_JSON_NAME, found {guard_count}"

    def test_happy_purge_uses_allowlist(self):
        """Happy: purge_runtime_state uses an allowlist, not a glob delete."""
        install_src = (REPO_ROOT / "install.py").read_text(encoding="utf-8")
        # The purge function should reference specific artifact names
        for artifact in ["SESSION_STATE.json", "repo-cache.yaml", "plan-record.json"]:
            assert artifact in install_src, f"Purge allowlist missing: {artifact}"

    def test_edge_purge_flat_file_count_matches_contract(self):
        """Edge: The 9 flat files listed in contract section 5.2 are all referenced in install.py."""
        install_src = (REPO_ROOT / "install.py").read_text(encoding="utf-8")
        flat_files = [
            "SESSION_STATE.json",
            "repo-identity-map.yaml",
            "repo-cache.yaml",
            "repo-map-digest.md",
            "workspace-memory.yaml",
            "decision-pack.md",
            "business-rules.md",
            "business-rules-status.md",
            "plan-record.json",
        ]
        missing = [f for f in flat_files if f not in install_src]
        assert not missing, f"Flat files missing from install.py purge: {missing}"

    def test_bad_opencode_json_not_in_workspace_artifact_names(self, tmp_path):
        """Bad: opencode.json must NEVER appear in workspace artifact purge targets."""
        # This mirrors the runtime assertion in install.py
        from governance.infrastructure import workspace_paths as wp

        ws_home = tmp_path / "ws"
        fp = "a" * 24
        artifact_paths = wp.all_phase_artifact_paths(ws_home, fp)
        artifact_names = {p.name for p in artifact_paths.values()}
        assert "opencode.json" not in artifact_names, \
            "opencode.json must never be a workspace artifact"


# ---------------------------------------------------------------------------
# Config-Root Safety (Section 7)
# ---------------------------------------------------------------------------

@pytest.mark.conformance
class TestConfigRootSafety:
    """Validate config-root safety invariants from contract section 7."""

    def test_happy_bootstrap_persistence_blocks_config_in_repo(self):
        """Happy: bootstrap_persistence.py contains config-root-inside-repo check."""
        bp_path = REPO_ROOT / "governance" / "infrastructure" / "bootstrap_persistence.py"
        if bp_path.is_file():
            src = bp_path.read_text(encoding="utf-8")
            assert "CONFIG_ROOT_INSIDE_REPO" in src or "config_root" in src.lower(), \
                "bootstrap_persistence.py missing config-root safety check"
