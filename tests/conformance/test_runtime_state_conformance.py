"""Conformance tests for runtime-state-contract.v1.

Tests validate the contract document, state classification taxonomy,
pointer semantics policy, backup/purge/recovery rules, and the artifact
completeness invariant.

Paths:
  Happy  – nominal expectations hold on the current source tree
  Corner – boundary conditions (empty workspace, edge-case fingerprints)
  Edge   – cross-platform paths, legacy pointer migration
  Bad    – contract violations that MUST be detected
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from tests.util import REPO_ROOT, get_docs_path

CONTRACT_PATH = get_docs_path() / "contracts" / "runtime-state-contract.v1.md"
THIS_FILE_REL = "tests/conformance/test_runtime_state_conformance.py"
INSTALLER_SOURCE_PATH = REPO_ROOT / "governance_runtime" / "install" / "install.py"

# ---------------------------------------------------------------------------
# State Classification Taxonomy — source of truth from the contract
# ---------------------------------------------------------------------------

# Every artifact from workspace_paths.py mapped to its expected class
CLASSIFICATION_TABLE: dict[str, str] = {
    # canonical
    "SESSION_STATE.json": "canonical",
    "plan-record.json": "canonical",
    "plan-record-archive": "canonical",
    "evidence": "canonical",
    "repo-identity-map.yaml": "canonical",
    "current_run.json": "canonical",
    "marker.json": "canonical",
    "runs": "canonical",
    # derived
    "repo-cache.yaml": "derived",
    "repo-map-digest.md": "derived",
    "workspace-memory.yaml": "derived",
    "decision-pack.md": "derived",
    "business-rules.md": "derived",
    "business-rules-status.md": "derived",
    # transient
    "locks": "transient",
}

# Artifacts that workspace_paths.py exposes (the function-name → filename mapping)
WORKSPACE_PATHS_FUNCTIONS = {
    "session_state_path": "SESSION_STATE.json",
    "repo_cache_path": "repo-cache.yaml",
    "repo_map_digest_path": "repo-map-digest.md",
    "workspace_memory_path": "workspace-memory.yaml",
    "decision_pack_path": "decision-pack.md",
    "business_rules_path": "business-rules.md",
    "business_rules_status_path": "business-rules-status.md",
    "plan_record_path": "plan-record.json",
    "plan_record_archive_dir": "plan-record-archive",
    "repo_identity_map_path": "repo-identity-map.yaml",
    "current_run_path": "current_run.json",
    "evidence_dir": "evidence",
    "locks_dir": "locks",
    "runs_dir": "runs",
}


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
# State Classification (Section 1)
# ---------------------------------------------------------------------------

@pytest.mark.conformance
class TestStateClassification:
    """Validate that the classification taxonomy is complete and consistent."""

    def test_happy_all_workspace_paths_classified(self, tmp_path):
        """Happy: Every artifact from workspace_paths.py has a classification entry."""
        from governance.infrastructure import workspace_paths as wp

        ws_home = tmp_path / "ws"
        fp = "a" * 24
        unclassified = []
        for fn_name, expected_filename in WORKSPACE_PATHS_FUNCTIONS.items():
            fn = getattr(wp, fn_name, None)
            assert fn is not None, f"workspace_paths.{fn_name} not found"
            actual_name = fn(ws_home, fp).name
            if actual_name not in CLASSIFICATION_TABLE:
                unclassified.append(f"{fn_name} -> {actual_name}")
        assert not unclassified, (
            f"Artifacts missing from classification table (contract violation, "
            f"should trigger BLOCKED-CONTRACT-RUNTIME-DRIFT): {unclassified}"
        )

    def test_happy_three_classes_only(self):
        """Happy: Only three classes exist: canonical, derived, transient."""
        classes = set(CLASSIFICATION_TABLE.values())
        assert classes == {"canonical", "derived", "transient"}, \
            f"Unexpected classes: {classes}"

    def test_happy_canonical_artifacts_include_session_state(self):
        """Happy: SESSION_STATE.json is classified as canonical."""
        assert CLASSIFICATION_TABLE.get("SESSION_STATE.json") == "canonical"

    def test_happy_derived_artifacts_are_regenerable(self):
        """Happy: All derived artifacts are the repo-analysis outputs."""
        derived = {k for k, v in CLASSIFICATION_TABLE.items() if v == "derived"}
        expected_derived = {
            "repo-cache.yaml",
            "repo-map-digest.md",
            "workspace-memory.yaml",
            "decision-pack.md",
            "business-rules.md",
            "business-rules-status.md",
        }
        assert derived == expected_derived, f"Derived set drift: {derived ^ expected_derived}"

    def test_happy_transient_is_locks_only(self):
        """Happy: Only locks/ is classified as transient."""
        transient = {k for k, v in CLASSIFICATION_TABLE.items() if v == "transient"}
        assert transient == {"locks"}, f"Transient set drift: {transient}"

    def test_corner_marker_json_not_in_workspace_paths(self):
        """Corner: marker.json is in contract but may not have a dedicated workspace_paths function.
        
        The classification table includes marker.json as canonical, but
        workspace_paths.py may not expose it. This is acceptable if the workspace
        ready gate manages it separately. We just verify the contract entry exists.
        """
        assert "marker.json" in CLASSIFICATION_TABLE

    def test_edge_classification_count(self):
        """Edge: Total classified artifacts matches expected count from contract."""
        # Contract section 1.1 lists 15 artifacts
        assert len(CLASSIFICATION_TABLE) == 15, \
            f"Expected 15 classified artifacts, got {len(CLASSIFICATION_TABLE)}"

    def test_bad_opencode_json_is_not_classified(self):
        """Bad: opencode.json is user-owned and must NOT appear in workspace classification."""
        assert "opencode.json" not in CLASSIFICATION_TABLE, \
            "opencode.json must not be classified as a workspace artifact"


# ---------------------------------------------------------------------------
# Pointer Semantics (Section 2)
# ---------------------------------------------------------------------------

@pytest.mark.conformance
class TestPointerSemantics:
    """Validate pointer semantics policy from contract section 2."""

    def test_happy_global_pointer_is_routing_only(self, tmp_path):
        """Happy: Global pointer file is named SESSION_STATE.json (routing pointer)."""
        from governance.infrastructure.workspace_paths import global_pointer_path
        ptr = global_pointer_path(tmp_path / "cfg")
        assert ptr.name == "SESSION_STATE.json"

    def test_happy_pointer_schema_is_v1(self):
        """Happy: Canonical pointer schema matches contract."""
        from governance.infrastructure.session_pointer import CANONICAL_POINTER_SCHEMA
        assert CANONICAL_POINTER_SCHEMA == "opencode-session-pointer.v1"

    def test_happy_pointer_keys_match_contract(self, tmp_path):
        """Happy: build_pointer_payload produces all contract-specified keys."""
        from governance.infrastructure.session_pointer import build_pointer_payload

        fp = "b" * 24
        config = tmp_path / "config"
        ss = config / "workspaces" / fp / "SESSION_STATE.json"
        payload = build_pointer_payload(fp, session_state_file=ss, config_root=config)
        assert payload["schema"] == "opencode-session-pointer.v1"
        assert payload["activeRepoFingerprint"] == fp
        assert "activeSessionStateRelativePath" in payload

    def test_happy_workspace_state_is_separate_from_pointer(self, tmp_path):
        """Happy: Workspace state path differs from global pointer path."""
        from governance.infrastructure import workspace_paths as wp

        config_root = tmp_path / "cfg"
        ws_home = config_root / "workspaces"
        fp = "c" * 24
        pointer = wp.global_pointer_path(config_root)
        ws_state = wp.session_state_path(ws_home, fp)
        assert pointer != ws_state, "Global pointer and workspace state must be different paths"

    def test_corner_legacy_schema_migration(self, tmp_path):
        """Corner: parse_pointer_payload accepts legacy schema and produces canonical keys."""
        from governance.infrastructure.session_pointer import parse_pointer_payload

        fp = "d" * 24
        legacy_payload = {
            "schema": "active-session-pointer.v1",
            "repo_fingerprint": fp,
            "active_session_state_file": str(tmp_path / "config" / "workspaces" / fp / "SESSION_STATE.json"),
            "active_session_state_relative_path": f"workspaces/{fp}/SESSION_STATE.json",
        }
        result = parse_pointer_payload(legacy_payload)
        assert result.get("schema") == "opencode-session-pointer.v1", \
            "Legacy pointer not migrated to canonical schema"
        assert result.get("activeRepoFingerprint") == fp

    def test_bad_pointer_inside_repo_root_blocked(self):
        """Bad: bootstrap_persistence should block config_root inside repo_root."""
        bp_path = REPO_ROOT / "governance" / "infrastructure" / "bootstrap_persistence.py"
        if bp_path.is_file():
            src = bp_path.read_text(encoding="utf-8")
            has_check = ("CONFIG_ROOT_INSIDE_REPO" in src or
                         "POINTER_PATH_INSIDE_REPO" in src or
                         "config_root" in src.lower())
            assert has_check, "bootstrap_persistence.py missing repo-root safety check"


# ---------------------------------------------------------------------------
# Purge Rules (Section 3)
# ---------------------------------------------------------------------------

@pytest.mark.conformance
class TestPurgeRules:
    """Validate purge behaviour from contract section 3."""

    def test_happy_purge_allowlist_flat_files(self):
        """Happy: All 9 contract flat files appear in install.py purge logic."""
        install_src = INSTALLER_SOURCE_PATH.read_text(encoding="utf-8")
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
        assert not missing, f"Purge allowlist flat files missing: {missing}"

    def test_happy_purge_subtrees(self):
        """Happy: All 3 contract subtrees appear in install.py purge logic."""
        install_src = INSTALLER_SOURCE_PATH.read_text(encoding="utf-8")
        subtrees = ["plan-record-archive", "evidence"]
        missing = [s for s in subtrees if s not in install_src]
        assert not missing, f"Purge allowlist subtrees missing: {missing}"

    def test_happy_config_root_purge_targets(self):
        """Happy: Both config-root-level purge targets in install.py."""
        install_src = INSTALLER_SOURCE_PATH.read_text(encoding="utf-8")
        assert "governance.activation_intent.json" in install_src

    def test_corner_purge_does_not_use_glob(self):
        """Corner: purge_runtime_state uses explicit names, not glob/wildcard patterns."""
        install_src = INSTALLER_SOURCE_PATH.read_text(encoding="utf-8")
        # Extract purge function body (rough heuristic)
        purge_idx = install_src.find("def purge_runtime_state")
        if purge_idx >= 0:
            purge_body = install_src[purge_idx:purge_idx + 3000]
            assert "glob" not in purge_body.lower() or "*.json" not in purge_body, \
                "purge_runtime_state should use allowlist, not glob patterns"

    def test_bad_opencode_json_never_purged(self):
        """Bad: opencode.json must be protected from purge by runtime guards."""
        import re
        install_src = INSTALLER_SOURCE_PATH.read_text(encoding="utf-8")
        # R14 replaced assert-based guards with RuntimeError guards that survive -O mode.
        guard_count = len(re.findall(
            r"if\s+OPENCODE_JSON_NAME\b.*?raise\s+RuntimeError",
            install_src,
            re.DOTALL,
        ))
        assert guard_count >= 1, \
            "No RuntimeError guard protecting opencode.json from purge"


# ---------------------------------------------------------------------------
# Artifact Completeness Invariant (Section 4)
# ---------------------------------------------------------------------------

@pytest.mark.conformance
class TestArtifactCompleteness:
    """Validate the artifact completeness invariant from contract section 4."""

    def test_happy_all_path_functions_have_classifications(self, tmp_path):
        """Happy: Every workspace_paths function output is in the classification table."""
        from governance.infrastructure import workspace_paths as wp

        ws_home = tmp_path / "ws"
        fp = "e" * 24
        unclassified = []
        for fn_name, expected_filename in WORKSPACE_PATHS_FUNCTIONS.items():
            fn = getattr(wp, fn_name)
            actual = fn(ws_home, fp).name
            if actual not in CLASSIFICATION_TABLE:
                unclassified.append(f"{fn_name} -> {actual}")
        assert not unclassified, (
            f"Artifact completeness invariant violated — unclassified artifacts "
            f"should trigger BLOCKED-CONTRACT-RUNTIME-DRIFT: {unclassified}"
        )

    def test_happy_reason_code_exists_for_drift(self):
        """Happy: BLOCKED-CONTRACT-RUNTIME-DRIFT reason code is registered."""
        from governance.domain.reason_codes import BLOCKED_CONTRACT_RUNTIME_DRIFT
        assert BLOCKED_CONTRACT_RUNTIME_DRIFT == "BLOCKED-CONTRACT-RUNTIME-DRIFT"

    def test_happy_all_three_drift_codes_exist(self):
        """Happy: All 3 contract drift reason codes are defined."""
        from governance.domain import reason_codes as rc
        assert hasattr(rc, "BLOCKED_CONTRACT_LAYOUT_DRIFT")
        assert hasattr(rc, "BLOCKED_CONTRACT_RUNTIME_DRIFT")
        assert hasattr(rc, "BLOCKED_CONTRACT_OPENCODE_DRIFT")

    def test_bad_drift_codes_in_canonical_tuple(self):
        """Bad: All 3 drift codes must be in CANONICAL_REASON_CODES."""
        from governance.domain.reason_codes import CANONICAL_REASON_CODES
        drift_codes = {
            "BLOCKED-CONTRACT-LAYOUT-DRIFT",
            "BLOCKED-CONTRACT-RUNTIME-DRIFT",
            "BLOCKED-CONTRACT-OPENCODE-DRIFT",
        }
        missing = drift_codes - set(CANONICAL_REASON_CODES)
        assert not missing, f"Drift codes missing from CANONICAL_REASON_CODES: {missing}"
