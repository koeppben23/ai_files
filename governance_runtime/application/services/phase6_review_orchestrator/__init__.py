"""Phase-6 Review Orchestrator Package.

Provides a clean orchestrator for Phase-6 internal review loop with:
- PolicyResolver: Loads and formats review mandates and policies
- LLMCaller: Invokes LLM executor for implementation review
- ResponseValidator: Validates LLM responses against schema
- ReviewResultAssembler: Assembles structured review results
- run_review_loop: Main orchestrator that coordinates the review loop

The orchestrator follows strict boundaries:
- Reads state_doc but never mutates it
- Returns a ReviewResult that the entrypoint applies and persists
- No direct event persistence (entrypoint handles that)
- commands_home is injected, not derived internally
"""

from __future__ import annotations

from governance_runtime.application.services.phase6_review_orchestrator.policy_resolver import (
    PolicyResolver,
    MandateSchema,
    ReviewPolicy,
)
from governance_runtime.application.services.phase6_review_orchestrator.llm_caller import (
    LLMCaller,
    LLMResponse,
)
from governance_runtime.application.services.phase6_review_orchestrator.response_validator import (
    ResponseValidator,
    ValidationResult,
)
from governance_runtime.application.services.phase6_review_orchestrator.review_result import (
    ReviewResult,
    ReviewIteration,
    ReviewOutcome,
    CompletionStatus,
)
from governance_runtime.application.services.phase6_review_orchestrator.orchestrator import (
    run_review_loop,
    ReviewLoopConfig,
    ReviewDependencies,
)

# Legacy compatibility exports
BLOCKED_EFFECTIVE_POLICY_UNAVAILABLE = "BLOCKED-EFFECTIVE-POLICY-UNAVAILABLE"
BLOCKED_MANDATE_SCHEMA_UNAVAILABLE = "MANDATE-SCHEMA-UNAVAILABLE"

# Module-level instances for dependency injection and mocking
_policy_resolver_instance = None
_llm_caller_instance = None
_response_validator_instance = None


def _get_policy_resolver():
    """Get the policy resolver instance (can be mocked in tests)."""
    global _policy_resolver_instance
    if _policy_resolver_instance is None:
        _policy_resolver_instance = PolicyResolver()
    return _policy_resolver_instance


def _get_llm_caller():
    """Get the LLM caller instance (can be mocked in tests)."""
    global _llm_caller_instance
    if _llm_caller_instance is None:
        import os

        def _bridge_env_factory() -> dict[str, str]:
            env = dict(os.environ)
            for key in (
                "OPENCODE",
                "OPENCODE_CLIENT",
                "OPENCODE_PID",
                "OPENCODE_SERVER_USERNAME",
                "OPENCODE_SERVER_PASSWORD",
            ):
                env.pop(key, None)
            return env

        _llm_caller_instance = LLMCaller(
            env_reader=lambda key: os.environ.get(key),
            bridge_env_factory=_bridge_env_factory,
        )
    return _llm_caller_instance


def _get_response_validator():
    """Get the response validator instance (can be mocked in tests)."""
    global _response_validator_instance
    if _response_validator_instance is None:
        _response_validator_instance = ResponseValidator()
    return _response_validator_instance


def _set_policy_resolver(resolver):
    """Set the policy resolver instance (for testing)."""
    global _policy_resolver_instance
    _policy_resolver_instance = resolver


def _set_llm_caller(caller):
    """Set the LLM caller instance (for testing)."""
    global _llm_caller_instance
    _llm_caller_instance = caller


def _set_response_validator(validator):
    """Set the response validator instance (for testing)."""
    global _response_validator_instance
    _response_validator_instance = validator


def _reset_instances():
    """Reset all module-level instances (for testing cleanup)."""
    global _policy_resolver_instance, _llm_caller_instance, _response_validator_instance
    _policy_resolver_instance = None
    _llm_caller_instance = None
    _response_validator_instance = None
