"""Legacy compatibility bridge for plan record state.

DEPRECATED: use governance_runtime.infrastructure.plan_record_state.
"""

from governance_runtime.infrastructure.plan_record_state import (
    PlanRecordSignal,
    resolve_plan_record_signal,
)

__all__ = ["PlanRecordSignal", "resolve_plan_record_signal"]
