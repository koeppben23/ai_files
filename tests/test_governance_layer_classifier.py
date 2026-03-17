"""
Tests for Layer Classifier - Wave 6

Validates the unified layer classification that integrates:
- spec_classifier (Wave 2)
- content_classifier (Wave 3)
- command_surface (Wave 4)
- state_classifier (Wave 5)

IMPORTANT: master.md and rules.md are CONTENT, NOT commands.
They belong in governance_content, NOT opencode_integration.

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from governance.engine.layer_classifier import (
    GovernanceLayer,
    classify_layer,
    get_layer_name,
    is_static_content_payload,
    is_installable_layer,
)


class TestOpenCodeIntegrationLayer:
    """Test classification of OpenCode integration layer."""

    def test_canonical_command_is_opencode_integration(self) -> None:
        """Canonical commands belong to opencode_integration layer."""
        assert classify_layer("commands/continue.md") == GovernanceLayer.OPENCODE_INTEGRATION
        assert classify_layer("commands/plan.md") == GovernanceLayer.OPENCODE_INTEGRATION
        assert classify_layer("commands/review.md") == GovernanceLayer.OPENCODE_INTEGRATION

    def test_non_command_file_is_content(self) -> None:
        """master.md and rules.md are CONTENT, not OpenCode integration."""
        assert classify_layer("master.md") == GovernanceLayer.GOVERNANCE_CONTENT
        assert classify_layer("rules.md") == GovernanceLayer.GOVERNANCE_CONTENT
        assert classify_layer("commands/master.md") == GovernanceLayer.GOVERNANCE_CONTENT
        assert classify_layer("commands/rules.md") == GovernanceLayer.GOVERNANCE_CONTENT


class TestGovernanceSpecLayer:
    """Test classification of governance_spec layer."""

    def test_root_spec_file_is_spec(self) -> None:
        """Root-level spec files belong to governance_spec."""
        assert classify_layer("phase_api.yaml") == GovernanceLayer.GOVERNANCE_SPEC
        assert classify_layer("rules.yml") == GovernanceLayer.GOVERNANCE_SPEC

    def test_spec_directory_is_spec(self) -> None:
        """Spec directories belong to governance_spec."""
        assert classify_layer("schemas") == GovernanceLayer.GOVERNANCE_SPEC
        assert classify_layer("governance/contracts") == GovernanceLayer.GOVERNANCE_SPEC


class TestGovernanceContentLayer:
    """Test classification of governance_content layer."""

    def test_root_content_file_is_content(self) -> None:
        """Root-level content files belong to governance_content."""
        assert classify_layer("master.md") == GovernanceLayer.GOVERNANCE_CONTENT
        assert classify_layer("rules.md") == GovernanceLayer.GOVERNANCE_CONTENT
        assert classify_layer("README.md") == GovernanceLayer.GOVERNANCE_CONTENT
        assert classify_layer("ADR.md") == GovernanceLayer.GOVERNANCE_CONTENT

    def test_content_directory_is_content(self) -> None:
        """Content directories belong to governance_content."""
        assert classify_layer("profiles") == GovernanceLayer.GOVERNANCE_CONTENT
        assert classify_layer("templates") == GovernanceLayer.GOVERNANCE_CONTENT


class TestGovernanceRuntimeLayer:
    """Test classification of governance_runtime layer."""

    def test_python_engine_file_is_runtime(self) -> None:
        """Python files in governance/engine/ are runtime."""
        assert classify_layer("governance/engine/orchestrator.py") == GovernanceLayer.GOVERNANCE_RUNTIME
        assert classify_layer("governance/engine/gate_evaluator.py") == GovernanceLayer.GOVERNANCE_RUNTIME


class TestRepoRunStateLayer:
    """Test classification of repo_run_state layer."""

    def test_state_file_is_state(self) -> None:
        """State files belong to repo_run_state."""
        assert classify_layer("SESSION_STATE.json") == GovernanceLayer.REPO_RUN_STATE
        assert classify_layer("events.jsonl") == GovernanceLayer.REPO_RUN_STATE
        assert classify_layer("flow.log.jsonl") == GovernanceLayer.REPO_RUN_STATE

    def test_state_directory_is_state(self) -> None:
        """State directories belong to repo_run_state."""
        assert classify_layer("workspaces") == GovernanceLayer.REPO_RUN_STATE
        assert classify_layer(".lock") == GovernanceLayer.REPO_RUN_STATE

    def test_log_in_workspace_logs_is_state(self) -> None:
        """Log files in workspace logs/ are repo_run_state."""
        assert classify_layer("workspaces/abc123/logs/flow.log.jsonl") == GovernanceLayer.REPO_RUN_STATE


class TestUnknownLayer:
    """Test classification of unknown layer."""

    def test_unclassified_file_is_unknown(self) -> None:
        """Files that don't match any layer are unknown."""
        assert classify_layer("some/random/path.txt") == GovernanceLayer.UNKNOWN


