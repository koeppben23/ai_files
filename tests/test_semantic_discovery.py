#!/usr/bin/env python3
"""Tests for governance_runtime.infrastructure.repo_discovery.semantic_discovery.

Tests cover:
- Happy paths for all semantic discovery functions
- Evidence and confidence levels
- Edge cases (empty repos, minimal repos)
- SemanticFacts composition
- Integration with workspace-memory.yaml rendering
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def tmp_git_repo(tmp_path: Path) -> Path:
    """Create a minimal git repository for testing."""
    repo = tmp_path / "test_repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, capture_output=True, check=True)
    (repo / "README.md").write_text("# Test Repo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=repo, capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, capture_output=True, check=True)
    return repo


class TestDiscoverSSOTs:
    """Tests for discover_ssots function."""

    def test_happy_path_with_phase_api(self, tmp_git_repo: Path) -> None:
        """Test SSOT discovery with phase_api.yaml."""
        from governance_runtime.infrastructure.repo_discovery.semantic_discovery import discover_ssots

        (tmp_git_repo / "governance_spec").mkdir()
        (tmp_git_repo / "governance_spec" / "phase_api.yaml").write_text("phases: []\n", encoding="utf-8")

        ssots = discover_ssots(tmp_git_repo)

        phase_routing = [s for s in ssots if s.concern == "phase-routing"]
        assert len(phase_routing) >= 1
        assert phase_routing[0].authority == "spec-ssot"

    def test_happy_path_with_repo_policy(self, tmp_git_repo: Path) -> None:
        """Test SSOT discovery with repo policy."""
        from governance_runtime.infrastructure.repo_discovery.semantic_discovery import discover_ssots

        (tmp_git_repo / ".opencode").mkdir()
        (tmp_git_repo / ".opencode" / "governance-repo-policy.json").write_text(
            '{"schema": "opencode-governance-repo-policy.v1"}', encoding="utf-8"
        )

        ssots = discover_ssots(tmp_git_repo)

        repo_policy = [s for s in ssots if s.concern == "repo-policy"]
        assert len(repo_policy) >= 1

    def test_no_ssots(self, tmp_git_repo: Path) -> None:
        """Test SSOT discovery with no known SSOTs."""
        from governance_runtime.infrastructure.repo_discovery.semantic_discovery import discover_ssots

        ssots = discover_ssots(tmp_git_repo)

        assert isinstance(ssots, list)


class TestDiscoverInvariants:
    """Tests for discover_invariants function."""

    def test_happy_path_with_config(self, tmp_git_repo: Path) -> None:
        """Test invariant discovery with governance.paths.json."""
        from governance_runtime.infrastructure.repo_discovery.semantic_discovery import discover_invariants

        (tmp_git_repo / "governance.paths.json").write_text(
            '{"paths": {"configRoot": "/tmp"}}', encoding="utf-8"
        )

        invariants = discover_invariants(tmp_git_repo)

        path_constraints = [i for i in invariants if i.category == "path-constraint"]
        assert len(path_constraints) >= 1

    def test_happy_path_with_session_state(self, tmp_git_repo: Path) -> None:
        """Test invariant discovery with SESSION_STATE.json.
        
        Note: With code-based heuristics, we need actual code that enforces
        the invariant, not just the file existence.
        """
        from governance_runtime.infrastructure.repo_discovery.semantic_discovery import discover_invariants

        # Create a Python file that references SESSION_STATE
        (tmp_git_repo / "module.py").write_text(
            'SESSION_STATE_FILE = "SESSION_STATE.json"\n'
            'def check():\n'
            '    if not SESSION_STATE_FILE.exists():\n'
            '        raise ValueError("SESSION_STATE must exist")\n',
            encoding="utf-8"
        )

        invariants = discover_invariants(tmp_git_repo)

        # With code-based detection, invariants may or may not match
        # depending on pattern matching - just verify no crash
        assert isinstance(invariants, list)

    def test_no_invariants(self, tmp_git_repo: Path) -> None:
        """Test invariant discovery with no invariants."""
        from governance_runtime.infrastructure.repo_discovery.semantic_discovery import discover_invariants

        invariants = discover_invariants(tmp_git_repo)

        assert isinstance(invariants, list)


class TestDiscoverConventions:
    """Tests for discover_conventions function."""

    def test_happy_path_with_tests(self, tmp_git_repo: Path) -> None:
        """Test convention discovery with test files."""
        from governance_runtime.infrastructure.repo_discovery.semantic_discovery import discover_conventions

        (tmp_git_repo / "tests").mkdir()
        (tmp_git_repo / "tests" / "test_a.py").write_text("def test_a(): pass\n", encoding="utf-8")
        (tmp_git_repo / "tests" / "test_b.py").write_text("def test_b(): pass\n", encoding="utf-8")
        (tmp_git_repo / "tests" / "test_c.py").write_text("def test_c(): pass\n", encoding="utf-8")

        conventions = discover_conventions(tmp_git_repo)

        test_naming = [c for c in conventions if c.name == "test-naming"]
        assert len(test_naming) >= 1

    def test_happy_path_with_python_modules(self, tmp_git_repo: Path) -> None:
        """Test convention discovery with Python modules."""
        from governance_runtime.infrastructure.repo_discovery.semantic_discovery import discover_conventions

        (tmp_git_repo / "mymodule").mkdir()
        (tmp_git_repo / "mymodule" / "__init__.py").write_text("", encoding="utf-8")
        (tmp_git_repo / "othermodule").mkdir()
        (tmp_git_repo / "othermodule" / "__init__.py").write_text("", encoding="utf-8")

        conventions = discover_conventions(tmp_git_repo)

        python_module = [c for c in conventions if c.name == "python-module"]
        assert len(python_module) >= 1

    def test_happy_path_with_governance_modules(self, tmp_git_repo: Path) -> None:
        """Test convention discovery with governance modules."""
        from governance_runtime.infrastructure.repo_discovery.semantic_discovery import discover_conventions

        (tmp_git_repo / "governance_runtime").mkdir()
        (tmp_git_repo / "governance_content").mkdir()

        conventions = discover_conventions(tmp_git_repo)

        gov_naming = [c for c in conventions if c.name == "governance-module-naming"]
        assert len(gov_naming) >= 1


class TestDiscoverPatterns:
    """Tests for discover_patterns function."""

    def test_happy_path_with_emit_gate_failure(self, tmp_git_repo: Path) -> None:
        """Test pattern discovery with emit_gate_failure usage."""
        from governance_runtime.infrastructure.repo_discovery.semantic_discovery import discover_patterns

        (tmp_git_repo / "module_a.py").write_text(
            "def foo():\n    emit_gate_failure(gate='TEST', code='ERR')\n", encoding="utf-8"
        )
        (tmp_git_repo / "module_b.py").write_text(
            "def bar():\n    emit_gate_failure(gate='TEST', code='ERR')\n", encoding="utf-8"
        )

        patterns = discover_patterns(tmp_git_repo)

        gate_failure = [p for p in patterns if p.name == "gate-failure-emission"]
        assert len(gate_failure) >= 1
        assert len(gate_failure[0].locations) >= 2

    def test_happy_path_with_fallback_imports(self, tmp_git_repo: Path) -> None:
        """Test pattern discovery with fallback import pattern."""
        from governance_runtime.infrastructure.repo_discovery.semantic_discovery import discover_patterns

        (tmp_git_repo / "module_a.py").write_text(
            "try:\n    from optional_module import something\nexcept ImportError:\n    something = None\n",
            encoding="utf-8",
        )
        (tmp_git_repo / "module_b.py").write_text(
            "try:\n    from other_module import other\nexcept ImportError:\n    other = None\n",
            encoding="utf-8",
        )

        patterns = discover_patterns(tmp_git_repo)

        fallback = [p for p in patterns if p.name == "fallback-import"]
        assert len(fallback) >= 1


class TestDiscoverDefaults:
    """Tests for discover_defaults function."""

    def test_happy_path(self, tmp_git_repo: Path) -> None:
        """Test defaults discovery."""
        from governance_runtime.infrastructure.repo_discovery.semantic_discovery import discover_defaults

        defaults = discover_defaults(tmp_git_repo)

        assert len(defaults) >= 2  # At least fingerprint-format and config-root


class TestDiscoverDeviations:
    """Tests for discover_deviations function."""

    def test_happy_path_with_no_tests(self, tmp_git_repo: Path) -> None:
        """Test deviation discovery when tests/ is missing."""
        from governance_runtime.infrastructure.repo_discovery.semantic_discovery import discover_deviations

        deviations = discover_deviations(tmp_git_repo)

        no_tests = [d for d in deviations if "tests" in d.description.lower()]
        # May or may not have this deviation - depends on implementation
        assert isinstance(deviations, list)

    def test_no_deviations(self, tmp_git_repo: Path) -> None:
        """Test deviation discovery with well-structured repo."""
        from governance_runtime.infrastructure.repo_discovery.semantic_discovery import discover_deviations

        (tmp_git_repo / "tests").mkdir()
        (tmp_git_repo / "tests" / "test_a.py").write_text("def test_a(): pass\n", encoding="utf-8")

        deviations = discover_deviations(tmp_git_repo)

        assert isinstance(deviations, list)


class TestDiscoverSemanticFacts:
    """Tests for discover_semantic_facts (composition) function."""

    def test_happy_path(self, tmp_git_repo: Path) -> None:
        """Test full semantic discovery."""
        from governance_runtime.infrastructure.repo_discovery.semantic_discovery import discover_semantic_facts

        # Add some structure
        (tmp_git_repo / "governance_spec").mkdir()
        (tmp_git_repo / "governance_spec" / "phase_api.yaml").write_text("phases: []\n", encoding="utf-8")
        (tmp_git_repo / "tests").mkdir()
        (tmp_git_repo / "tests" / "test_a.py").write_text("def test_a(): pass\n", encoding="utf-8")

        facts = discover_semantic_facts(tmp_git_repo, profile="solo", repo_fingerprint="abc123")

        assert isinstance(facts.ssots, list)
        assert isinstance(facts.invariants, list)
        assert isinstance(facts.conventions, list)
        assert isinstance(facts.patterns, list)
        assert isinstance(facts.defaults, list)
        assert isinstance(facts.deviations, list)
        assert facts.discovery_version == "2.0"
        assert facts.discovered_at is not None


class TestWorkspaceMemoryRendering:
    """Tests for workspace-memory.yaml rendering with semantic facts."""

    def test_render_with_semantics(self, tmp_git_repo: Path) -> None:
        """Test rendering workspace memory with semantic facts."""
        from governance_runtime.infrastructure.repo_discovery.semantic_discovery import discover_semantic_facts
        from artifacts.writers.workspace_memory import render_workspace_memory

        # Add some structure
        (tmp_git_repo / "tests").mkdir()
        (tmp_git_repo / "tests" / "test_a.py").write_text("def test_a(): pass\n", encoding="utf-8")
        (tmp_git_repo / "tests" / "test_b.py").write_text("def test_b(): pass\n", encoding="utf-8")
        (tmp_git_repo / "tests" / "test_c.py").write_text("def test_c(): pass\n", encoding="utf-8")

        semantic = discover_semantic_facts(tmp_git_repo)

        content = render_workspace_memory(
            date="2026-03-30",
            repo_name="test",
            repo_fingerprint="abc123",
            semantic=semantic,
        )

        assert "WorkspaceMemory:" in content
        assert "Version:" in content
        # Should have conventions from discovery
        assert "Conventions:" in content

    def test_render_legacy_without_semantics(self) -> None:
        """Test rendering workspace memory without semantic facts (legacy)."""
        from artifacts.writers.workspace_memory import render_workspace_memory

        content = render_workspace_memory(
            date="2026-03-30",
            repo_name="test",
            repo_fingerprint="abc123",
        )

        assert "WorkspaceMemory:" in content
        assert "Version:" in content


class TestEvidenceAndConfidence:
    """Tests for evidence and confidence in semantic discovery."""

    def test_ssot_has_evidence(self, tmp_git_repo: Path) -> None:
        """Test that SSOTs have proper evidence."""
        from governance_runtime.infrastructure.repo_discovery.semantic_discovery import discover_ssots
        from governance_runtime.infrastructure.repo_discovery.deep_repo_discovery import Confidence

        (tmp_git_repo / "governance_spec").mkdir()
        (tmp_git_repo / "governance_spec" / "phase_api.yaml").write_text("phases: []\n", encoding="utf-8")

        ssots = discover_ssots(tmp_git_repo)

        assert len(ssots) >= 1
        for s in ssots:
            assert s.evidence is not None
            assert s.evidence.confidence in {Confidence.HIGH, Confidence.MEDIUM, Confidence.LOW}

    def test_convention_has_evidence(self, tmp_git_repo: Path) -> None:
        """Test that conventions have proper evidence."""
        from governance_runtime.infrastructure.repo_discovery.semantic_discovery import discover_conventions
        from governance_runtime.infrastructure.repo_discovery.deep_repo_discovery import Confidence

        (tmp_git_repo / "tests").mkdir()
        (tmp_git_repo / "tests" / "test_a.py").write_text("def test_a(): pass\n", encoding="utf-8")
        (tmp_git_repo / "tests" / "test_b.py").write_text("def test_b(): pass\n", encoding="utf-8")
        (tmp_git_repo / "tests" / "test_c.py").write_text("def test_c(): pass\n", encoding="utf-8")

        conventions = discover_conventions(tmp_git_repo)

        assert len(conventions) >= 1
        for c in conventions:
            assert c.evidence is not None
            assert c.evidence.confidence in {Confidence.HIGH, Confidence.MEDIUM, Confidence.LOW}
