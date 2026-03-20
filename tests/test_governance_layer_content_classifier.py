"""
Content Classification Tests - Wave 3

Tests for:
- Content file identification
- Runtime file identification
- Content vs spec vs runtime boundaries

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

import pytest
from pathlib import Path

from governance.engine.content_classifier import (
    is_content_file,
    is_content_directory,
    is_runtime_file,
    get_content_paths,
    CONTENT_PATTERNS,
)
from governance.engine.spec_classifier import is_spec_file as is_spec


class TestContentClassificationHappyPath:
    """Happy path: correct content identification."""

    def test_rules_md_is_content(self) -> None:
        """rules.md is content."""
        assert is_content_file(Path("rules.md")) is True

    def test_governance_content_rules_md_is_content(self) -> None:
        """governance_content/reference/rules.md is content (new path)."""
        assert is_content_file(Path("governance_content/reference/rules.md")) is True

    def test_governance_content_master_md_is_content(self) -> None:
        """governance_content/reference/master.md is content (new path)."""
        assert is_content_file(Path("governance_content/reference/master.md")) is True

    def test_master_md_is_content(self) -> None:
        """master.md is content."""
        assert is_content_file(Path("master.md")) is True

    def test_readme_md_is_content(self) -> None:
        """README.md is content."""
        assert is_content_file(Path("README.md")) is True

    def test_adr_md_is_content(self) -> None:
        """ADR.md is content."""
        assert is_content_file(Path("ADR.md")) is True

    def test_changelog_md_is_content(self) -> None:
        """CHANGELOG.md is content."""
        assert is_content_file(Path("CHANGELOG.md")) is True

    def test_file_in_docs_is_content(self) -> None:
        """Files in docs/ are content."""
        assert is_content_file(Path("docs/some_file.md")) is True

    def test_file_in_profiles_is_content(self) -> None:
        """Files in profiles/ are content."""
        assert is_content_file(Path("profiles/some_profile.md")) is True


class TestContentClassificationNonContent:
    """Happy path: correctly identify non-content files."""

    def test_python_is_not_content(self) -> None:
        """Python files are runtime, not content."""
        assert is_content_file(Path("governance/engine/some.py")) is False

    def test_yaml_is_not_content(self) -> None:
        """YAML files are spec, not content."""
        assert is_content_file(Path("phase_api.yaml")) is False

    def test_json_is_not_content(self) -> None:
        """JSON files are spec, not content."""
        assert is_content_file(Path("some_config.json")) is False

    def test_shell_is_not_content(self) -> None:
        """Shell scripts are runtime, not content."""
        assert is_content_file(Path("scripts/deploy.sh")) is False


class TestRuntimeClassification:
    """Test runtime file identification."""

    def test_python_is_runtime(self) -> None:
        """Python files are runtime."""
        assert is_runtime_file(Path("governance/engine/module.py")) is True

    def test_shell_is_runtime(self) -> None:
        """Shell scripts are runtime."""
        assert is_runtime_file(Path("scripts/deploy.sh")) is True

    def test_cmd_is_runtime(self) -> None:
        """Batch files are runtime."""
        assert is_runtime_file(Path("bin/script.cmd")) is True

    def test_mjs_is_runtime(self) -> None:
        """JavaScript modules are runtime."""
        assert is_runtime_file(Path("some/module.mjs")) is True

    def test_github_workflow_is_runtime(self) -> None:
        """GitHub workflow files are runtime."""
        assert is_runtime_file(Path(".github/workflows/ci.yml")) is True

    def test_plugin_mjs_is_not_runtime(self) -> None:
        """OpenCode plugins are NOT runtime (they're plugins)."""
        assert is_runtime_file(Path("governance/artifacts/opencode-plugins/audit-new-session.mjs")) is False


class TestContentVsSpecBoundary:
    """Test boundaries between content and spec."""

    def test_rules_md_vs_rules_yml(self) -> None:
        """rules.md is content, rules.yml is spec."""
        assert is_content_file(Path("rules.md")) is True
        assert is_spec(Path("rules.yml")) is True
        assert is_content_file(Path("rules.yml")) is False

    def test_readme_md_vs_json_config(self) -> None:
        """README.md is content, config.json is spec."""
        assert is_content_file(Path("README.md")) is True
        assert is_spec(Path("config.json")) is False  # Not in spec locations

    def test_docs_md_vs_contracts_json(self) -> None:
        """docs/ is content, contracts/ JSON is spec."""
        assert is_content_file(Path("docs/guide.md")) is True
        assert is_spec(Path("governance/contracts/some.json")) is True


class TestContentVsRuntimeBoundary:
    """Test boundaries between content and runtime."""

    def test_docs_py_is_runtime(self) -> None:
        """Python files in docs/ are runtime, not content."""
        # Even if in docs/, .py is runtime
        path = Path("docs/some_script.py")
        assert is_content_file(path) is False
        assert is_runtime_file(path) is True

    def test_profiles_yaml_in_addons_is_spec(self) -> None:
        """profiles/addons/*.yml is spec, not content."""
        # This is spec, not content
        path = Path("profiles/addons/some.addon.yml")
        assert is_content_file(path) is False
        assert is_spec(path) is True


class TestContentDirectoryClassification:
    """Test content directory identification."""

    def test_docs_is_content_directory(self) -> None:
        """docs is a content directory."""
        assert is_content_directory(Path("docs")) is True

    def test_profiles_is_content_directory(self) -> None:
        """profiles is a content directory."""
        assert is_content_directory(Path("profiles")) is True

    def test_templates_is_content_directory(self) -> None:
        """templates is a content directory."""
        assert is_content_directory(Path("templates")) is True

    def test_governance_is_not_content_directory(self) -> None:
        """governance is NOT a content directory (it's runtime + spec)."""
        assert is_content_directory(Path("governance")) is False


class TestContentClassificationPatterns:
    """Verify content patterns are defined."""

    def test_content_patterns_not_empty(self) -> None:
        """Content patterns must be defined."""
        assert len(CONTENT_PATTERNS) > 0

    def test_critical_content_files_in_patterns(self) -> None:
        """Critical content files must be in patterns."""
        assert "rules.md" in CONTENT_PATTERNS
        assert "master.md" in CONTENT_PATTERNS
        assert "README.md" in CONTENT_PATTERNS

    def test_content_patterns_is_frozen(self) -> None:
        """Content patterns must be immutable."""
        assert isinstance(CONTENT_PATTERNS, frozenset)


class TestContentClassificationEdgeCases:
    """Edge cases: unusual but valid inputs."""

    def test_arbitrary_file_not_content(self) -> None:
        """Arbitrary file in root is NOT content unless in patterns."""
        path = Path("some_random_file.txt")
        assert is_content_file(path) is False

    def test_nested_in_content_dir_is_content(self) -> None:
        """Deeply nested file in content directory is content."""
        path = Path("docs/api/reference/overview.md")
        assert is_content_file(path) is True

    def test_empty_path_handled(self) -> None:
        """Empty path doesn't crash."""
        path = Path("")
        result = is_content_file(path)
        assert isinstance(result, bool)
