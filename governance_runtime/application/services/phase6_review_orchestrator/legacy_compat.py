"""Legacy compatibility layer for Phase-6 review functions.

This module provides backward-compatible aliases for functions that were
previously defined in session_reader.py. These are used by existing tests
and should be migrated over time.

New code should import directly from:
- governance_runtime.application.services.phase6_review_orchestrator
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from governance_runtime.application.services.phase6_review_orchestrator import (
    PolicyResolver,
    LLMCaller,
    ResponseValidator,
    ReviewResult,
    ReviewLoopConfig,
    run_review_loop,
    BLOCKED_EFFECTIVE_POLICY_UNAVAILABLE,
)


# Module-level instances for backward compatibility
_policy_resolver = PolicyResolver()
_llm_caller = LLMCaller()
_response_validator = ResponseValidator()


def load_mandates_schema() -> dict[str, object] | None:
    """Load mandates schema (legacy alias)."""
    result = _policy_resolver.load_mandate_schema()
    return result.raw_schema if result else None


def get_review_output_schema_text() -> str:
    """Get review output schema text (legacy alias)."""
    result = _policy_resolver.load_mandate_schema()
    return result.review_output_schema_text if result else ""


def build_review_mandate_text(schema: dict[str, object]) -> str:
    """Build mandate text (legacy alias)."""
    result = _policy_resolver.load_mandate_schema()
    return result.mandate_text if result else ""


def load_effective_review_policy_text(state: Any, commands_home: Path) -> tuple[str, str]:
    """Load effective review policy (legacy alias)."""
    result = _policy_resolver.load_effective_review_policy(
        state=state, commands_home=commands_home
    )
    return result.policy_text, result.error_code or ""


def has_any_llm_executor() -> bool:
    """Check if LLM executor is configured (legacy alias)."""
    return _llm_caller.is_configured


def parse_llm_review_response(
    response_text: str, mandates_schema: dict[str, object] | None = None
) -> dict:
    """Parse LLM review response (legacy alias)."""
    result = _response_validator.validate(response_text, mandates_schema=mandates_schema)
    return {
        "llm_invoked": True,
        "validation_valid": result.valid,
        "verdict": result.verdict,
        "findings": result.findings,
        "validation_violations": result.violations,
        "raw_response": result.raw_response,
    }


def read_plan_body(session_path: Path, json_loader: Callable[[Path], dict] | None = None) -> str:
    """Read plan body from plan-record.json.
    
    Args:
        session_path: Path to the session file.
        json_loader: Injectable JSON loader (for testing). If None,
                    raises ValueError to enforce architecture rules.
    """
    if json_loader is None:
        raise ValueError("json_loader is required for read_plan_body (inject load_json from infrastructure)")
    try:
        plan_record_path = session_path.parent / "plan-record.json"
        if plan_record_path.is_file():
            payload = json_loader(plan_record_path)
            if isinstance(payload, dict):
                body = payload.get("body") or payload.get("planBody") or payload.get("plan_body")
                if isinstance(body, str) and body.strip():
                    return body.strip()
    except Exception:
        pass
    return "none"


def sync_phase6_completion_fields(*, state_doc: dict) -> None:
    """Synchronize Phase 6 completion fields (legacy no-op).

    The orchestrator now handles completion status correctly in its result.
    This function is kept for backward compatibility.
    """
    pass


# Re-export for backward compatibility
BLOCKED_EFFECTIVE_POLICY_UNAVAILABLE_ALIAS = BLOCKED_EFFECTIVE_POLICY_UNAVAILABLE