class TestGetLayerName:
    """Test human-readable layer name generation."""

    def test_returns_correct_names(self) -> None:
        """Each layer returns its correct name."""
        assert get_layer_name(GovernanceLayer.OPENCODE_INTEGRATION) == "opencode_integration"
        assert get_layer_name(GovernanceLayer.GOVERNANCE_RUNTIME) == "governance_runtime"
        assert get_layer_name(GovernanceLayer.GOVERNANCE_CONTENT) == "governance_content"
        assert get_layer_name(GovernanceLayer.GOVERNANCE_SPEC) == "governance_spec"
        assert get_layer_name(GovernanceLayer.REPO_RUN_STATE) == "repo_run_state"
        assert get_layer_name(GovernanceLayer.UNKNOWN) == "unknown"


class TestStaticContentPayload:
    """Test static content payload classification."""

    def test_content_is_static_payload(self) -> None:
        """governance_content is part of static content payload."""
        assert is_static_content_payload(GovernanceLayer.GOVERNANCE_CONTENT) is True

    def test_spec_is_static_payload(self) -> None:
        """governance_spec is part of static content payload."""
        assert is_static_content_payload(GovernanceLayer.GOVERNANCE_SPEC) is True

    def test_runtime_is_not_static_payload(self) -> None:
        """governance_runtime is NOT static content payload."""
        assert is_static_content_payload(GovernanceLayer.GOVERNANCE_RUNTIME) is False

    def test_opencode_integration_is_not_static_payload(self) -> None:
        """opencode_integration is NOT static content payload."""
        assert is_static_content_payload(GovernanceLayer.OPENCODE_INTEGRATION) is False

    def test_repo_run_state_is_not_static_payload(self) -> None:
        """repo_run_state is NOT static content payload."""
        assert is_static_content_payload(GovernanceLayer.REPO_RUN_STATE) is False


class TestInstallableLayer:
    """Test installability classification."""

    def test_content_is_installable(self) -> None:
        """governance_content is installable."""
        assert is_installable_layer(GovernanceLayer.GOVERNANCE_CONTENT) is True

    def test_spec_is_installable(self) -> None:
        """governance_spec is installable."""
        assert is_installable_layer(GovernanceLayer.GOVERNANCE_SPEC) is True

    def test_runtime_is_installable(self) -> None:
        """governance_runtime is installable."""
        assert is_installable_layer(GovernanceLayer.GOVERNANCE_RUNTIME) is True

    def test_opencode_integration_is_installable(self) -> None:
        """opencode_integration is installable."""
        assert is_installable_layer(GovernanceLayer.OPENCODE_INTEGRATION) is True

    def test_repo_run_state_is_not_installable(self) -> None:
        """repo_run_state is NOT installable (runtime state)."""
        assert is_installable_layer(GovernanceLayer.REPO_RUN_STATE) is False

    def test_unknown_is_not_installable(self) -> None:
        """unknown is NOT installable."""
        assert is_installable_layer(GovernanceLayer.UNKNOWN) is False


class TestPriorityOrder:
    """Test that classification priority is correct."""

    def test_state_takes_precedence_over_content(self) -> None:
        """State files are classified as state even if they match content patterns."""
        assert classify_layer("SESSION_STATE.json") == GovernanceLayer.REPO_RUN_STATE
