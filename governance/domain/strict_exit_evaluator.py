"""Legacy compatibility bridge for strict-exit evaluator.

DEPRECATED: use governance_runtime.domain.strict_exit_evaluator.
"""

from governance_runtime.domain.strict_exit_evaluator import (  # noqa: F401
    CriterionResult,
    StrictExitResult,
    StrictVerdict,
    evaluate_strict_exit,
    get_threshold_resolver,
)

__all__ = [
    "CriterionResult",
    "StrictExitResult",
    "StrictVerdict",
    "evaluate_strict_exit",
    "get_threshold_resolver",
]
