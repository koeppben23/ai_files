"""Canonical user-facing next-action resolver.

This module is the single source of truth for operator guidance lines that are
rendered at the bottom of session readouts and reused by mutating rails.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class NextActionRender:
    command: str
    label: str
    kind: str
    reason: str


def _coerce_int(value: object) -> int:
    try:
        if value is None:
            return 0
        if isinstance(value, bool):
            return 1 if value else 0
        if isinstance(value, int):
            return max(0, value)
        return max(0, int(str(value).strip()))
    except (TypeError, ValueError):
        return 0


def _normalized_text(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _phase_text(snapshot: Mapping[str, object]) -> str:
    return str(snapshot.get("phase") or "").strip()


def _active_gate(snapshot: Mapping[str, object]) -> str:
    return str(snapshot.get("active_gate") or "").strip().lower()


def _status(snapshot: Mapping[str, object]) -> str:
    return str(snapshot.get("status") or "").strip().lower()


def _review_clarification_has_input(snapshot: Mapping[str, object]) -> bool:
    text = str(
        snapshot.get("rework_clarification_input")
        or snapshot.get("rework_clarification_text")
        or snapshot.get("rework_clarification_note")
        or ""
    ).strip()
    return bool(text)


_PHASE4_TICKET_REVIEW_LABEL = (
    "run /ticket with the ticket/task details. "
    "Alternative: run /review for read-only feedback (no state change)."
)


def _validate_next_action_alignment(snapshot: Mapping[str, object], render: NextActionRender) -> bool:
    phase = _phase_text(snapshot)
    gate = _active_gate(snapshot)
    next_condition = _normalized_text(snapshot.get("next_gate_condition"))
    command = render.command.strip().lower()
    label = _normalized_text(render.label)

    if gate == "ticket input gate" or phase.startswith("4"):
        return command == "/ticket" and "/review" in label

    if "/review-decision" in next_condition:
        return command == "/review-decision"
    if "/implementation-decision" in next_condition:
        return command == "/implementation-decision"
    if "run /plan" in next_condition:
        return command == "/plan"
    if "run /ticket" in next_condition:
        return command == "/ticket"
    if "run /continue" in next_condition:
        return command == "/continue"

    if gate == "workflow complete":
        return command == "/implement"
    if gate == "plan record preparation gate":
        versions = _coerce_int(snapshot.get("plan_record_versions"))
        if versions < 1:
            return command == "/plan"
    if gate == "implementation blocked":
        return command == "/implement"

    return True


def _fallback_next_action(snapshot: Mapping[str, object]) -> NextActionRender:
    phase = _phase_text(snapshot)
    gate = _active_gate(snapshot)
    next_condition = _normalized_text(snapshot.get("next_gate_condition"))

    if gate == "ticket input gate" or phase.startswith("4"):
        return NextActionRender(
            command="/ticket",
            label=_PHASE4_TICKET_REVIEW_LABEL,
            kind="normal",
            reason="phase4-ticket-input-fallback",
        )
    if "/review-decision" in next_condition:
        return NextActionRender(
            command="/review-decision",
            label="run /review-decision <approve|changes_requested|reject>.",
            kind="normal",
            reason="condition-review-decision-fallback",
        )
    if "/implementation-decision" in next_condition:
        return NextActionRender(
            command="/implementation-decision",
            label="run /implementation-decision <approve|changes_requested|reject>.",
            kind="normal",
            reason="condition-implementation-decision-fallback",
        )
    if "run /plan" in next_condition or gate == "plan record preparation gate":
        return NextActionRender(
            command="/plan",
            label="run /plan.",
            kind="normal",
            reason="condition-plan-fallback",
        )
    if "run /ticket" in next_condition:
        return NextActionRender(
            command="/ticket",
            label=_PHASE4_TICKET_REVIEW_LABEL,
            kind="normal",
            reason="condition-ticket-fallback",
        )
    if gate == "implementation blocked":
        return NextActionRender(
            command="/implement",
            label="resolve implementation blockers, then run /implement.",
            kind="blocked",
            reason="implementation-blocked-fallback",
        )
    if gate == "workflow complete":
        return NextActionRender(
            command="/implement",
            label="run /implement.",
            kind="terminal",
            reason="workflow-approved-fallback",
        )
    return NextActionRender(
        command="/continue",
        label="run /continue.",
        kind="normal",
        reason="default-fallback",
    )


def _resolve_next_action_candidate(snapshot: Mapping[str, object]) -> NextActionRender:
    """Resolve exactly one canonical user-facing next action.

    The returned ``label`` is intended to be rendered verbatim as:
    ``Next action: <label>``.
    """

    status = _status(snapshot)
    phase = _phase_text(snapshot)
    gate = _active_gate(snapshot)
    next_condition = _normalized_text(snapshot.get("next_gate_condition"))

    if status == "error":
        return NextActionRender(
            command="/continue",
            label="resolve the reported error, then run /continue.",
            kind="recovery",
            reason="error-status",
        )

    if status == "blocked":
        return NextActionRender(
            command="/continue",
            label="resolve the reported blocker evidence, then run /continue.",
            kind="blocked",
            reason="blocked-status",
        )

    if gate == "ticket input gate" or phase.startswith("4"):
        return NextActionRender(
            command="/ticket",
            label=_PHASE4_TICKET_REVIEW_LABEL,
            kind="normal",
            reason="phase4-ticket-input",
        )

    if gate == "plan record preparation gate":
        versions = _coerce_int(snapshot.get("plan_record_versions"))
        if versions < 1:
            return NextActionRender(
                command="/plan",
                label="run /plan.",
                kind="normal",
                reason="plan-record-missing",
            )

    if phase.startswith("5"):
        if phase.startswith("5.4"):
            p54 = _normalized_text(snapshot.get("p54_evaluated_status"))
            if p54 not in {"compliant", "compliant-with-exceptions", "not-applicable"}:
                return NextActionRender(
                    command="chat",
                    label="complete the active business-rules validation work in chat.",
                    kind="blocked",
                    reason="p54-open",
                )
        if phase.startswith("5.5"):
            p55 = _normalized_text(snapshot.get("p55_evaluated_status"))
            if p55 not in {"approved", "not-applicable"}:
                return NextActionRender(
                    command="chat",
                    label="complete the active technical-debt validation work in chat.",
                    kind="blocked",
                    reason="p55-open",
                )
        if phase.startswith("5.6"):
            p56 = _normalized_text(snapshot.get("p56_evaluated_status"))
            if p56 not in {"approved", "not-applicable"}:
                return NextActionRender(
                    command="chat",
                    label="complete the active rollback-safety validation work in chat.",
                    kind="blocked",
                    reason="p56-open",
                )

        return NextActionRender(
            command="/continue",
            label="run /continue.",
            kind="normal",
            reason="phase5-progress",
        )

    if phase.startswith("6"):
        if gate == "workflow complete":
            return NextActionRender(
                command="/implement",
                label="run /implement.",
                kind="terminal",
                reason="workflow-approved",
            )
        if gate == "implementation started":
            return NextActionRender(
                command="execute",
                label="continue implementation work on the approved plan.",
                kind="implementation",
                reason="implementation-running",
            )
        if gate in {
            "implementation execution in progress",
            "implementation self review",
            "implementation revision",
            "implementation verification",
            "implementation review complete",
        }:
            return NextActionRender(
                command="/continue",
                label="run /continue.",
                kind="normal",
                reason="implementation-loop-progress",
            )
        if gate == "implementation blocked":
            return NextActionRender(
                command="/implement",
                label="resolve implementation blockers, then run /implement.",
                kind="blocked",
                reason="implementation-blocked",
            )
        if gate == "implementation presentation gate":
            return NextActionRender(
                command="/implementation-decision",
                label="run /implementation-decision <approve|changes_requested|reject>.",
                kind="normal",
                reason="implementation-decision-available",
            )
        if gate == "implementation rework clarification gate":
            text = str(snapshot.get("implementation_rework_clarification_input") or "").strip()
            if text:
                return NextActionRender(
                    command="/implement",
                    label="run /implement.",
                    kind="normal",
                    reason="implementation-rework-clarified",
                )
            return NextActionRender(
                command="chat",
                label="describe requested implementation changes in chat.",
                kind="blocked",
                reason="implementation-rework-clarification-required",
            )
        if gate == "implementation accepted":
            return NextActionRender(
                command="delivery",
                label="continue delivery workflow for the accepted implementation result.",
                kind="terminal",
                reason="implementation-accepted",
            )
        if gate == "evidence presentation gate":
            return NextActionRender(
                command="/review-decision",
                label="run /review-decision <approve|changes_requested|reject>.",
                kind="normal",
                reason="awaiting-final-decision",
            )
        if gate == "rework clarification gate":
            if _review_clarification_has_input(snapshot):
                from governance.application.use_cases.rework_clarification import (
                    classify_rework_clarification,
                    derive_next_rail,
                )

                text = str(
                    snapshot.get("rework_clarification_input")
                    or snapshot.get("rework_clarification_text")
                    or snapshot.get("rework_clarification_note")
                    or ""
                ).strip()
                rail = derive_next_rail(classify_rework_clarification(text))
                if rail == "/ticket":
                    return NextActionRender(
                        command="/ticket",
                        label="run /ticket with the revised task details.",
                        kind="normal",
                        reason="clarification-directed-ticket",
                    )
                if rail == "/plan":
                    return NextActionRender(
                        command="/plan",
                        label="run /plan with the updated plan details.",
                        kind="normal",
                        reason="clarification-directed-plan",
                    )
                return NextActionRender(
                    command="/continue",
                    label="run /continue.",
                    kind="normal",
                    reason="clarification-directed-continue",
                )
            return NextActionRender(
                command="chat",
                label="describe the requested changes in chat.",
                kind="blocked",
                reason="clarification-required",
            )

        if "review-decision" in next_condition:
            return NextActionRender(
                command="/review-decision",
                label="run /review-decision <approve|changes_requested|reject>.",
                kind="normal",
                reason="decision-available",
            )
        if "implementation-decision" in next_condition:
            return NextActionRender(
                command="/implementation-decision",
                label="run /implementation-decision <approve|changes_requested|reject>.",
                kind="normal",
                reason="implementation-decision-by-condition",
            )

        return NextActionRender(
            command="/continue",
            label="run /continue.",
            kind="normal",
            reason="phase6-progress",
        )

    return NextActionRender(
        command="/continue",
        label="run /continue.",
        kind="normal",
        reason="default-progress",
    )


def resolve_next_action(snapshot: Mapping[str, object]) -> NextActionRender:
    candidate = _resolve_next_action_candidate(snapshot)
    if _validate_next_action_alignment(snapshot, candidate):
        return candidate
    return _fallback_next_action(snapshot)
