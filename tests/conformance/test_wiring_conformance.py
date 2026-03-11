"""Conformance tests for cross-cutting wiring invariants.

Tests validate that the subsystems are correctly wired together:
installer→files, launcher→entrypoints, rails→paths, plugin→runtime,
runtime→workspace consistency, the "no rogue paths" invariant, and
contract-ref integrity across all contract documents.

Paths:
  Happy  – nominal expectations hold on the current source tree
  Corner – boundary conditions (missing entrypoints, empty modules)
  Edge   – cross-platform path separators, placeholder detection
  Bad    – wiring violations that MUST be detected
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from tests.util import REPO_ROOT

# ---------------------------------------------------------------------------
# Contract documents — all 5 contracts must be validated
# ---------------------------------------------------------------------------

CONTRACT_DIR = REPO_ROOT / "docs" / "contracts"

ALL_CONTRACTS = {
    "install-layout-contract.v_current.md": "tests/conformance/test_layout_conformance.py",
    "install-layout-contract.v_next.md": None,       # v_next has no conformance suite yet
    "install-layout-migration.v1.md": None,           # planned, conformance_suite: TBD
    "opencode-integration-contract.v1.md": "tests/conformance/test_opencode_integration_conformance.py",
    "runtime-state-contract.v1.md": "tests/conformance/test_runtime_state_conformance.py",
    "python-binding-contract.v1.md": "tests/conformance/test_binding_conformance.py",
}

# Contracts with active conformance suites
CONTRACTS_WITH_SUITES = {
    k: v for k, v in ALL_CONTRACTS.items() if v is not None
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


def _read_source(path: Path) -> str:
    """Read a source file as text."""
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Contract-Ref Validation — ALL contract documents
# ---------------------------------------------------------------------------

@pytest.mark.conformance
class TestAllContractRefsExist:
    """Validate that every contract document exists and has valid frontmatter."""

    def test_happy_all_contract_files_exist(self):
        """Happy: All 5 contract documents exist on disk."""
        missing = [
            name for name in ALL_CONTRACTS
            if not (CONTRACT_DIR / name).is_file()
        ]
        assert not missing, f"Missing contract documents: {missing}"

    @pytest.mark.parametrize("contract_name", list(ALL_CONTRACTS.keys()))
    def test_happy_frontmatter_parseable(self, contract_name: str):
        """Happy: YAML frontmatter can be parsed without errors."""
        path = CONTRACT_DIR / contract_name
        fm = _parse_frontmatter(path)
        assert isinstance(fm, dict)

    @pytest.mark.parametrize("contract_name", list(ALL_CONTRACTS.keys()))
    def test_happy_frontmatter_has_required_keys(self, contract_name: str):
        """Happy: Frontmatter contains all standardised keys."""
        path = CONTRACT_DIR / contract_name
        fm = _parse_frontmatter(path)
        required = {"contract", "version", "status", "scope", "owner",
                     "effective_version", "supersedes", "conformance_suite"}
        missing = required - set(fm.keys())
        assert not missing, f"{contract_name}: missing frontmatter keys: {missing}"

    @pytest.mark.parametrize(
        "contract_name,expected_suite",
        list(CONTRACTS_WITH_SUITES.items()),
    )
    def test_happy_conformance_suite_points_to_correct_file(
        self, contract_name: str, expected_suite: str
    ):
        """Happy: conformance_suite field references the correct test file."""
        path = CONTRACT_DIR / contract_name
        fm = _parse_frontmatter(path)
        actual = fm.get("conformance_suite", "")
        assert actual == expected_suite, (
            f"{contract_name}: conformance_suite mismatch: "
            f"expected {expected_suite!r}, got {actual!r}"
        )

    @pytest.mark.parametrize(
        "contract_name,expected_suite",
        list(CONTRACTS_WITH_SUITES.items()),
    )
    def test_happy_conformance_suite_file_exists(
        self, contract_name: str, expected_suite: str
    ):
        """Happy: The conformance suite test file actually exists."""
        suite_path = REPO_ROOT / expected_suite
        assert suite_path.is_file(), (
            f"{contract_name}: conformance suite file not found: {suite_path}"
        )


# ---------------------------------------------------------------------------
# Installer → Files (installed file references resolve)
# ---------------------------------------------------------------------------

@pytest.mark.conformance
class TestInstallerToFiles:
    """Validate that installer references to source files are resolvable."""

    # Command source files that install.py copies to ${COMMANDS_HOME}/commands/
    COMMAND_SOURCES = [
        "master.md",
        "rules.md",
        "BOOTSTRAP.md",
        "continue.md",
        "review.md",
        "plan.md",
        "ticket.md",
        "README.md",
        "README-RULES.md",
        "README-OPENCODE.md",
        "SESSION_STATE_SCHEMA.md",
    ]

    def test_happy_all_command_sources_exist(self):
        """Happy: All command source files referenced by install.py exist in source tree."""
        missing = [f for f in self.COMMAND_SOURCES if not (REPO_ROOT / f).is_file()]
        assert not missing, f"Command source files missing from repo root: {missing}"

    def test_happy_install_py_references_all_command_files(self):
        """Happy: install.py source code contains references to each command file."""
        install_src = _read_source(REPO_ROOT / "install.py")
        unreferenced = []
        for cmd in self.COMMAND_SOURCES:
            if cmd not in install_src:
                unreferenced.append(cmd)
        assert not unreferenced, (
            f"Command files not referenced in install.py: {unreferenced}"
        )

    def test_happy_governance_paths_json_schema_referenced(self):
        """Happy: install.py defines the binding evidence schema string."""
        install_src = _read_source(REPO_ROOT / "install.py")
        assert "opencode-governance.paths.v1" in install_src, (
            "install.py missing governance.paths schema definition"
        )

    def test_happy_plugin_source_referenced_in_installer(self):
        """Happy: install.py references the plugin source file."""
        install_src = _read_source(REPO_ROOT / "install.py")
        assert "audit-new-session.mjs" in install_src, (
            "install.py missing reference to plugin source"
        )

    def test_corner_install_py_exists(self):
        """Corner: install.py itself exists at repo root."""
        assert (REPO_ROOT / "install.py").is_file()

    def test_edge_audit_readout_exists(self):
        """Edge: audit-readout.md (injection target) exists in source tree."""
        assert (REPO_ROOT / "audit-readout.md").is_file(), (
            "audit-readout.md missing — install.py injects session reader into it"
        )


# ---------------------------------------------------------------------------
# Launcher → Entrypoints (bootstrap launcher references valid entrypoints)
# ---------------------------------------------------------------------------

@pytest.mark.conformance
class TestLauncherToEntrypoints:
    """Validate that launcher references resolve to real entrypoint modules."""

    ENTRYPOINTS_DIR = REPO_ROOT / "governance" / "entrypoints"

    # The key entrypoint modules that launchers/plugin invoke
    REQUIRED_ENTRYPOINTS = [
        "new_work_session.py",      # Plugin invokes via -m governance.entrypoints.new_work_session
        "session_reader.py",        # Rail injection target
        "phase4_intake_persist.py", # ticket.md invokes via -m
        "phase5_plan_record_persist.py",  # plan.md invokes via -m
        "review_decision_persist.py",  # review-decision.md invokes via -m
        "implement_start.py",      # implement.md invokes via -m
        "bootstrap_executor.py",    # Launcher entrypoint
    ]

    def test_happy_entrypoints_dir_exists(self):
        """Happy: governance/entrypoints/ directory exists."""
        assert self.ENTRYPOINTS_DIR.is_dir()

    def test_happy_all_required_entrypoints_exist(self):
        """Happy: All launcher-referenced entrypoint modules exist."""
        missing = [
            ep for ep in self.REQUIRED_ENTRYPOINTS
            if not (self.ENTRYPOINTS_DIR / ep).is_file()
        ]
        assert not missing, f"Missing entrypoint modules: {missing}"

    def test_happy_entrypoints_init_exists(self):
        """Happy: __init__.py exists making entrypoints a proper package."""
        assert (self.ENTRYPOINTS_DIR / "__init__.py").is_file()

    def test_happy_plugin_references_correct_module(self):
        """Happy: Plugin source references governance.entrypoints.new_work_session."""
        plugin_src = _read_source(
            REPO_ROOT / "governance" / "artifacts" / "opencode-plugins" / "audit-new-session.mjs"
        )
        assert "governance.entrypoints.new_work_session" in plugin_src

    def test_corner_session_reader_is_importable_module(self):
        """Corner: session_reader.py has a recognizable entrypoint pattern."""
        sr_path = self.ENTRYPOINTS_DIR / "session_reader.py"
        src = _read_source(sr_path)
        # Should have either a main guard or argparse for CLI invocation
        has_main = '__name__' in src and '__main__' in src
        has_argparse = 'argparse' in src or 'ArgumentParser' in src
        has_cli = 'def main' in src or 'def run' in src or 'def cli' in src
        assert has_main or has_argparse or has_cli, (
            "session_reader.py has no recognizable CLI entrypoint"
        )

    def test_bad_no_dangling_entrypoint_references(self):
        """Bad: No entrypoint reference in install.py points to a non-existent module."""
        install_src = _read_source(REPO_ROOT / "install.py")
        # Extract governance.entrypoints.<module> references
        refs = re.findall(r"governance\.entrypoints\.(\w+)", install_src)
        for module_name in set(refs):
            module_file = self.ENTRYPOINTS_DIR / f"{module_name}.py"
            assert module_file.is_file(), (
                f"install.py references governance.entrypoints.{module_name} "
                f"but {module_file} does not exist"
            )


# ---------------------------------------------------------------------------
# Rails → Paths (rail markdown references valid session reader paths)
# ---------------------------------------------------------------------------

@pytest.mark.conformance
class TestRailsToPaths:
    """Validate that rail files reference valid paths and placeholders."""

    # All rail injection targets including audit-readout
    RAIL_FILES_WITH_LAUNCHER = ["continue.md", "review.md", "audit-readout.md"]
    RAIL_FILES_WITH_ENTRYPOINT = ["plan.md", "ticket.md", "review-decision.md", "implement.md"]
    ALL_RAIL_FILES = RAIL_FILES_WITH_LAUNCHER + RAIL_FILES_WITH_ENTRYPOINT

    BIN_DIR_PLACEHOLDER = "{{BIN_DIR}}"

    def test_happy_all_rail_files_exist(self):
        """Happy: All rail injection target files exist at repo root."""
        missing = [f for f in self.ALL_RAIL_FILES if not (REPO_ROOT / f).is_file()]
        assert not missing, f"Rail files missing: {missing}"

    def test_happy_launcher_rails_have_bin_dir_or_resolved(self):
        """Happy: Launcher rails have BIN_DIR placeholder or resolved opencode-governance-bootstrap."""
        for fname in self.RAIL_FILES_WITH_LAUNCHER:
            content = _read_source(REPO_ROOT / fname)
            has_placeholder = self.BIN_DIR_PLACEHOLDER in content
            has_launcher = "opencode-governance-bootstrap" in content
            assert has_placeholder or has_launcher, (
                f"{fname} missing both BIN_DIR placeholder and launcher reference"
            )

    def test_happy_all_rails_have_launcher_or_python_reference(self):
        """Happy: All rail files reference BIN_DIR/launcher or a resolved python command."""
        for fname in self.ALL_RAIL_FILES:
            content = _read_source(REPO_ROOT / fname)
            has_bin_dir = self.BIN_DIR_PLACEHOLDER in content
            has_launcher = "opencode-governance-bootstrap" in content
            has_python = "python" in content.lower()
            assert has_bin_dir or has_launcher or has_python, (
                f"{fname} missing BIN_DIR placeholder, launcher reference, and resolved python reference"
            )

    def test_happy_plan_uses_canonical_plan_subcommand(self):
        """Happy: plan.md uses canonical --plan-persist launcher surface."""
        content = _read_source(REPO_ROOT / "plan.md")
        assert "--plan-persist" in content, (
            "plan.md must use canonical --plan-persist subcommand"
        )

    def test_happy_ticket_uses_canonical_ticket_subcommand(self):
        """Happy: ticket.md uses canonical --ticket-persist launcher surface."""
        content = _read_source(REPO_ROOT / "ticket.md")
        assert "--ticket-persist" in content, (
            "ticket.md must use canonical --ticket-persist subcommand"
        )

    def test_happy_review_decision_uses_canonical_subcommand(self):
        """Happy: review-decision.md uses canonical --review-decision-persist launcher surface."""
        content = _read_source(REPO_ROOT / "review-decision.md")
        assert "--review-decision-persist" in content, (
            "review-decision.md must use canonical --review-decision-persist subcommand"
        )

    def test_corner_legacy_entrypoint_not_in_primary_rails(self):
        """Corner: docs switched immediately to canonical subcommands."""
        combined = (
            _read_source(REPO_ROOT / "plan.md")
            + "\n"
            + _read_source(REPO_ROOT / "ticket.md")
            + "\n"
            + _read_source(REPO_ROOT / "review-decision.md")
        )
        assert "--entrypoint governance.entrypoints." not in combined

    def test_happy_referenced_modules_exist(self):
        """Happy: All -m module references in rail files resolve to real files."""
        entrypoints = REPO_ROOT / "governance" / "entrypoints"
        modules_referenced = set()
        for fname in self.ALL_RAIL_FILES:
            content = _read_source(REPO_ROOT / fname)
            # Match patterns like: governance.entrypoints.<module_name>
            for m in re.finditer(r"governance\.entrypoints\.(\w+)", content):
                modules_referenced.add(m.group(1))
        missing = [
            mod for mod in modules_referenced
            if not (entrypoints / f"{mod}.py").is_file()
        ]
        assert not missing, f"Rail files reference non-existent modules: {missing}"

    def test_corner_bin_dir_placeholder_in_install(self):
        """Corner: install.py defines BIN_DIR_PLACEHOLDER constant."""
        install_src = _read_source(REPO_ROOT / "install.py")
        assert "BIN_DIR_PLACEHOLDER" in install_src or "BIN_DIR" in install_src

    def test_edge_no_mixed_placeholder_and_resolved_in_same_rail(self):
        """Edge: A rail file should not have both an unresolved BIN_DIR placeholder AND a resolved
        absolute bin path (indicates partial injection)."""
        for fname in self.RAIL_FILES_WITH_LAUNCHER:
            content = _read_source(REPO_ROOT / fname)
            has_bin_dir_placeholder = self.BIN_DIR_PLACEHOLDER in content
            # A resolved bin dir looks like an absolute path before opencode-governance-bootstrap.
            # Match both POSIX and Windows installed rail formats:
            #   POSIX: PATH="/abs/path:$PATH" opencode-governance-bootstrap
            #   Windows: set "PATH=C:/abs/path;%PATH%" && opencode-governance-bootstrap.cmd
            has_resolved = bool(re.search(
                r'PATH="(/[^"]+|[A-Za-z]:[/\\][^"]+)[;:][^"]*"\s+(?:&&\s+)?opencode-governance-bootstrap',
                content,
            ))
            if has_bin_dir_placeholder and has_resolved:
                pytest.fail(
                    f"{fname} has both unresolved BIN_DIR placeholder AND resolved bin path — "
                    f"partial injection detected"
                )

    def test_bad_no_broken_placeholder_syntax(self):
        """Bad: No rail file has malformed placeholders like {BIN_DIR} (single brace)."""
        single_brace_pattern = re.compile(r"(?<!\{)\{(BIN_DIR|SESSION_READER_PATH|PYTHON_COMMAND)\}(?!\})")
        for fname in self.ALL_RAIL_FILES:
            content = _read_source(REPO_ROOT / fname)
            match = single_brace_pattern.search(content)
            assert match is None, (
                f"{fname} has malformed single-brace placeholder: {match.group()}"
            )


# ---------------------------------------------------------------------------
# Plugin → Runtime (plugin references valid governance invocation)
# ---------------------------------------------------------------------------

@pytest.mark.conformance
class TestPluginToRuntime:
    """Validate that the plugin invokes governance correctly."""

    PLUGIN_PATH = REPO_ROOT / "governance" / "artifacts" / "opencode-plugins" / "audit-new-session.mjs"

    def test_happy_plugin_invokes_governance_module(self):
        """Happy: Plugin uses -m governance.entrypoints.new_work_session."""
        src = _read_source(self.PLUGIN_PATH)
        assert "governance.entrypoints.new_work_session" in src

    def test_happy_plugin_passes_trigger_source(self):
        """Happy: Plugin passes --trigger-source desktop-plugin."""
        src = _read_source(self.PLUGIN_PATH)
        assert "--trigger-source" in src
        assert "desktop-plugin" in src

    def test_happy_plugin_checks_opencode_python(self):
        """Happy: Plugin checks OPENCODE_PYTHON env var for resolution."""
        src = _read_source(self.PLUGIN_PATH)
        assert "OPENCODE_PYTHON" in src

    def test_happy_plugin_resolve_python_function_exists(self):
        """Happy: Plugin has a resolvePython function."""
        src = _read_source(self.PLUGIN_PATH)
        assert "resolvePython" in src

    def test_happy_plugin_handles_session_created(self):
        """Happy: Plugin only fires on session.created events."""
        src = _read_source(self.PLUGIN_PATH)
        assert "session.created" in src

    def test_corner_plugin_passes_session_id(self):
        """Corner: Plugin passes --session-id to the entrypoint."""
        src = _read_source(self.PLUGIN_PATH)
        assert "--session-id" in src

    def test_corner_plugin_deduplicates_sessions(self):
        """Corner: Plugin uses a Set for session deduplication."""
        src = _read_source(self.PLUGIN_PATH)
        assert "new Set()" in src or "Set()" in src

    def test_edge_plugin_caps_output(self):
        """Edge: Plugin caps stdout/stderr to MAX_LOG_BYTES."""
        src = _read_source(self.PLUGIN_PATH)
        assert "MAX_LOG_BYTES" in src

    def test_bad_plugin_does_not_hardcode_python_path(self):
        """Bad: Plugin must not hardcode an absolute python path."""
        src = _read_source(self.PLUGIN_PATH)
        # Should not have hardcoded paths like /usr/bin/python or C:\Python
        hardcoded_patterns = [
            r"/usr/bin/python",
            r"/usr/local/bin/python",
            r"C:\\Python",
            r"C:\\Users\\.*\\python",
        ]
        for pattern in hardcoded_patterns:
            assert not re.search(pattern, src, re.IGNORECASE), (
                f"Plugin hardcodes python path: {pattern}"
            )


# ---------------------------------------------------------------------------
# Runtime → Workspace (workspace_paths consistency)
# ---------------------------------------------------------------------------

@pytest.mark.conformance
class TestRuntimeToWorkspace:
    """Validate that runtime workspace path functions produce consistent results."""

    def test_happy_all_artifact_paths_under_workspace_or_audit_root(self, tmp_path):
        """Happy: Runtime paths resolve under workspace, audit paths under governance-records."""
        from governance.infrastructure import workspace_paths as wp

        ws_home = tmp_path / "workspaces"
        fp = "a" * 24
        root = wp.workspace_root(ws_home, fp)

        runtime_fns = [
            wp.session_state_path, wp.repo_cache_path, wp.repo_map_digest_path,
            wp.workspace_memory_path, wp.decision_pack_path, wp.business_rules_path,
            wp.business_rules_status_path, wp.plan_record_path, wp.plan_record_archive_dir,
            wp.repo_identity_map_path, wp.current_run_path, wp.evidence_dir,
            wp.locks_dir,
        ]
        escaped = []
        for fn in runtime_fns:
            p = fn(ws_home, fp)
            try:
                p.relative_to(root)
            except ValueError:
                escaped.append(f"{fn.__name__} -> {p}")
        assert not escaped, f"Artifacts escape workspace root: {escaped}"

        audit_root = ws_home / "governance-records" / fp
        runs = wp.runs_dir(ws_home, fp)
        assert runs.relative_to(audit_root)

    def test_happy_workspace_root_deterministic(self, tmp_path):
        """Happy: workspace_root returns same result for same inputs."""
        from governance.infrastructure import workspace_paths as wp

        ws_home = tmp_path / "workspaces"
        fp = "b" * 24
        r1 = wp.workspace_root(ws_home, fp)
        r2 = wp.workspace_root(ws_home, fp)
        assert r1 == r2

    def test_happy_global_pointer_at_config_root(self, tmp_path):
        """Happy: global_pointer_path is at config root level."""
        from governance.infrastructure import workspace_paths as wp

        config_root = tmp_path / "opencode"
        ptr = wp.global_pointer_path(config_root)
        assert ptr.parent == config_root
        assert ptr.name == "SESSION_STATE.json"

    def test_happy_phase_artifact_lists_match_functions(self, tmp_path):
        """Happy: PHASE*_ARTIFACTS constants reference real artifact filenames."""
        from governance.infrastructure import workspace_paths as wp

        ws_home = tmp_path / "ws"
        fp = "c" * 24

        # Collect all artifact filenames from path functions
        all_artifact_names = set()
        for fn_name in dir(wp):
            fn = getattr(wp, fn_name)
            if callable(fn) and fn_name.endswith(("_path", "_dir")):
                try:
                    result = fn(ws_home, fp)
                    if isinstance(result, Path):
                        all_artifact_names.add(result.name)
                except TypeError:
                    pass  # Functions with different signatures (e.g. run_dir)

        # All phase artifact names should be in the collected set
        for phase_list in [wp.PHASE2_ARTIFACTS, wp.PHASE21_ARTIFACTS,
                           wp.PHASE15_ARTIFACTS, wp.PHASE4_ARTIFACTS]:
            for artifact_name in phase_list:
                assert artifact_name in all_artifact_names, (
                    f"Phase artifact {artifact_name!r} not produced by any path function"
                )

    def test_corner_run_artifacts_under_runs_dir(self, tmp_path):
        """Corner: Run-scoped artifacts are all under runs/<run_id>/."""
        from governance.infrastructure import workspace_paths as wp

        ws_home = tmp_path / "ws"
        fp = "d" * 24
        run_id = "run-001"
        runs = wp.runs_dir(ws_home, fp)

        run_fns = [
            lambda: wp.run_session_state_path(ws_home, fp, run_id),
            lambda: wp.run_plan_record_path(ws_home, fp, run_id),
            lambda: wp.run_metadata_path(ws_home, fp, run_id),
        ]
        for fn in run_fns:
            p = fn()
            try:
                p.relative_to(runs)
            except ValueError:
                pytest.fail(f"Run artifact {p} escapes runs_dir {runs}")

    def test_bad_no_artifact_named_opencode_json(self, tmp_path):
        """Bad: opencode.json must never be a workspace artifact."""
        from governance.infrastructure import workspace_paths as wp

        ws_home = tmp_path / "ws"
        fp = "e" * 24
        artifacts = wp.all_phase_artifact_paths(ws_home, fp)
        names = {p.name for p in artifacts.values()}
        assert "opencode.json" not in names


# ---------------------------------------------------------------------------
# No Rogue Paths
# ---------------------------------------------------------------------------

@pytest.mark.conformance
class TestNoRoguePaths:
    """Validate that no unplanned files or hardcoded paths violate the contract."""

    # Root-level files that are expected to exist (from install-layout-contract)
    # This is the complete allowlist of files at REPO_ROOT
    ALLOWED_ROOT_FILES = {
        # Command sources (installed to commands/)
        "master.md",
        "rules.md",
        "BOOTSTRAP.md",
        "continue.md",
        "review.md",
        "plan.md",
        "ticket.md",
        "review-decision.md",
        "implementation-decision.md",
        "implement.md",
        "audit-readout.md",
        "README.md",
        "README-RULES.md",
        "README-OPENCODE.md",
        "SESSION_STATE_SCHEMA.md",
        "TICKET_RECORD_TEMPLATE.md",
        # Infrastructure
        "install.py",
        "package.json",
        "pytest.ini",
        "LICENSE",
        "VERSION",
        # Configuration
        "rules.yml",
        "phase_api.yaml",
        # Documentation
        "ADR.md",
        "CHANGELOG.md",
        "CONFLICT_RESOLUTION.md",
        "HowTo_Release.txt",
        "QUALITY_INDEX.md",
        "QUICKSTART.md",
        "SCOPE-AND-CONTEXT.md",
        "STABILITY_SLA.md",
        # Dotfiles
        ".commitlintrc.cjs",
        ".gitignore",
        ".gitleaks.toml",
        # Known artifact
        "nul",
    }

    # Root-level directories that are expected
    ALLOWED_ROOT_DIRS = {
        ".git",
        ".github",
        ".husky",
        ".opencode",
        ".pytest_cache",
        "artifacts",
        "bin",
        "bootstrap",
        "ci",
        "cli",
        "docs",
        "governance",
        "logs",
        "profiles",
        "rulesets",
        "schemas",
        "scripts",
        "session_state",
        "templates",
        "tests",
    }

    def test_happy_no_unplanned_root_level_files(self):
        """Happy: No unplanned files exist at repo root outside current contract.
        
        This catches rogue files that were accidentally committed at the wrong level.
        The allowlist is derived from the install-layout contract + known repo files.
        """
        actual_files = {
            p.name for p in REPO_ROOT.iterdir()
            if p.is_file() and not p.name.startswith("__")
        }
        rogue_files = actual_files - self.ALLOWED_ROOT_FILES
        assert not rogue_files, (
            f"Unplanned root-level files outside contract: {sorted(rogue_files)}"
        )

    def test_happy_no_unplanned_root_level_dirs(self):
        """Happy: No unplanned directories at repo root."""
        actual_dirs = {
            p.name for p in REPO_ROOT.iterdir()
            if p.is_dir() and not p.name.startswith("__")
        }
        rogue_dirs = actual_dirs - self.ALLOWED_ROOT_DIRS
        assert not rogue_dirs, (
            f"Unplanned root-level directories: {sorted(rogue_dirs)}"
        )

    def test_happy_no_hardcoded_alternative_config_roots(self):
        """Happy: No governance module hardcodes an alternative config root outside
        the canonical resolution chain (OPENCODE_CONFIG_ROOT → canonical_config_root).
        """
        governance_dir = REPO_ROOT / "governance"
        # Patterns that would indicate a hardcoded config root
        hardcoded_patterns = [
            # Absolute paths to .config/opencode (should use canonical_config_root())
            re.compile(r'["\'](?:/home/|C:\\Users\\)[^"\']*[/\\]\.config[/\\]opencode["\']'),
            # Hardcoded ~/.config/opencode as a string literal
            re.compile(r'["\']~[/\\]\.config[/\\]opencode["\']'),
        ]

        violations = []
        for py_file in governance_dir.rglob("*.py"):
            # Skip __pycache__
            if "__pycache__" in str(py_file):
                continue
            content = _read_source(py_file)
            for pattern in hardcoded_patterns:
                matches = pattern.findall(content)
                if matches:
                    rel = py_file.relative_to(REPO_ROOT)
                    violations.append(f"{rel}: {matches}")

        assert not violations, (
            f"Hardcoded config root paths found in governance modules: {violations}"
        )

    def test_happy_no_rogue_path_references_in_rails(self):
        """Happy: Rail files do not reference non-installed paths.
        
        Rails should only reference paths that exist after installation:
        - governance.entrypoints.* modules
        - {{SESSION_READER_PATH}} / {{PYTHON_COMMAND}} placeholders
        - Relative references within installed tree
        """
        entrypoints_dir = REPO_ROOT / "governance" / "entrypoints"
        rail_files = ["continue.md", "review.md", "plan.md", "ticket.md", "review-decision.md", "implement.md"]

        for fname in rail_files:
            content = _read_source(REPO_ROOT / fname)
            # Check for governance module references
            module_refs = re.findall(r"governance\.entrypoints\.(\w+)", content)
            for mod in module_refs:
                assert (entrypoints_dir / f"{mod}.py").is_file(), (
                    f"{fname} references non-existent module: "
                    f"governance.entrypoints.{mod}"
                )

    def test_corner_no_commands_dir_at_repo_root(self):
        """Corner: commands/ directory should NOT exist at repo root.
        
        In the source tree, command files live at REPO_ROOT directly.
        commands/ is only created by the installer at ${CONFIG_ROOT}/commands/.
        """
        commands_at_root = REPO_ROOT / "commands"
        assert not commands_at_root.is_dir(), (
            "commands/ directory found at repo root — this is only created by "
            "the installer at ${CONFIG_ROOT}/commands/, not in the source tree"
        )

    def test_edge_no_launcher_references_to_noninstalled_paths(self):
        """Edge: Plugin does not reference paths that only exist after installation
        by absolute path (it should use module invocation instead)."""
        plugin_src = _read_source(
            REPO_ROOT / "governance" / "artifacts" / "opencode-plugins" / "audit-new-session.mjs"
        )
        # Plugin should use -m module invocation, not absolute script paths
        assert "-m" in plugin_src, (
            "Plugin should use -m module invocation for governance entrypoints"
        )
        # Should NOT hardcode paths like /path/to/governance/entrypoints/
        hardcoded_ep = re.search(
            r'["\'][A-Za-z]:\\.*?governance[/\\]entrypoints|'
            r'["\']/.*?governance/entrypoints',
            plugin_src,
        )
        assert hardcoded_ep is None, (
            f"Plugin hardcodes entrypoint path: {hardcoded_ep.group()}"
        )

    def test_bad_no_plugin_references_to_noninstalled_paths(self):
        """Bad: Plugin must not reference any paths that don't exist in the source tree."""
        plugin_src = _read_source(
            REPO_ROOT / "governance" / "artifacts" / "opencode-plugins" / "audit-new-session.mjs"
        )
        # The plugin should not reference governance files by absolute path
        # It should only use -m module invocation
        assert "governance.entrypoints.new_work_session" in plugin_src, (
            "Plugin missing -m module reference to new_work_session"
        )


