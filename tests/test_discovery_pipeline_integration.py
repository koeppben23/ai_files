#!/usr/bin/env python3
"""Integration tests for discovery → artifacts pipeline.

Proves that Structural Discovery + Semantic Discovery flow into artifacts
and produce meaningful output, not just seed/placeholder content.

Tests:
- Orchestrator runs successfully with discovery
- repo-cache.yaml contains real structural facts
- repo-map-digest.md is not seed-heavy
- workspace-memory.yaml contains semantic facts
- decision-pack.md contains curated decisions
- Full pipeline from repo to artifacts works
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def repo_with_structure(tmp_path: Path) -> Path:
    """Create a git repo with realistic structure for integration testing."""
    repo = tmp_path / "integration_test_repo"
    repo.mkdir()

    # Initialize git
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, capture_output=True, check=True)

    # Create realistic structure
    (repo / "pyproject.toml").write_text('[project]\nname = "test-repo"\nversion = "1.0"\n', encoding="utf-8")

    # Python modules
    (repo / "mymodule").mkdir()
    (repo / "mymodule" / "__init__.py").write_text('"""My module."""\n', encoding="utf-8")
    (repo / "mymodule" / "core.py").write_text(
        "def process():\n    '''Process data.'''\n    pass\n",
        encoding="utf-8",
    )

    # Governance modules
    (repo / "governance_runtime").mkdir()
    (repo / "governance_runtime" / "__init__.py").write_text("", encoding="utf-8")
    (repo / "governance_runtime" / "kernel.py").write_text(
        "from governance_runtime.infrastructure import emit_gate_failure\n",
        encoding="utf-8",
    )
    (repo / "governance_content").mkdir()
    (repo / "governance_content" / "__init__.py").write_text("", encoding="utf-8")

    # Spec
    (repo / "governance_spec").mkdir()
    (repo / "governance_spec" / "phase_api.yaml").write_text(
        "phases:\n  - id: 0\n    name: Bootstrap\n",
        encoding="utf-8",
    )

    # Tests
    (repo / "tests").mkdir()
    (repo / "tests" / "test_core.py").write_text(
        "def test_process():\n    assert True\n",
        encoding="utf-8",
    )
    (repo / "tests" / "test_kernel.py").write_text(
        "def test_kernel():\n    assert True\n",
        encoding="utf-8",
    )

    # Bin scripts
    (repo / "bin").mkdir()
    (repo / "bin" / "cli.py").write_text(
        "#!/usr/bin/env python3\nimport sys\nsys.exit(0)\n",
        encoding="utf-8",
    )

    # Documentation
    (repo / "README.md").write_text("# Test Repo\n\nA test repository.\n", encoding="utf-8")
    (repo / "CONTRIBUTING.md").write_text("# Contributing\n\nGuidelines.\n", encoding="utf-8")

    # Config
    (repo / ".opencode").mkdir()
    (repo / ".opencode" / "governance-repo-policy.json").write_text(
        json.dumps({
            "schema": "opencode-governance-repo-policy.v1",
            "repoFingerprint": "abc123def456789012345678",
            "operatingMode": "solo",
        }),
        encoding="utf-8",
    )

    # Commit
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=repo, capture_output=True, check=True)

    return repo


@pytest.fixture
def config_root(tmp_path: Path) -> Path:
    """Create a config root for testing."""
    config = tmp_path / "config"
    (config / "commands").mkdir(parents=True)
    (config / "workspaces").mkdir(parents=True)

    # Copy governance_runtime for import
    import shutil
    checkout = Path(__file__).resolve().parents[1]
    if (checkout / "governance_runtime").is_dir():
        shutil.copytree(
            checkout / "governance_runtime",
            config / "commands" / "governance_runtime",
            dirs_exist_ok=True,
        )
    if (checkout / "artifacts").is_dir():
        shutil.copytree(
            checkout / "artifacts",
            config / "commands" / "artifacts",
            dirs_exist_ok=True,
        )

    # Create governance.paths.json
    paths_config = {
        "schema": "opencode-governance.paths.v1",
        "paths": {
            "configRoot": str(config),
            "commandsHome": str(config / "commands"),
            "workspacesHome": str(config / "workspaces"),
        },
    }
    (config / "commands" / "governance.paths.json").write_text(
        json.dumps(paths_config),
        encoding="utf-8",
    )

    return config


class TestFullPipelineIntegration:
    """Full pipeline integration tests."""

    def test_orchestrator_runs_successfully(
        self, repo_with_structure: Path, config_root: Path
    ) -> None:
        """Test that orchestrator completes without error."""
        result = subprocess.run(
            [
                "python3",
                "-m",
                "governance_runtime.entrypoints.persist_workspace_artifacts_orchestrator",
                "--repo-root",
                str(repo_with_structure),
                "--config-root",
                str(config_root),
                "--require-phase2",
                "--skip-lock",
                "--quiet",
            ],
            capture_output=True,
            text=True,
            cwd=config_root / "commands",
            env={
                "PYTHONPATH": str(config_root / "commands"),
                "HOME": str(config_root.parent),
            },
        )

        assert result.returncode == 0, f"stdout: {result.stdout[:500]}\nstderr: {result.stderr[:500]}"

    def test_repo_cache_has_structural_facts(
        self, repo_with_structure: Path, config_root: Path
    ) -> None:
        """Test that repo-cache.yaml contains real structural facts."""
        # Run orchestrator
        subprocess.run(
            [
                "python3",
                "-m",
                "governance_runtime.entrypoints.persist_workspace_artifacts_orchestrator",
                "--repo-root",
                str(repo_with_structure),
                "--config-root",
                str(config_root),
                "--require-phase2",
                "--skip-lock",
                "--quiet",
            ],
            capture_output=True,
            text=True,
            cwd=config_root / "commands",
            env={
                "PYTHONPATH": str(config_root / "commands"),
                "HOME": str(config_root.parent),
            },
            check=True,
        )

        # Find the workspace
        workspaces = list((config_root / "workspaces").glob("*/repo-cache.yaml"))
        assert len(workspaces) >= 1, "No repo-cache.yaml found"

        cache = workspaces[0].read_text()

        # Must have version
        assert "Version:" in cache

        # Must have repository type (not unknown)
        assert "RepositoryType:" in cache
        assert "unknown" not in cache.split("RepositoryType:")[1].split("\n")[0].lower()

        # Must have some structure
        assert "Modules:" in cache or "EntryPoints:" in cache

    def test_repo_map_digest_not_just_seeds(
        self, repo_with_structure: Path, config_root: Path
    ) -> None:
        """Test that repo-map-digest.md contains real content, not just seeds."""
        subprocess.run(
            [
                "python3",
                "-m",
                "governance_runtime.entrypoints.persist_workspace_artifacts_orchestrator",
                "--repo-root",
                str(repo_with_structure),
                "--config-root",
                str(config_root),
                "--require-phase2",
                "--skip-lock",
                "--quiet",
            ],
            capture_output=True,
            text=True,
            cwd=config_root / "commands",
            env={
                "PYTHONPATH": str(config_root / "commands"),
                "HOME": str(config_root.parent),
            },
            check=True,
        )

        workspaces = list((config_root / "workspaces").glob("*/repo-map-digest.md"))
        assert len(workspaces) >= 1, "No repo-map-digest.md found"

        digest = workspaces[0].read_text()

        # Must have content
        assert len(digest) > 100, "repo-map-digest.md is too short"

        # Should have real repository type, not placeholder
        assert "RepositoryType:" in digest

        # Should have module or entry point info
        has_content = (
            "EntryPoints:" in digest
            or "Modules:" in digest
            or "DataStores:" in digest
        )
        assert has_content, "No structural content in repo-map-digest.md"

    def test_workspace_memory_has_semantic_facts(
        self, repo_with_structure: Path, config_root: Path
    ) -> None:
        """Test that workspace-memory.yaml contains semantic facts."""
        subprocess.run(
            [
                "python3",
                "-m",
                "governance_runtime.entrypoints.persist_workspace_artifacts_orchestrator",
                "--repo-root",
                str(repo_with_structure),
                "--config-root",
                str(config_root),
                "--require-phase2",
                "--skip-lock",
                "--quiet",
            ],
            capture_output=True,
            text=True,
            cwd=config_root / "commands",
            env={
                "PYTHONPATH": str(config_root / "commands"),
                "HOME": str(config_root.parent),
            },
            check=True,
        )

        workspaces = list((config_root / "workspaces").glob("*/workspace-memory.yaml"))
        assert len(workspaces) >= 1, "No workspace-memory.yaml found"

        memory = workspaces[0].read_text()

        # Must have version 2.0 (semantic version)
        assert 'Version: "2.0"' in memory or "Version: 2.0" in memory

        # Must have conventions or patterns (not empty)
        assert "Conventions:" in memory

        # Should not be empty braces
        assert "{}" not in memory or "Conventions: {}" not in memory

        # Should have provenance
        assert "Provenance:" in memory
        assert "evidence-required" in memory

    def test_decision_pack_has_curated_decisions(
        self, repo_with_structure: Path, config_root: Path
    ) -> None:
        """Test that decision-pack.md contains curated decisions."""
        subprocess.run(
            [
                "python3",
                "-m",
                "governance_runtime.entrypoints.persist_workspace_artifacts_orchestrator",
                "--repo-root",
                str(repo_with_structure),
                "--config-root",
                str(config_root),
                "--require-phase2",
                "--skip-lock",
                "--quiet",
            ],
            capture_output=True,
            text=True,
            cwd=config_root / "commands",
            env={
                "PYTHONPATH": str(config_root / "commands"),
                "HOME": str(config_root.parent),
            },
            check=True,
        )

        workspaces = list((config_root / "workspaces").glob("*/decision-pack.md"))
        assert len(workspaces) >= 1, "No decision-pack.md found"

        decision = workspaces[0].read_text()

        # Must have decision header
        assert "Decision Pack" in decision

        # Must have multiple decisions (D-001, D-002, etc.)
        decision_count = decision.count("D-001:") + decision.count("D-002:") + decision.count("D-003:")
        assert decision_count >= 2, f"Expected multiple decisions, found {decision_count}"

        # Must have status fields
        assert "Status:" in decision

        # Must have policy fields
        assert "Policy:" in decision


class TestDiscoveryFactsIntegration:
    """Test that discovery facts flow correctly into artifacts."""

    def test_structural_facts_render_to_yaml(
        self, repo_with_structure: Path
    ) -> None:
        """Test that structural facts render correctly to YAML."""
        from governance_runtime.infrastructure.repo_discovery import discover_structural_facts
        from artifacts.writers.repo_cache import render_repo_cache

        facts = discover_structural_facts(repo_with_structure)

        yaml_content = render_repo_cache(
            date="2026-03-30",
            repo_name="test-repo",
            profile="solo",
            profile_evidence="test",
            discovery=facts,
        )

        # Must have YAML structure
        assert "RepoCache:" in yaml_content
        assert "Version:" in yaml_content

        # Must have real repository type
        assert "RepositoryType:" in yaml_content

        # Should have modules if we have them
        if facts.modules:
            assert "Modules:" in yaml_content

    def test_semantic_facts_render_to_memory(
        self, repo_with_structure: Path
    ) -> None:
        """Test that semantic facts render correctly to workspace memory."""
        from governance_runtime.infrastructure.repo_discovery import discover_semantic_facts
        from artifacts.writers.workspace_memory import render_workspace_memory

        facts = discover_semantic_facts(repo_with_structure)

        memory_content = render_workspace_memory(
            date="2026-03-30",
            repo_name="test-repo",
            repo_fingerprint="abc123",
            semantic=facts,
        )

        # Must have workspace memory structure
        assert "WorkspaceMemory:" in memory_content

        # Must have conventions if we found any
        if facts.conventions:
            assert "Conventions:" in memory_content

        # Must have evidence mode
        assert "evidence-required" in memory_content

    def test_semantic_facts_render_to_decisions(
        self, repo_with_structure: Path
    ) -> None:
        """Test that semantic facts render to decisions."""
        from governance_runtime.infrastructure.repo_discovery import discover_semantic_facts
        from artifacts.writers.decision_pack import render_decision_pack_create

        facts = discover_semantic_facts(repo_with_structure)

        decision_content = render_decision_pack_create(
            date="2026-03-30",
            date_compact="20260330",
            repo_name="test-repo",
            semantic=facts,
        )

        # Must have decision pack structure
        assert "Decision Pack" in decision_content

        # Must have at least the business rules decision
        assert "D-" in decision_content

        # Should have status fields
        assert "Status:" in decision_content


class TestDiscoveryConsistency:
    """Test that discovery is consistent across runs."""

    def test_structural_facts_deterministic(
        self, repo_with_structure: Path
    ) -> None:
        """Test that structural facts are deterministic."""
        from governance_runtime.infrastructure.repo_discovery import discover_structural_facts

        facts1 = discover_structural_facts(repo_with_structure)
        facts2 = discover_structural_facts(repo_with_structure)

        assert facts1.repository_type == facts2.repository_type
        assert len(facts1.modules) == len(facts2.modules)
        assert len(facts1.entry_points) == len(facts2.entry_points)

    def test_semantic_facts_deterministic(
        self, repo_with_structure: Path
    ) -> None:
        """Test that semantic facts are deterministic."""
        from governance_runtime.infrastructure.repo_discovery import discover_semantic_facts

        facts1 = discover_semantic_facts(repo_with_structure)
        facts2 = discover_semantic_facts(repo_with_structure)

        assert len(facts1.ssots) == len(facts2.ssots)
        assert len(facts1.conventions) == len(facts2.conventions)
        assert len(facts1.patterns) == len(facts2.patterns)
