"""Phase-5 Normalizer for governance state.

This module handles normalization and synchronization of Phase-5 (P5) gate
states. It provides functions to:

1. Canonicalize legacy P5.x surfaces to explicit phases
2. Synchronize conditional P5 gate states from evaluators
3. Detect and correct inconsistent Phase 6 / P5 gate states

These functions modify state_doc in place (as required by the governance
kernel contract) but do not persist events - the entrypoint handles persistence.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from governance_runtime.application.services.phase5_gate_constants import (
    GATE_TO_PHASE_NEXT,
    P5_GATE_PRIORITY_ORDER,
    P5_GATE_TERMINAL_VALUES,
    reason_code_for_gate,
)
from governance_runtime.application.services.phase5_gate_evaluators import (
    GateEvaluationResult,
    evaluate_p53_test_quality,
    evaluate_p54_business_rules,
    evaluate_p55_technical_debt,
    evaluate_p56_rollback_safety,
    phase_1_5_executed,
)
from governance_runtime.application.services.state_normalizer import (
    normalize_to_canonical,
)


@dataclass(frozen=True)
class GateEvaluators:
    """Injectable gate evaluators for testing.
    
    Each evaluator returns an object with a `status` attribute.
    """
    evaluate_p53: Callable[..., Any]  # Returns object with .status
    evaluate_p54: Callable[..., Any]  # Returns object with .status
    evaluate_p55: Callable[..., Any]  # Returns object with .status
    evaluate_p56: Callable[..., Any]  # Returns object with .status
    phase_1_5_executed: Callable[[dict], bool]


@dataclass(frozen=True)
class GateConstants:
    """Injectable gate constants for testing.
    
    Contains the canonical gate priority order, terminal values, and
    reason code mapping from the engine.gate_evaluator module.
    """
    priority_order: tuple[str, ...]
    terminal_values: dict[str, tuple[str, ...]]
    reason_code_for_gate: Callable[[str], str]


def canonicalize_legacy_p5x_surface(*, state_doc: dict) -> None:
    """Normalize legacy Phase-5 architecture surface to canonical P5.x states.

    Older snapshots may expose open P5.x gates through
    ``phase=5-ArchitectureReview`` with legacy gate labels. Canonicalize those
    to the explicit user-facing P5.x phases so /continue does not stay stuck on
    the generic architecture-review surface.

    Modifies state_doc in place.
    """
    state_obj = state_doc.get("SESSION_STATE")
    state = state_obj if isinstance(state_obj, dict) else state_doc

    canonical = normalize_to_canonical(state)

    phase_text = str(canonical.get("phase") or "").strip()
    if phase_text != "5-ArchitectureReview":
        return

    next_token = str(canonical.get("next_action") or "").strip()
    active_gate = str(canonical.get("active_gate") or "").strip().lower()
    ngc = str(canonical.get("next_gate_condition") or "").strip().upper()

    target: tuple[str, str, str] | None = None

    if (
        next_token == "5.4"
        or "BLOCKED-P5-4-BUSINESS-RULES-GATE" in ngc
        or active_gate in {"business rules compliance gate", "business rules validation"}
    ):
        target = ("5.4-BusinessRules", "5.4", "Business Rules Validation")
    elif (
        next_token == "5.5"
        or "BLOCKED-P5-5-TECHNICAL-DEBT-GATE" in ngc
        or active_gate in {"technical debt gate", "technical debt review"}
    ):
        target = ("5.5-TechnicalDebt", "5.5", "Technical Debt Review")
    elif (
        next_token == "5.6"
        or "BLOCKED-P5-6-ROLLBACK-SAFETY-GATE" in ngc
        or active_gate in {"rollback safety gate", "rollback safety review"}
    ):
        target = ("5.6-RollbackSafety", "5.6", "Rollback Safety Review")

    if target is None:
        return

    canonical_phase, canonical_next, canonical_gate = target
    state["phase"] = canonical_phase
    state["next"] = canonical_next
    state["active_gate"] = canonical_gate

    marker = state.get("_p6_state_normalization")
    if isinstance(marker, dict):
        marker["corrected_phase"] = canonical_phase
        marker["corrected_next"] = canonical_next
        marker["corrected_active_gate"] = canonical_gate


def sync_conditional_p5_gate_states(
    *,
    state_doc: dict,
    gate_evaluators: GateEvaluators | None = None,
) -> None:
    """Synchronize conditional P5 gate states from evaluator SSOT.

    Pending-only policy: write only when a gate is currently pending so prior
    non-pending operator decisions are preserved.

    Modifies state_doc in place.
    
    Args:
        state_doc: The session state document.
        gate_evaluators: Injectable gate evaluators (optional, uses pure defaults).
    """
    if gate_evaluators is None:
        gate_evaluators = GateEvaluators(
            evaluate_p53=evaluate_p53_test_quality,
            evaluate_p54=evaluate_p54_business_rules,
            evaluate_p55=evaluate_p55_technical_debt,
            evaluate_p56=evaluate_p56_rollback_safety,
            phase_1_5_executed=phase_1_5_executed,
        )
    
    state_obj = state_doc.get("SESSION_STATE")
    state = state_obj if isinstance(state_obj, dict) else state_doc

    canonical = normalize_to_canonical(state)
    gates = state.get("Gates")
    if not isinstance(gates, dict):
        return

    # --- P5.3 Test Quality ---
    p53_eval = gate_evaluators.evaluate_p53(session_state=state)
    if str(gates.get("P5.3-TestQuality", "")).strip().lower() == "pending":
        if p53_eval.status in {"pass", "pass-with-exceptions", "not-applicable"}:
            gates["P5.3-TestQuality"] = p53_eval.status

    # --- P5.4 Business Rules ---
    p54_eval = gate_evaluators.evaluate_p54(
        session_state=state,
        phase_1_5_executed=gate_evaluators.phase_1_5_executed(state),
    )
    current_p54 = str(gates.get("P5.4-BusinessRules", "")).strip().lower()
    if current_p54 in {"pending", "gap-detected"}:
        if p54_eval.status in {
            "compliant",
            "compliant-with-exceptions",
            "not-applicable",
            "gap-detected",
        }:
            gates["P5.4-BusinessRules"] = p54_eval.status
    if p54_eval.status not in {"compliant", "compliant-with-exceptions", "not-applicable", "gap-detected"}:
        phase5_completed = canonical.get("phase5_completed")
        if str(phase5_completed or "").strip().lower() in {"true", "1"} or phase5_completed is True:
            state["phase5_completed"] = False
            state["phase5_state"] = "phase5-in-progress"
            state["Phase5State"] = "phase5-in-progress"
            state["phase5_completion_status"] = "phase5-in-progress"

    # --- P5.5 Technical Debt ---
    p55_eval = gate_evaluators.evaluate_p55(session_state=state)
    if str(gates.get("P5.5-TechnicalDebt", "")).strip().lower() == "pending":
        if p55_eval.status in {"approved", "not-applicable", "rejected"}:
            gates["P5.5-TechnicalDebt"] = p55_eval.status

    # --- P5.6 Rollback Safety ---
    p56_eval = gate_evaluators.evaluate_p56(session_state=state)
    if str(gates.get("P5.6-RollbackSafety", "")).strip().lower() == "pending":
        if p56_eval.status in {"approved", "not-applicable", "rejected"}:
            gates["P5.6-RollbackSafety"] = p56_eval.status


def normalize_phase6_p5_state(
    *,
    state_doc: dict,
    events_path: Path | None = None,
    clock: Callable[[], str] | None = None,
    audit_sink: Callable[[Path, dict], None] | None = None,
    gate_constants: GateConstants | None = None,
    gate_evaluators: GateEvaluators | None = None,
) -> None:
    """Detect and correct inconsistent Phase 6 / P5 gate state (fail-closed).

    If ``phase=6`` but one or more P5 gates are still in a non-terminal
    status, this function **resets** the document to a consistent P5 state
    rather than silently papering over the inconsistency.

    Fail-closed reset writes:
    - ``phase6_state = "phase5_in_progress"``
    - ``implementation_review_complete = false``
    - ``workflow_complete`` / ``WorkflowComplete`` removed
    - ``active_gate`` set to the first open P5 gate

    A warning marker is written to state_doc for auditability.
    The entrypoint should persist audit events if needed.

    Modifies state_doc in place.
    
    Args:
        state_doc: The session state document.
        events_path: Path for audit events (optional).
        clock: Clock function for timestamps (optional).
        audit_sink: Audit event sink (optional). If events_path is provided but
            audit_sink is not, uses a simple default that appends JSON lines.
        gate_constants: Injectable gate constants (optional, uses defaults for tests).
        gate_evaluators: Injectable gate evaluators (optional, uses defaults for tests).
    """
    if audit_sink is None and events_path is not None:
        import json

        def _default_audit_sink(path: Path, row: dict) -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=True) + "\n")

        audit_sink = _default_audit_sink

    if gate_constants is None:
        gate_constants = GateConstants(
            priority_order=P5_GATE_PRIORITY_ORDER,
            terminal_values=P5_GATE_TERMINAL_VALUES,
            reason_code_for_gate=reason_code_for_gate,
        )
    
    if gate_evaluators is None:
        gate_evaluators = GateEvaluators(
            evaluate_p53=evaluate_p53_test_quality,
            evaluate_p54=evaluate_p54_business_rules,
            evaluate_p55=evaluate_p55_technical_debt,
            evaluate_p56=evaluate_p56_rollback_safety,
            phase_1_5_executed=phase_1_5_executed,
        )

    state_obj = state_doc.get("SESSION_STATE")
    state = state_obj if isinstance(state_obj, dict) else state_doc

    canonical = normalize_to_canonical(state)

    phase_text = str(canonical.get("phase") or "").strip()
    if not phase_text.startswith("6"):
        return

    gates = state.get("Gates")
    if not isinstance(gates, dict):
        gates = {}
        state["Gates"] = gates

    # Walk the canonical gate priority order from gate_evaluator (SSOT).
    # Only gates that *exist but are not terminal* are considered open.
    # Absent gates are skipped — they may be conditionally not-applicable.
    open_gates: list[str] = []
    for gate_key in gate_constants.priority_order:
        terminal_values = gate_constants.terminal_values.get(gate_key, ())
        current = gates.get(gate_key)
        if current is None:
            continue
        if current not in terminal_values:
            open_gates.append(gate_key)

    # Fail-closed: even with stale terminal gate states, force-open P5.4 when
    # the evaluator reports non-compliant business-rules validation.
    active_gate_text = str(canonical.get("active_gate") or "").strip().lower()
    if gate_evaluators.phase_1_5_executed(state) and active_gate_text == "rework clarification gate":
        p54_eval = gate_evaluators.evaluate_p54(
            session_state=state,
            phase_1_5_executed=True,
        )
        if p54_eval and p54_eval.status in {"gap-detected", "pending", "invalid-rules-detected"}:
            if "P5.4-BusinessRules" not in open_gates:
                open_gates.append("P5.4-BusinessRules")
                _order = {gate: idx for idx, gate in enumerate(gate_constants.priority_order)}
                open_gates.sort(key=lambda gate: _order.get(gate, 999))

    if not open_gates:
        _normalize_phase6_completion_flags(state, canonical)
        return

    first_open = open_gates[0]
    blocking_reason_code = gate_constants.reason_code_for_gate(first_open)

    corrected_phase, corrected_next, corrected_gate = GATE_TO_PHASE_NEXT.get(
        first_open,
        ("5-ArchitectureReview", "5", "Architecture Review Gate"),
    )

    original_phase = str(canonical.get("phase") or "")
    original_next = str(canonical.get("next") or canonical.get("next_action") or "")

    # ── Fail-closed reset: bring the document back to a P5-consistent
    #    snapshot so no mixed Phase-6 / open-P5 state is visible.  ──
    state["phase"] = corrected_phase
    state["next"] = corrected_next
    state["phase6_state"] = ""
    state["implementation_review_complete"] = False
    state["phase5_completed"] = False
    state["phase5_state"] = "phase5-in-progress"
    state["Phase5State"] = "phase5-in-progress"
    state["phase5_completion_status"] = "phase5-in-progress"
    state.pop("workflow_complete", None)
    state.pop("WorkflowComplete", None)
    state["active_gate"] = corrected_gate
    state["next_gate_condition"] = (
        f"Phase 6 promotion blocked: {blocking_reason_code}. "
        f"Complete {corrected_gate} and run /continue."
    )

    # Also clean up the ImplementationReview block to prevent stale
    # Phase-6 iteration fields from leaking into the reset snapshot.
    review_block = state.get("ImplementationReview")
    if isinstance(review_block, dict):
        review_block["implementation_review_complete"] = False

    # Write the warning marker for auditability (not an admin-alert).
    state["_p6_state_normalization"] = {
        "open_gates": open_gates,
        "first_open_gate": first_open,
        "reason": "WARN-P6-STATE-INCONSISTENCY",
        "blocking_reason_code": blocking_reason_code,
        "action": "fail-closed-reset-to-p5",
        "original_phase": original_phase,
        "original_next": original_next,
        "corrected_phase": corrected_phase,
        "corrected_next": corrected_next,
        "corrected_active_gate": corrected_gate,
    }

    if events_path is not None and audit_sink is not None:
        now = clock() if clock else "unknown"
        event = {
            "schema": "opencode.state-normalization.v1",
            "event": "P6_STATE_NORMALIZED",
            "observed_at": now,
            "reason_code": "WARN-P6-STATE-INCONSISTENCY",
            "blocking_reason_code": blocking_reason_code,
            "first_open_gate": first_open,
            "open_gates": open_gates,
            "original_phase": original_phase,
            "original_next": original_next,
            "corrected_phase": corrected_phase,
            "corrected_next": corrected_next,
            "corrected_active_gate": corrected_gate,
        }
        audit_sink(events_path, event)


def _normalize_phase6_completion_flags(state: dict, canonical: dict) -> None:
    """Normalize Phase 6 completion flags when iterations reach max.

    When phase6_review_iterations >= phase6_max_review_iterations and all P5 gates
    are terminal, the internal review loop is considered complete. This function
    normalizes stale implementation_review_complete and phase6_state values.

    Only normalizes when:
    1. The completion_status is stale (e.g., "phase6-in-progress")
    2. The state doesn't have LLM verdict data indicating the loop made a blocking decision

    Modifies state in place.
    """
    from governance_runtime.shared.number_utils import coerce_int

    phase6_iterations = coerce_int(
        canonical.get("phase6_review_iterations")
        or state.get("phase6_review_iterations")
        or state.get("phase6ReviewIterations")
        or 0
    )
    phase6_max = coerce_int(
        canonical.get("phase6_max_review_iterations")
        or state.get("phase6_max_review_iterations")
        or state.get("phase6MaxReviewIterations")
        or 3
    )

    if phase6_iterations >= phase6_max:
        review_block = state.get("ImplementationReview")
        current_completion_status = None
        if isinstance(review_block, dict):
            current_completion_status = review_block.get("completion_status", "")

        stale_completion_statuses = {"phase6-in-progress", "in-progress", "pending", ""}
        is_stale = current_completion_status in stale_completion_statuses

        if not is_stale:
            return

        llm_verdict = None
        if isinstance(review_block, dict):
            llm_verdict = review_block.get("llm_review_verdict", "")

        blocked_verdicts = {"changes_requested", "reject"}
        if llm_verdict in blocked_verdicts:
            return

        if not state.get("implementation_review_complete", False):
            state["implementation_review_complete"] = True
            if isinstance(review_block, dict):
                review_block["implementation_review_complete"] = True

        if state.get("phase6_state") not in ("6.complete", "completed", "phase6_completed"):
            state["phase6_state"] = "6.complete"
            if isinstance(review_block, dict):
                review_block["completion_status"] = "phase6-completed"
