#!/usr/bin/env python3
"""Tests for governance_runtime.infrastructure.repo_discovery.deep_repo_discovery.

Tests cover:
- Happy paths for all discovery functions
- Edge cases (empty repos, malformed files)
- Evidence and confidence levels
- StructuralFacts composition
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def tmp_git_repo(tmp_path: Path) -> Path:
    """Create a minimal git repository for testing."""
    repo = tmp_path / "test_repo"
    repo.mkdir()
    # Initialize git repo
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, capture_output=True, check=True)
    # Create a README
    (repo / "README.md").write_text("# Test Repo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, capture_output=True, check=True)
    return repo


class TestDiscoverTopology:
    """Tests for discover_topology function."""

    def test_happy_path_python_app(self, tmp_git_repo: Path) -> None:
        """Test topology discovery for a Python app."""
        from governance_runtime.infrastructure.repo_discovery.deep_repo_discovery import discover_topology

        # Add pyproject.toml to indicate Python app
        (tmp_git_repo / "pyproject.toml").write_text('[project]\nname = "test"\n', encoding="utf-8")

        repo_type, layers, core_subsystems = discover_topology(tmp_git_repo)

        assert repo_type in {"app", "single-package", "library"}
        assert isinstance(layers, list)
        assert isinstance(core_subsystems, list)

    def test_happy_path_monorepo(self, tmp_git_repo: Path) -> None:
        """Test topology discovery for a monorepo."""
        from governance_runtime.infrastructure.repo_discovery.deep_repo_discovery import discover_topology

        # Create multiple governance modules (needs >2 layers for monorepo detection)
        (tmp_git_repo / "governance_runtime").mkdir()
        (tmp_git_repo / "governance_runtime" / "__init__.py").write_text("", encoding="utf-8")
        (tmp_git_repo / "governance_content").mkdir()
        (tmp_git_repo / "governance_content" / "__init__.py").write_text("", encoding="utf-8")
        (tmp_git_repo / "governance_spec").mkdir()
        (tmp_git_repo / "governance_spec" / "__init__.py").write_text("", encoding="utf-8")
        (tmp_git_repo / "bin").mkdir()  # Additional layer

        repo_type, layers, core_subsystems = discover_topology(tmp_git_repo)

        # With >2 layers, should be detected as monorepo
        assert repo_type == "monorepo"
        assert "governance_runtime" in layers
        assert "governance_content" in layers
        assert "governance_runtime" in core_subsystems

    def test_empty_repo(self, tmp_path: Path) -> None:
        """Test topology discovery for an empty directory (no git)."""
        from governance_runtime.infrastructure.repo_discovery.deep_repo_discovery import discover_topology

        repo_type, layers, core_subsystems = discover_topology(tmp_path)

        # Should still return valid results
        assert repo_type in {"single-package", "app", "library"}
        assert isinstance(layers, list)
        assert isinstance(core_subsystems, list)

    def test_no_git_marker(self, tmp_path: Path) -> None:
        """Test topology discovery for directory without .git."""
        from governance_runtime.infrastructure.repo_discovery.deep_repo_discovery import discover_topology

        repo_type, layers, core_subsystems = discover_topology(tmp_path)

        assert repo_type == "single-package"
        assert layers == []
        assert core_subsystems == []


class TestDiscoverModules:
    """Tests for discover_modules function."""

    def test_happy_path_with_modules(self, tmp_git_repo: Path) -> None:
        """Test module discovery with Python modules."""
        from governance_runtime.infrastructure.repo_discovery.deep_repo_discovery import discover_modules

        # Create a Python module
        (tmp_git_repo / "mymodule").mkdir()
        (tmp_git_repo / "mymodule" / "__init__.py").write_text("# mymodule\n", encoding="utf-8")
        (tmp_git_repo / "mymodule" / "core.py").write_text("def main(): pass\n", encoding="utf-8")

        modules = discover_modules(tmp_git_repo)

        assert len(modules) >= 1
        module_names = [m.name for m in modules]
        assert "mymodule" in module_names

        # Check evidence
        mymodule = next(m for m in modules if m.name == "mymodule")
        assert mymodule.evidence.confidence.value == "high"
        assert "file_exists" in mymodule.evidence.source

    def test_happy_path_with_js_module(self, tmp_git_repo: Path) -> None:
        """Test module discovery with JS module."""
        from governance_runtime.infrastructure.repo_discovery.deep_repo_discovery import discover_modules

        # Create a JS module
        (tmp_git_repo / "jsmodule").mkdir()
        (tmp_git_repo / "jsmodule" / "index.js").write_text("console.log('hello');\n", encoding="utf-8")

        modules = discover_modules(tmp_git_repo)

        module_names = [m.name for m in modules]
        assert "jsmodule" in module_names

    def test_no_modules(self, tmp_git_repo: Path) -> None:
        """Test module discovery with no modules."""
        from governance_runtime.infrastructure.repo_discovery.deep_repo_discovery import discover_modules

        modules = discover_modules(tmp_git_repo)

        # Should return empty list
        assert isinstance(modules, list)


class TestDiscoverEntryPoints:
    """Tests for discover_entry_points function."""

    def test_happy_path_with_bin(self, tmp_git_repo: Path) -> None:
        """Test entry point discovery with bin directory."""
        from governance_runtime.infrastructure.repo_discovery.deep_repo_discovery import discover_entry_points

        # Create bin directory with scripts
        (tmp_git_repo / "bin").mkdir()
        (tmp_git_repo / "bin" / "opencode-governance-bootstrap").write_text("#!/bin/bash\necho test\n", encoding="utf-8")
        (tmp_git_repo / "bin" / "cli.py").write_text("import sys\nsys.exit(0)\n", encoding="utf-8")

        entry_points = discover_entry_points(tmp_git_repo)

        assert len(entry_points) >= 2

        # Check bootstrap entry point
        bootstrap_eps = [ep for ep in entry_points if ep.kind == "bootstrap"]
        assert len(bootstrap_eps) >= 1

        # Check CLI entry point
        cli_eps = [ep for ep in entry_points if ep.kind == "cli"]
        assert len(cli_eps) >= 1

    def test_happy_path_with_commands(self, tmp_git_repo: Path) -> None:
        """Test entry point discovery with commands directory."""
        from governance_runtime.infrastructure.repo_discovery.deep_repo_discovery import discover_entry_points

        # Create commands directory
        (tmp_git_repo / "commands").mkdir()
        (tmp_git_repo / "commands" / "ticket.md").write_text("# Ticket Command\n", encoding="utf-8")

        entry_points = discover_entry_points(tmp_git_repo)

        command_eps = [ep for ep in entry_points if ep.kind == "command"]
        assert len(command_eps) >= 1

    def test_no_entry_points(self, tmp_git_repo: Path) -> None:
        """Test entry point discovery with no entry points."""
        from governance_runtime.infrastructure.repo_discovery.deep_repo_discovery import discover_entry_points

        entry_points = discover_entry_points(tmp_git_repo)

        assert isinstance(entry_points, list)


class TestDiscoverDataStores:
    """Tests for discover_data_stores function."""

    def test_happy_path_with_session_state(self, tmp_git_repo: Path) -> None:
        """Test data store discovery with session state file."""
        from governance_runtime.infrastructure.repo_discovery.deep_repo_discovery import discover_data_stores

        # Create workspace with session state
        (tmp_git_repo / "workspaces").mkdir()
        (tmp_git_repo / "workspaces" / "abc123").mkdir()
        (tmp_git_repo / "workspaces" / "abc123" / "SESSION_STATE.json").write_text('{"SESSION_STATE": {}}', encoding="utf-8")

        data_stores = discover_data_stores(tmp_git_repo)

        session_stores = [ds for ds in data_stores if ds.kind == "session_state"]
        assert len(session_stores) >= 1
        assert session_stores[0].schema_hint == "json"

    def test_happy_path_with_config(self, tmp_git_repo: Path) -> None:
        """Test data store discovery with config file."""
        from governance_runtime.infrastructure.repo_discovery.deep_repo_discovery import discover_data_stores

        # Create config file
        (tmp_git_repo / "opencode.json").write_text('{"version": "1.0"}', encoding="utf-8")

        data_stores = discover_data_stores(tmp_git_repo)

        config_stores = [ds for ds in data_stores if ds.kind == "config"]
        assert len(config_stores) >= 1

    def test_no_data_stores(self, tmp_git_repo: Path) -> None:
        """Test data store discovery with no data stores."""
        from governance_runtime.infrastructure.repo_discovery.deep_repo_discovery import discover_data_stores

        data_stores = discover_data_stores(tmp_git_repo)

        assert isinstance(data_stores, list)


class TestDiscoverBuildAndTooling:
    """Tests for discover_build_and_tooling function."""

    def test_happy_path_with_pyproject(self, tmp_git_repo: Path) -> None:
        """Test build discovery with pyproject.toml."""
        from governance_runtime.infrastructure.repo_discovery.deep_repo_discovery import discover_build_and_tooling

        (tmp_git_repo / "pyproject.toml").write_text('[project]\nname = "test"\n', encoding="utf-8")

        build = discover_build_and_tooling(tmp_git_repo)

        assert build.package_manager is not None
        assert "pip" in build.package_manager or "pyproject" in build.package_manager

    def test_happy_path_with_makefile(self, tmp_git_repo: Path) -> None:
        """Test build discovery with Makefile."""
        from governance_runtime.infrastructure.repo_discovery.deep_repo_discovery import discover_build_and_tooling

        (tmp_git_repo / "Makefile").write_text("all:\n\techo test\n", encoding="utf-8")

        build = discover_build_and_tooling(tmp_git_repo)

        assert "make" in build.ci_commands

    def test_happy_path_with_github_workflows(self, tmp_git_repo: Path) -> None:
        """Test build discovery with GitHub workflows."""
        from governance_runtime.infrastructure.repo_discovery.deep_repo_discovery import discover_build_and_tooling

        (tmp_git_repo / ".github").mkdir()
        (tmp_git_repo / ".github" / "workflows").mkdir()
        (tmp_git_repo / ".github" / "workflows" / "ci.yml").write_text("name: CI\n", encoding="utf-8")

        build = discover_build_and_tooling(tmp_git_repo)

        assert "github-actions" in build.ci_commands

    def test_no_config(self, tmp_git_repo: Path) -> None:
        """Test build discovery with no configuration."""
        from governance_runtime.infrastructure.repo_discovery.deep_repo_discovery import discover_build_and_tooling

        build = discover_build_and_tooling(tmp_git_repo)

        assert build.package_manager is None
        assert build.evidence.confidence.value == "high"


class TestDiscoverTestingSurface:
    """Tests for discover_testing_surface function."""

    def test_happy_path_with_tests(self, tmp_git_repo: Path) -> None:
        """Test testing surface discovery with test files."""
        from governance_runtime.infrastructure.repo_discovery.deep_repo_discovery import discover_testing_surface

        # Create test directory with test files
        (tmp_git_repo / "tests").mkdir()
        (tmp_git_repo / "tests" / "unit").mkdir()
        (tmp_git_repo / "tests" / "unit" / "test_core.py").write_text("def test_core(): pass\n", encoding="utf-8")

        testing = discover_testing_surface(tmp_git_repo)

        assert len(testing) >= 1
        unit_tests = [t for t in testing if t.scope == "unit"]
        assert len(unit_tests) >= 1

    def test_no_tests(self, tmp_git_repo: Path) -> None:
        """Test testing surface discovery with no tests."""
        from governance_runtime.infrastructure.repo_discovery.deep_repo_discovery import discover_testing_surface

        testing = discover_testing_surface(tmp_git_repo)

        assert isinstance(testing, list)


class TestDiscoverStructuralFacts:
    """Tests for discover_structural_facts (composition) function."""

    def test_happy_path(self, tmp_git_repo: Path) -> None:
        """Test full structural discovery."""
        from governance_runtime.infrastructure.repo_discovery.deep_repo_discovery import discover_structural_facts

        # Add some structure
        (tmp_git_repo / "pyproject.toml").write_text('[project]\nname = "test"\n', encoding="utf-8")
        (tmp_git_repo / "mymodule").mkdir()
        (tmp_git_repo / "mymodule" / "__init__.py").write_text("", encoding="utf-8")

        facts = discover_structural_facts(tmp_git_repo, profile="solo", repo_fingerprint="abc123")

        assert facts.repository_type in {"app", "single-package", "library"}
        assert isinstance(facts.layers, list)
        assert isinstance(facts.modules, list)
        assert isinstance(facts.entry_points, list)
        assert isinstance(facts.data_stores, list)
        assert facts.build_and_tooling is not None
        assert isinstance(facts.testing_surface, list)
        assert facts.discovered_at is not None
        assert facts.discovery_version == "2.0"

    def test_empty_repo(self, tmp_path: Path) -> None:
        """Test structural discovery on empty directory."""
        from governance_runtime.infrastructure.repo_discovery.deep_repo_discovery import discover_structural_facts

        facts = discover_structural_facts(tmp_path)

        assert facts.repository_type == "single-package"
        assert facts.discovery_version == "2.0"


class TestEvidenceAndConfidence:
    """Tests for evidence and confidence types."""

    def test_confidence_levels(self) -> None:
        """Test Confidence enum levels."""
        from governance_runtime.infrastructure.repo_discovery.deep_repo_discovery import Confidence

        assert Confidence.HIGH.value == "high"
        assert Confidence.MEDIUM.value == "medium"
        assert Confidence.LOW.value == "low"

    def test_evidence_creation(self) -> None:
        """Test Evidence dataclass creation."""
        from governance_runtime.infrastructure.repo_discovery.deep_repo_discovery import Confidence, Evidence

        evidence = Evidence("file_exists", "/path/to/file", Confidence.HIGH)

        assert evidence.source == "file_exists"
        assert evidence.reference == "/path/to/file"
        assert evidence.confidence == Confidence.HIGH

    def test_evidence_with_confidence(self) -> None:
        """Test Evidence.with_confidence method."""
        from governance_runtime.infrastructure.repo_discovery.deep_repo_discovery import Confidence, Evidence

        evidence = Evidence("pattern_match", "/path", Confidence.MEDIUM)
        new_evidence = evidence.with_confidence(Confidence.HIGH)

        assert new_evidence.source == "file_exists" or new_evidence.source == "pattern_match"
        assert new_evidence.confidence == Confidence.HIGH


class TestArtifactQuality:
    """Artifact-quality tests to ensure discovery produces valid output."""

    def test_structural_facts_serializable(self, tmp_git_repo: Path) -> None:
        """Test that StructuralFacts can be used by writers."""
        from governance_runtime.infrastructure.repo_discovery.deep_repo_discovery import discover_structural_facts
        from artifacts.writers.repo_cache import render_repo_cache
        from artifacts.writers.repo_map_digest import repo_map_digest_section

        facts = discover_structural_facts(tmp_git_repo, profile="solo", repo_fingerprint="test123")

        # Should be able to render without errors
        cache = render_repo_cache(
            date="2026-03-30",
            repo_name="test",
            profile="solo",
            profile_evidence="test",
            discovery=facts,
        )
        assert "RepoCache:" in cache
        assert "Version:" in cache

        section = repo_map_digest_section("2026-03-30", facts)
        assert "Repo Map Digest" in section

    def test_no_unknown_in_output(self, tmp_git_repo: Path) -> None:
        """Test that discovery output doesn't contain 'unknown' strings where avoidable."""
        from governance_runtime.infrastructure.repo_discovery.deep_repo_discovery import discover_structural_facts

        facts = discover_structural_facts(tmp_git_repo)

        # Repository type should be discovered, not "unknown"
        assert facts.repository_type != "unknown"

        # Discovery timestamp should be set
        assert facts.discovered_at is not None
        assert len(facts.discovered_at) > 0
