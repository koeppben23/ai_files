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
from typing import Any, Callable, Mapping


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
    from governance_runtime.shared.string_utils import safe_str as _safe_str

    state_obj = state_doc.get("SESSION_STATE")
    state = state_obj if isinstance(state_obj, dict) else state_doc

    phase_text = str(state.get("Phase") or state.get("phase") or "").strip()
    if phase_text != "5-ArchitectureReview":
        return

    next_token = str(state.get("Next") or state.get("next") or "").strip()
    active_gate = str(state.get("active_gate") or "").strip().lower()
    ngc = str(state.get("next_gate_condition") or "").strip().upper()

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
    state["Phase"] = canonical_phase
    state["phase"] = canonical_phase
    state["Next"] = canonical_next
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
    gate_evaluators: GateEvaluators,
) -> None:
    """Synchronize conditional P5 gate states from evaluator SSOT.

    Pending-only policy: write only when a gate is currently pending so prior
    non-pending operator decisions are preserved.

    Modifies state_doc in place.
    
    Args:
        state_doc: The session state document.
        gate_evaluators: Injectable gate evaluators (required).
    """
    state_obj = state_doc.get("SESSION_STATE")
    state = state_obj if isinstance(state_obj, dict) else state_doc
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
    if str(gates.get("P5.4-BusinessRules", "")).strip().lower() == "pending":
        if p54_eval.status in {
            "compliant",
            "compliant-with-exceptions",
            "not-applicable",
            "gap-detected",
        }:
            gates["P5.4-BusinessRules"] = p54_eval.status
    if p54_eval.status not in {"compliant", "compliant-with-exceptions", "not-applicable", "gap-detected"}:
        if str(state.get("phase5_completed") or "").strip().lower() in {"true", "1"} or state.get("phase5_completed") is True:
            state["phase5_completed"] = False
            state["phase5_state"] = "phase5-in-progress"
            state["Phase5State"] = "phase5-in-progress"
            state["phase5_completion_status"] = "phase5-in-progress"

    p55_eval = gate_evaluators.evaluate_p55(session_state=state)
    if str(gates.get("P5.5-TechnicalDebt", "")).strip().lower() == "pending":
        if p55_eval.status in {"approved", "not-applicable", "rejected"}:
            gates["P5.5-TechnicalDebt"] = p55_eval.status

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
    gate_constants: GateConstants,
    gate_evaluators: GateEvaluators,
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
        audit_sink: Audit event sink (optional).
        gate_constants: Injectable gate constants (required).
        gate_evaluators: Injectable gate evaluators (required).
    """

    state_obj = state_doc.get("SESSION_STATE")
    state = state_obj if isinstance(state_obj, dict) else state_doc

    phase_raw = state.get("Phase") or state.get("phase") or ""
    phase_text = str(phase_raw).strip()
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
    active_gate_text = str(state.get("active_gate") or "").strip().lower()
    if gate_evaluators.phase_1_5_executed(state) and active_gate_text == "rework clarification gate":
        p54_eval = gate_evaluators.evaluate_p54(
            session_state=state,
            phase_1_5_executed=True,
        )
        if p54_eval and p54_eval.status in {"gap-detected", "pending"}:
            if "P5.4-BusinessRules" not in open_gates:
                open_gates.append("P5.4-BusinessRules")
                _order = {gate: idx for idx, gate in enumerate(gate_constants.priority_order)}
                open_gates.sort(key=lambda gate: _order.get(gate, 999))

    if not open_gates:
        return

    first_open = open_gates[0]
    blocking_reason_code = gate_constants.reason_code_for_gate(first_open)

    gate_to_phase_next: dict[str, tuple[str, str, str]] = {
        "P5.3-TestQuality": ("5.3-TestQuality", "5.3", "Test Quality Gate"),
        "P5.4-BusinessRules": ("5.4-BusinessRules", "5.4", "Business Rules Validation"),
        "P5.5-TechnicalDebt": ("5.5-TechnicalDebt", "5.5", "Technical Debt Review"),
        "P5.6-RollbackSafety": ("5.6-RollbackSafety", "5.6", "Rollback Safety Review"),
        "P5-Architecture": ("5-ArchitectureReview", "5", "Architecture Review Gate"),
    }
    corrected_phase, corrected_next, corrected_gate = gate_to_phase_next.get(
        first_open,
        ("5-ArchitectureReview", "5", "Architecture Review Gate"),
    )

    original_phase = str(state.get("Phase") or state.get("phase") or "")
    original_next = str(state.get("Next") or state.get("next") or "")

    # ── Fail-closed reset: bring the document back to a P5-consistent
    #    snapshot so no mixed Phase-6 / open-P5 state is visible.  ──
    state["Phase"] = corrected_phase
    state["phase"] = corrected_phase
    state["Next"] = corrected_next
    state["next"] = corrected_next
    state["phase6_state"] = "phase5_in_progress"
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
