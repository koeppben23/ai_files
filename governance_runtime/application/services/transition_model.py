"""Transition Model for Governance Workflow.

This module defines the explicit transition model for the governance workflow:
- Transition definitions (from_gate, event, guard, to_gate, command)
- Guard functions (pure functions that check preconditions)
- Resolver that evaluates transitions based on state

The model is the single source of truth for next_action derivation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Literal, Mapping

from governance_runtime.application.services.state_normalizer import normalize_to_canonical


NextActionCommand = Literal[
    "/ticket",
    "/plan",
    "/continue",
    "/review-decision",
    "/implementation-decision",
    "/implement",
    "chat",
    "execute",
    "delivery",
]


class NextActionKind(str, Enum):
    NORMAL = "normal"
    BLOCKED = "blocked"
    RECOVERY = "recovery"
    TERMINAL = "terminal"
    IMPLEMENTATION = "implementation"


@dataclass(frozen=True)
class GuardResult:
    passed: bool
    reason: str = ""


@dataclass(frozen=True)
class Transition:
    source_gate: str
    target_gate: str | None
    command: NextActionCommand
    kind: NextActionKind
    reason: str
    guard: Callable[[Mapping], GuardResult] | None = None
    condition: Callable[[Mapping], bool] | None = None
    label_template: str = "run {command}."


Guard = Callable[[Mapping], GuardResult]
Condition = Callable[[Mapping], bool]


def _always_pass(_state: Mapping) -> GuardResult:
    return GuardResult(passed=True)


def _always_fail(_state: Mapping) -> GuardResult:
    return GuardResult(passed=False, reason="always fails")


def _has_rework_clarification_input(state: Mapping) -> GuardResult:
    text = str(
        state.get("rework_clarification_input") or
        state.get("rework_clarification_text") or
        state.get("rework_clarification_note") or
        ""
    ).strip()
    return GuardResult(passed=bool(text), reason="rework clarification input present" if text else "no rework clarification")


def _plan_versions_available(state: Mapping) -> GuardResult:
    versions = state.get("plan_record_versions", 0)
    return GuardResult(
        passed=int(versions or 0) >= 1,
        reason=f"plan versions: {versions}",
    )


def _p54_compliant(state: Mapping) -> GuardResult:
    p54 = str(state.get("p54_evaluated_status") or "").strip().lower()
    compliant = p54 in {"compliant", "compliant-with-exceptions", "not-applicable"}
    return GuardResult(passed=compliant, reason=f"p54 status: {p54}")


def _p55_approved(state: Mapping) -> GuardResult:
    p55 = str(state.get("p55_evaluated_status") or "").strip().lower()
    approved = p55 in {"approved", "not-applicable"}
    return GuardResult(passed=approved, reason=f"p55 status: {p55}")


def _p56_approved(state: Mapping) -> GuardResult:
    p56 = str(state.get("p56_evaluated_status") or "").strip().lower()
    approved = p56 in {"approved", "not-applicable"}
    return GuardResult(passed=approved, reason=f"p56 status: {p56}")


def _status_error(state: Mapping) -> bool:
    canonical = normalize_to_canonical(dict(state))
    return str(canonical.get("status") or "").strip().lower() == "error"


def _status_blocked(state: Mapping) -> bool:
    canonical = normalize_to_canonical(dict(state))
    return str(canonical.get("status") or "").strip().lower() == "blocked"


def _is_phase4(state: Mapping) -> bool:
    canonical = normalize_to_canonical(dict(state))
    phase = str(canonical.get("phase") or "").strip()
    return phase.startswith("4") or phase.lower() == "ticket input gate"


def _is_phase5(state: Mapping) -> bool:
    canonical = normalize_to_canonical(dict(state))
    phase = str(canonical.get("phase") or "").strip()
    return phase.startswith("5")


def _is_phase6(state: Mapping) -> bool:
    canonical = normalize_to_canonical(dict(state))
    phase = str(canonical.get("phase") or "").strip()
    return phase.startswith("6")


def _gate_equals(state: Mapping, expected: str) -> bool:
    gate = str(state.get("active_gate") or "").strip().lower()
    return gate == expected.lower()


def _next_condition_contains(state: Mapping, substring: str) -> bool:
    condition = str(state.get("next_gate_condition") or "").strip().lower()
    return substring.lower() in condition


@dataclass(frozen=True)
class TransitionTable:
    """Immutable table of transition rules."""

    transitions: tuple[Transition, ...] = field(default_factory=tuple)

    def find_matching(
        self,
        state: Mapping,
        source_gate: str,
    ) -> Transition | None:
        """Find first matching transition for the given gate."""
        for t in self.transitions:
            if t.source_gate.lower() != source_gate.lower():
                continue
            if t.condition is not None and not t.condition(state):
                continue
            if t.guard is not None:
                result = t.guard(state)
                if not result.passed:
                    continue
            return t
        return None


PHASE4_TRANSITIONS = TransitionTable(
    transitions=(
        Transition(
            source_gate="ticket input gate",
            target_gate="ticket input gate",
            command="/ticket",
            kind=NextActionKind.NORMAL,
            reason="phase4-ticket-input",
            label_template="run /ticket with the ticket/task details.",
        ),
        Transition(
            source_gate="plan record preparation gate",
            target_gate="plan record preparation gate",
            command="/plan",
            kind=NextActionKind.NORMAL,
            reason="plan-record-missing",
            guard=_plan_versions_available,
            condition=lambda s: _is_phase4(s),
            label_template="run /plan.",
        ),
    )
)

PHASE5_TRANSITIONS = TransitionTable(
    transitions=(
        Transition(
            source_gate="*",
            target_gate=None,
            command="/continue",
            kind=NextActionKind.NORMAL,
            reason="phase5-progress",
            condition=_is_phase5,
            label_template="run /continue.",
        ),
    )
)

PHASE6_TRANSITIONS = TransitionTable(
    transitions=(
        Transition(
            source_gate="workflow complete",
            target_gate="workflow complete",
            command="/implement",
            kind=NextActionKind.TERMINAL,
            reason="workflow-approved",
            condition=_is_phase6,
            label_template="run /implement.",
        ),
        Transition(
            source_gate="implementation started",
            target_gate="implementation started",
            command="execute",
            kind=NextActionKind.IMPLEMENTATION,
            reason="implementation-running",
            condition=_is_phase6,
            label_template="continue implementation work on the approved plan.",
        ),
        Transition(
            source_gate="implementation execution in progress",
            target_gate=None,
            command="/continue",
            kind=NextActionKind.NORMAL,
            reason="implementation-loop-progress",
            condition=_is_phase6,
            label_template="run /continue.",
        ),
        Transition(
            source_gate="implementation self review",
            target_gate=None,
            command="/continue",
            kind=NextActionKind.NORMAL,
            reason="implementation-loop-progress",
            condition=_is_phase6,
            label_template="run /continue.",
        ),
        Transition(
            source_gate="implementation revision",
            target_gate=None,
            command="/continue",
            kind=NextActionKind.NORMAL,
            reason="implementation-loop-progress",
            condition=_is_phase6,
            label_template="run /continue.",
        ),
        Transition(
            source_gate="implementation verification",
            target_gate=None,
            command="/continue",
            kind=NextActionKind.NORMAL,
            reason="implementation-loop-progress",
            condition=_is_phase6,
            label_template="run /continue.",
        ),
        Transition(
            source_gate="implementation review complete",
            target_gate=None,
            command="/continue",
            kind=NextActionKind.NORMAL,
            reason="implementation-loop-progress",
            condition=_is_phase6,
            label_template="run /continue.",
        ),
        Transition(
            source_gate="implementation blocked",
            target_gate="implementation blocked",
            command="/implement",
            kind=NextActionKind.BLOCKED,
            reason="implementation-blocked",
            condition=_is_phase6,
            label_template="resolve implementation blockers, then run /implement.",
        ),
        Transition(
            source_gate="implementation presentation gate",
            target_gate="implementation presentation gate",
            command="/implementation-decision",
            kind=NextActionKind.NORMAL,
            reason="implementation-decision-available",
            condition=_is_phase6,
            label_template="run /implementation-decision <approve|changes_requested|reject>.",
        ),
        Transition(
            source_gate="evidence presentation gate",
            target_gate="evidence presentation gate",
            command="/review-decision",
            kind=NextActionKind.NORMAL,
            reason="awaiting-final-decision",
            condition=_is_phase6,
            label_template="run /review-decision <approve|changes_requested|reject>.",
        ),
        Transition(
            source_gate="*",
            target_gate=None,
            command="/continue",
            kind=NextActionKind.NORMAL,
            reason="phase6-progress",
            condition=_is_phase6,
            label_template="run /continue.",
        ),
    )
)

STATUS_OVERRIDE_TRANSITIONS = TransitionTable(
    transitions=(
        Transition(
            source_gate="*",
            target_gate=None,
            command="/continue",
            kind=NextActionKind.RECOVERY,
            reason="error-status",
            condition=_status_error,
            label_template="resolve the reported error, then run /continue.",
        ),
        Transition(
            source_gate="*",
            target_gate=None,
            command="/continue",
            kind=NextActionKind.BLOCKED,
            reason="blocked-status",
            condition=_status_blocked,
            label_template="resolve the reported blocker evidence, then run /continue.",
        ),
    )
)


@dataclass(frozen=True)
class ResolvedNextAction:
    command: NextActionCommand
    label: str
    kind: NextActionKind
    reason: str


def resolve_next_action(state: Mapping) -> ResolvedNextAction:
    """Resolve the canonical next action from state using the transition model."""
    
    if _status_error(state):
        return ResolvedNextAction(
            command="/continue",
            label="resolve the reported error, then run /continue.",
            kind=NextActionKind.RECOVERY,
            reason="error-status",
        )

    if _status_blocked(state):
        return ResolvedNextAction(
            command="/continue",
            label="resolve the reported blocker evidence, then run /continue.",
            kind=NextActionKind.BLOCKED,
            reason="blocked-status",
        )

    canonical = normalize_to_canonical(dict(state))
    gate = str(canonical.get("active_gate") or "").strip().lower()
    phase = str(canonical.get("phase") or "").strip()

    if _is_phase4(state) or gate == "ticket input gate":
        match = PHASE4_TRANSITIONS.find_matching(state, gate)
        if match:
            label = match.label_template.format(command=match.command)
            return ResolvedNextAction(
                command=match.command,
                label=label,
                kind=match.kind,
                reason=match.reason,
            )

    if _is_phase5(state):
        match = PHASE5_TRANSITIONS.find_matching(state, gate)
        if match:
            label = match.label_template.format(command=match.command)
            return ResolvedNextAction(
                command=match.command,
                label=label,
                kind=match.kind,
                reason=match.reason,
            )

    if _is_phase6(state):
        match = PHASE6_TRANSITIONS.find_matching(state, gate)
        if match:
            label = match.label_template.format(command=match.command)
            return ResolvedNextAction(
                command=match.command,
                label=label,
                kind=match.kind,
                reason=match.reason,
            )

    return ResolvedNextAction(
        command="/continue",
        label="run /continue.",
        kind=NextActionKind.NORMAL,
        reason="default-progress",
    )