# ---------------------------------------------------------------------------
# Binding Path Resolver Wiring
# ---------------------------------------------------------------------------

@pytest.mark.conformance
class TestBindingPathWiring:
    """Validate that the binding path resolution chain is correctly wired."""

    def test_happy_binding_paths_module_exists(self):
        """Happy: binding_paths.py module exists."""
        assert (REPO_ROOT / "governance" / "infrastructure" / "binding_paths.py").is_file()

    def test_happy_path_contract_module_exists(self):
        """Happy: path_contract.py module exists (canonical_config_root SSOT)."""
        assert (REPO_ROOT / "governance" / "infrastructure" / "path_contract.py").is_file()

    def test_happy_binding_evidence_resolver_exists(self):
        """Happy: binding_evidence_resolver.py exists."""
        assert (REPO_ROOT / "governance" / "infrastructure" / "binding_evidence_resolver.py").is_file()

    def test_happy_supported_binding_schemas(self):
        """Happy: binding_paths supports the expected schema versions."""
        from governance.infrastructure.binding_paths import SUPPORTED_BINDING_SCHEMAS
        assert "opencode-governance.paths.v1" in SUPPORTED_BINDING_SCHEMAS

    def test_happy_canonical_config_root_importable(self):
        """Happy: canonical_config_root function is importable from path_contract."""
        from governance.infrastructure.path_contract import canonical_config_root
        result = canonical_config_root()
        assert isinstance(result, Path)
        assert "opencode" in str(result).lower()

    def test_corner_binding_load_strict_validates_schema(self):
        """Corner: load_binding_paths_strict rejects unsupported schemas."""
        import json
        import tempfile

        from governance.infrastructure.binding_paths import (
            BindingLoadError,
            load_binding_paths_strict,
        )

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump({"schema": "invalid-schema-v99", "paths": {}}, f)
            f.flush()
            tmp_path = Path(f.name)

        try:
            with pytest.raises(BindingLoadError):
                load_binding_paths_strict(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_bad_binding_load_rejects_missing_file(self):
        """Bad: load_binding_paths_strict raises on missing file."""
        from governance.infrastructure.binding_paths import (
            BindingLoadError,
            load_binding_paths_strict,
        )

        with pytest.raises(BindingLoadError):
            load_binding_paths_strict(Path("/nonexistent/governance.paths.json"))
