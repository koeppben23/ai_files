"""Tests for run_review_loop orchestrator integration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from governance_runtime.application.services.phase6_review_orchestrator import (
    run_review_loop,
    ReviewLoopConfig,
    ReviewDependencies,
    PolicyResolver,
    LLMCaller,
    ResponseValidator,
    ReviewResult,
    BLOCKED_EFFECTIVE_POLICY_UNAVAILABLE,
)
from governance_runtime.application.services.phase6_review_orchestrator.review_result import (
    CompletionStatus,
)


# Mock functions for dependency injection
def _mock_json_loader(path: Path) -> dict[str, Any]:
    """Mock JSON loader that returns empty dict."""
    return {}


def _mock_context_writer(path: Path, data: dict[str, Any]) -> None:
    """Mock context writer that does nothing."""
    pass


def _mock_clock() -> str:
    """Mock clock that returns a fixed timestamp."""
    return "2026-03-22T19:30:00Z"


class TestReviewLoopConfig:
    """Tests for ReviewLoopConfig."""

    def test_from_state_extracts_values(self):
        """from_state extracts config values from state."""
        state = {
            "ImplementationReview": {
                "max_iterations": 5,
                "min_self_review_iterations": 2,
            },
            "phase6_force_stable_digest": True,
        }
        config = ReviewLoopConfig.from_state(
            state=state,
            session_path=Path("/tmp/session.json"),
            commands_home=Path("/tmp/commands"),
        )
        assert config.max_iterations == 3  # Clamped to 3
        assert config.min_iterations == 2
        assert config.force_stable_digest is True
        assert config.commands_home == Path("/tmp/commands")

    def test_from_state_defaults(self):
        """from_state uses defaults when values not in state."""
        state = {}
        config = ReviewLoopConfig.from_state(
            state=state,
            session_path=Path("/tmp/session.json"),
            commands_home=Path("/tmp/commands"),
        )
        assert config.max_iterations == 3
        assert config.min_iterations == 1
        assert config.force_stable_digest is False


class TestRunReviewLoop:
    """Tests for run_review_loop orchestrator."""

    @pytest.fixture
    def mock_dependencies(self):
        """Create mock dependencies for testing."""
        policy_resolver = MagicMock(spec=PolicyResolver)
        policy_resolver.load_mandate_schema.return_value = None
        policy_resolver.load_effective_review_policy.return_value = MagicMock(
            policy_text="test policy",
            is_available=True,
            error_code=None,
        )

        llm_caller = MagicMock(spec=LLMCaller)
        llm_caller.is_configured = True
        llm_caller.build_context.return_value = {"test": "context"}
        llm_caller.invoke.return_value = MagicMock(
            invoked=True,
            stdout=json.dumps({
                "verdict": "approve",
                "governing_evidence": "All good",
                "contract_check": "No issues",
                "findings": [],
                "regression_assessment": "Low risk",
                "test_assessment": "Sufficient",
            }),
            stderr="",
            return_code=0,
            error=None,
            pipeline_mode=True,
            binding_role="review",
            binding_source="env:AI_GOVERNANCE_REVIEW_BINDING",
        )

        response_validator = MagicMock(spec=ResponseValidator)
        response_validator.validate.return_value = MagicMock(
            valid=True,
            verdict="approve",
            findings=[],
            violations=[],
            parsed_data={},
            raw_response="",
        )

        return ReviewDependencies(
            policy_resolver=policy_resolver,
            llm_caller=llm_caller,
            response_validator=response_validator,
        )

    def test_returns_none_for_non_phase6(self, mock_dependencies):
        """run_review_loop returns None result for non-Phase-6 states."""
        state_doc = {
            "SESSION_STATE": {
                "phase": "5-ArchitectureReview",
                "next": "5",
            }
        }
        config = ReviewLoopConfig(
            commands_home=Path("/tmp"),
            session_path=Path("/tmp/session.json"),
        )

        result = run_review_loop(
            state_doc=state_doc,
            config=config,
            dependencies=mock_dependencies,
        )

        assert result.loop_result is None

    def test_blocked_when_policy_unavailable(self, mock_dependencies):
        """run_review_loop returns blocked result when policy unavailable."""
        mock_dependencies.policy_resolver.load_effective_review_policy.return_value = MagicMock(
            policy_text="",
            is_available=False,
            error_code=BLOCKED_EFFECTIVE_POLICY_UNAVAILABLE,
        )

        state_doc = {
            "SESSION_STATE": {
                "phase": "6-PostFlight",
                "next": "6",
                "LoadedRulebooks": {"core": "rules.md"},
            }
        }
        config = ReviewLoopConfig(
            commands_home=Path("/tmp"),
            session_path=Path("/tmp/session.json"),
        )

        result = run_review_loop(
            state_doc=state_doc,
            config=config,
            dependencies=mock_dependencies,
        )

        assert result.is_blocked is True
        assert result.loop_result is not None
        assert result.loop_result.block_reason_code == BLOCKED_EFFECTIVE_POLICY_UNAVAILABLE

    def test_complete_path_with_approve(self, mock_dependencies):
        """run_review_loop completes when LLM approves at max iterations."""
        state_doc = {
            "SESSION_STATE": {
                "phase": "6-PostFlight",
                "next": "6",
                "phase5_plan_record_digest": "sha256:plan-v1",
                "phase6_force_stable_digest": True,  # Force stable for deterministic test
            }
        }
        config = ReviewLoopConfig(
            commands_home=Path("/tmp"),
            session_path=Path("/tmp/session.json"),
            max_iterations=2,
            min_iterations=1,
            force_stable_digest=True,
        )

        result = run_review_loop(
            state_doc=state_doc,
            config=config,
            dependencies=mock_dependencies,
            json_loader=_mock_json_loader,
            context_writer=_mock_context_writer,
            clock=_mock_clock,
        )

        assert result.success is True
        assert result.is_complete is True
        assert result.loop_result is not None
        assert result.loop_result.final_iteration == 2
        assert result.loop_result.completion_status == CompletionStatus.PHASE6_COMPLETED

    def test_uses_configured_workspace_root_for_llm_binding_resolution(self, mock_dependencies):
        """run_review_loop passes config.workspace_root into LLM caller."""
        state_doc = {
            "SESSION_STATE": {
                "phase": "6-PostFlight",
                "next": "6",
                "phase5_plan_record_digest": "sha256:plan-v1",
                "phase6_force_stable_digest": True,
            }
        }
        workspace_root = Path("/tmp/workspace-canonical")
        config = ReviewLoopConfig(
            commands_home=Path("/tmp"),
            session_path=Path("/tmp/session.json"),
            workspace_root=workspace_root,
            max_iterations=1,
            min_iterations=1,
            force_stable_digest=True,
        )

        run_review_loop(
            state_doc=state_doc,
            config=config,
            dependencies=mock_dependencies,
            json_loader=_mock_json_loader,
            context_writer=_mock_context_writer,
            clock=_mock_clock,
        )

        mock_dependencies.llm_caller.set_workspace_root.assert_called_once_with(workspace_root)

    def test_to_state_updates_returns_correct_structure(self, mock_dependencies):
        """to_state_updates returns proper state dict."""
        state_doc = {
            "SESSION_STATE": {
                "phase": "6-PostFlight",
                "next": "6",
                "phase5_plan_record_digest": "sha256:plan-v1",
                "phase6_force_stable_digest": True,
            }
        }
        config = ReviewLoopConfig(
            commands_home=Path("/tmp"),
            session_path=Path("/tmp/session.json"),
            max_iterations=1,
            min_iterations=1,
            force_stable_digest=True,
        )

        result = run_review_loop(
            state_doc=state_doc,
            config=config,
            dependencies=mock_dependencies,
            json_loader=_mock_json_loader,
            context_writer=_mock_context_writer,
            clock=_mock_clock,
        )

        updates = result.loop_result.to_state_updates()
        assert "ImplementationReview" in updates
        assert "phase6_review_iterations" in updates
        assert "implementation_review_complete" in updates
        assert updates["implementation_review_complete"] is True
        assert updates["ImplementationReview"]["llm_review_binding_role"] == "review"
        assert (
            updates["ImplementationReview"]["llm_review_binding_source"]
            == "env:AI_GOVERNANCE_REVIEW_BINDING"
        )

    def test_to_audit_events_returns_iterations(self, mock_dependencies):
        """to_audit_events returns audit events for each iteration."""
        state_doc = {
            "SESSION_STATE": {
                "phase": "6-PostFlight",
                "next": "6",
                "phase5_plan_record_digest": "sha256:plan-v1",
                "phase6_force_stable_digest": True,
            }
        }
        config = ReviewLoopConfig(
            commands_home=Path("/tmp"),
            session_path=Path("/tmp/session.json"),
            max_iterations=2,
            min_iterations=1,
            force_stable_digest=True,
        )

        result = run_review_loop(
            state_doc=state_doc,
            config=config,
            dependencies=mock_dependencies,
            json_loader=_mock_json_loader,
            context_writer=_mock_context_writer,
            clock=_mock_clock,
        )

        events = result.loop_result.to_audit_events()
        assert len(events) == 2
        assert events[0]["event"] == "phase6-implementation-review-iteration"
        assert events[0]["iteration"] == 1
        assert events[1]["iteration"] == 2


class TestReviewDependencies:
    """Tests for ReviewDependencies."""

    def test_default_creates_real_instances(self):
        """default() creates real component instances."""
        deps = ReviewDependencies.default()
        assert isinstance(deps.policy_resolver, PolicyResolver)
        assert isinstance(deps.llm_caller, LLMCaller)
        assert isinstance(deps.response_validator, ResponseValidator)
