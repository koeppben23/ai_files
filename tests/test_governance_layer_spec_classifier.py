"""
Spec Classification Tests - Wave 2

Tests for:
- Spec file identification
- Spec directory identification
- Known spec paths verification

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

import pytest
from pathlib import Path

from governance_runtime.engine.spec_classifier import (
    is_spec_file,
    is_spec_directory,
    get_spec_paths,
    GOVERNANCE_SPEC_PATTERNS,
)


class TestSpecClassificationHappyPath:
    """Happy path: correct spec identification."""

    def test_phase_api_yaml_is_spec(self) -> None:
        """phase_api.yaml is a known spec file."""
        path = Path("phase_api.yaml")
        assert is_spec_file(path) is True

    def test_rules_yml_is_spec(self) -> None:
        """rules.yml is a known spec file."""
        path = Path("rules.yml")
        assert is_spec_file(path) is True

    def test_template_catalog_is_spec(self) -> None:
        """template_catalog.json is a known spec file."""
        path = Path("templates/github-actions/template_catalog.json")
        assert is_spec_file(path) is True

    def test_yaml_in_schemas_dir_is_spec(self) -> None:
        """YAML files in schemas directory are spec."""
        path = Path("governance_runtime/assets/schemas/some_schema.yaml")
        assert is_spec_file(path) is True

    def test_json_in_contracts_dir_is_spec(self) -> None:
        """JSON files in contracts directory are spec."""
        path = Path("governance_spec/contracts/some_contract.json")
        assert is_spec_file(path) is True

    def test_yaml_in_receipts_dir_is_spec(self) -> None:
        """YAML files in receipts directory are spec."""
        path = Path("governance_spec/receipts/some_receipt.yaml")
        assert is_spec_file(path) is True

    def test_addon_manifest_is_spec(self) -> None:
        """Addon manifests are spec."""
        path = Path("profiles/addons/some.addon.yml")
        assert is_spec_file(path) is True

    def test_ruleset_yml_is_spec(self) -> None:
        """Ruleset YAML files are spec."""
        path = Path("rulesets/core/rules.yml")
        assert is_spec_file(path) is True


class TestSpecClassificationNonSpec:
    """Happy path: correctly identify non-spec files."""

    def test_markdown_is_not_spec(self) -> None:
        """Markdown files are not spec."""
        path = Path("docs/some_doc.md")
        assert is_spec_file(path) is False

    def test_python_is_not_spec(self) -> None:
        """Python files are not spec."""
        path = Path("governance_runtime/engine/some_module.py")
        assert is_spec_file(path) is False

    def test_readme_is_not_spec(self) -> None:
        """README files are not spec."""
        path = Path("README.md")
        assert is_spec_file(path) is False


class TestSpecDirectoryClassification:
    """Verify spec directory identification."""

    def test_schemas_dir_is_spec_directory(self) -> None:
        """schemas is a spec directory."""
        assert is_spec_directory(Path("schemas")) is True
        assert is_spec_directory(Path("governance_runtime/assets/schemas")) is True

    def test_contracts_dir_is_spec_directory(self) -> None:
        """contracts is a spec directory."""
        assert is_spec_directory(Path("governance_runtime/contracts")) is True

    def test_receipts_dir_is_spec_directory(self) -> None:
        """receipts is a spec directory."""
        assert is_spec_directory(Path("governance_runtime/receipts")) is True

    def test_docs_is_not_spec_directory(self) -> None:
        """docs is NOT a spec directory."""
        assert is_spec_directory(Path("docs")) is False

    def test_profiles_is_not_spec_directory(self) -> None:
        """profiles is NOT a spec directory (only addons inside is)."""
        assert is_spec_directory(Path("profiles")) is False
        assert is_spec_directory(Path("profiles/addons")) is True


class TestSpecDirectoryClassificationPrecision:
    """Precision tests for spec directory classification."""

    def test_config_dir_is_spec_directory(self) -> None:
        """config is a spec directory."""
        assert is_spec_directory(Path("governance_runtime/assets/config")) is True

    def test_configs_dir_is_spec_directory(self) -> None:
        """configs is a spec directory."""
        assert is_spec_directory(Path("governance_runtime/assets/configs")) is True

    def test_rulesets_is_spec_directory(self) -> None:
        """rulesets is a spec directory."""
        assert is_spec_directory(Path("rulesets")) is True

    def test_rulesets_core_is_spec_directory(self) -> None:
        """rulesets/core is a spec directory."""
        assert is_spec_directory(Path("rulesets/core")) is True

    def test_rulesets_arbitrary_subdir_is_not_spec(self) -> None:
        """Arbitrary subdir under rulesets is NOT spec (exact match only)."""
        # Note: with exact-match only, rulesets/custom is NOT spec
        # unless explicitly in SPEC_PATTERNS
        assert is_spec_directory(Path("rulesets/custom")) is False


class TestSpecPatternConflictCases:
    """Conflict tests: content vs spec boundaries."""

    def test_docs_not_spec_even_with_yaml(self) -> None:
        """docs/ with YAML files is NOT spec."""
        path = Path("docs/configuration.yaml")
        assert is_spec_file(path) is False

    def test_profiles_readme_not_spec(self) -> None:
        """README in profiles/ is NOT spec."""
        path = Path("profiles/README.md")
        assert is_spec_file(path) is False

    def test_templates_workflow_yaml_is_content_not_spec(self) -> None:
        """YAML in templates/ (not template_catalog.json) is content."""
        path = Path("templates/github-actions/my-workflow.yml")
        # templates/ is content, only template_catalog.json is spec
        assert is_spec_file(path) is False

    def test_rulesets_profile_yaml_is_spec(self) -> None:
        """YAML in rulesets/profiles/ IS spec."""
        path = Path("rulesets/profiles/python.yml")
        assert is_spec_file(path) is True

    def test_governance_spec_rulesets_profile_yaml_is_spec(self) -> None:
        """YAML in governance_spec/rulesets/profiles/ IS spec (new path)."""
        path = Path("governance_spec/rulesets/profiles/python.yml")
        assert is_spec_file(path) is True

    def test_rulesets_arbitrary_yaml_in_subdir_is_spec(self) -> None:
        """Any YAML in rulesets/ subdirectories IS spec."""
        path = Path("rulesets/core/custom.yaml")
        assert is_spec_file(path) is True


class TestSpecClassificationBadPath:
    """Bad path: error handling."""

    def test_none_path_doesnt_crash(self) -> None:
        """None path is handled gracefully."""
        # Should not raise
        try:
            is_spec_file(Path("nonexistent"))
        except Exception:
            pytest.fail("Should not raise for nonexistent path")
