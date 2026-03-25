"""Guard Evaluator - transition guard evaluation from guards.yaml.

Evaluates transition guards from governance_spec/guards.yaml using the
closed condition grammar. In WP3 this is integrated in the Phase-6
topology-authoritative transition path in phase_kernel, where the evaluator
determines which event fires and topology resolves the target state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from governance_runtime.kernel.spec_registry import SpecRegistry


class GuardEvaluationError(RuntimeError):
    """Raised when guard evaluation cannot be performed safely."""


@dataclass(frozen=True)
class TransitionGuard:
    """Transition guard definition from guards.yaml."""

    id: str
    event: str
    condition: Mapping[str, Any]


class GuardEvaluator:
    """Evaluates transition guards defined in guards.yaml."""

    _transition_guards_by_event: dict[str, TransitionGuard] | None = None

    @classmethod
    def reset(cls) -> None:
        cls._transition_guards_by_event = None

    @classmethod
    def _ensure_loaded(cls) -> None:
        if cls._transition_guards_by_event is not None:
            return

        guards_spec = SpecRegistry.get_guards()
        by_event: dict[str, TransitionGuard] = {}
        for raw in guards_spec.get("guards", []):
            if raw.get("guard_type") != "transition":
                continue
            event = str(raw.get("event", "")).strip()
            if not event:
                continue
            by_event[event] = TransitionGuard(
                id=str(raw.get("id", "")),
                event=event,
                condition=raw.get("condition", {}),
            )
        cls._transition_guards_by_event = by_event

    @classmethod
    def evaluate_event(
        cls,
        event: str,
        state: Mapping[str, Any],
        *,
        context: Mapping[str, Any] | None = None,
    ) -> bool:
        """Return True if transition event guard passes for this state."""
        cls._ensure_loaded()
        guard = cls._transition_guards_by_event.get(event)
        if guard is None:
            raise GuardEvaluationError(
                f"Transition guard for event '{event}' not found in guards.yaml"
            )

        merged = dict(state)
        if context:
            merged.update(context)
        return cls._eval_condition(guard.condition, merged)

    @classmethod
    def _eval_condition(cls, node: Mapping[str, Any], state: Mapping[str, Any]) -> bool:
        node_type = str(node.get("type", "")).strip()
        if not node_type:
            raise GuardEvaluationError("Guard condition missing 'type'")

        if node_type == "always":
            return True

        if node_type == "all_of":
            operands = node.get("operands")
            if not isinstance(operands, list) or not operands:
                raise GuardEvaluationError("all_of requires non-empty operands")
            return all(cls._eval_condition(op, state) for op in operands)

        if node_type == "any_of":
            operands = node.get("operands")
            if not isinstance(operands, list) or not operands:
                raise GuardEvaluationError("any_of requires non-empty operands")
            return any(cls._eval_condition(op, state) for op in operands)

        key = str(node.get("key", "")).strip()
        if not key:
            raise GuardEvaluationError(f"{node_type} requires 'key'")
        value = cls._read_key(state, key)

        if node_type == "key_present":
            return value is not None

        if node_type == "key_missing":
            return value is None

        if node_type == "key_equals":
            return value == node.get("value")

        if node_type == "numeric_gte":
            operator = str(node.get("operator", "gte")).strip().lower()
            threshold = node.get("threshold", {})
            threshold_value = threshold.get("value") if isinstance(threshold, Mapping) else None
            try:
                left = float(value)
                right = float(threshold_value)
            except (TypeError, ValueError):
                return False
            if operator == "gte":
                return left >= right
            if operator == "lt":
                return left < right
            raise GuardEvaluationError(f"Unsupported numeric_gte operator '{operator}'")

        raise GuardEvaluationError(f"Unsupported guard condition type '{node_type}'")

    @staticmethod
    def _read_key(state: Mapping[str, Any], key_path: str) -> Any:
        current: Any = state
        for segment in key_path.split("."):
            if not isinstance(current, Mapping) or segment not in current:
                return None
            current = current[segment]
        return current
