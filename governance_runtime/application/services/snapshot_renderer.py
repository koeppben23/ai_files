"""Snapshot rendering layer for governance session state.

This module provides functions to render governance session snapshots
into human-readable text formats for CLI output.

Two main rendering modes:
- format_snapshot: Debug/diagnostic key-value output
- format_guided_snapshot: Guided operator-facing output with sections

The rendering functions are stateless - they take a snapshot dict and
return formatted strings without modifying the input.
"""

from __future__ import annotations

from typing import Any, Mapping

from governance_runtime.infrastructure.number_utils import coerce_int as _coerce_int
from governance_runtime.infrastructure.number_utils import quote_if_needed as _quote_if_needed
from governance_runtime.infrastructure.text_utils import format_list as _format_list
from governance_runtime.infrastructure.text_utils import safe_str as _safe_str

# Schema constant
SNAPSHOT_SCHEMA = "governance-session-snapshot.v1"

# Gate purpose mappings
_GATE_PURPOSES: dict[str, str] = {
    "ticket input gate": "Capture the concrete task before planning can proceed.",
    "plan record preparation gate": "Persist the approved plan record before architecture review.",
    "architecture review gate": "Run and complete internal architecture self-review.",
    "business rules validation": "Validate business-rule compliance before implementation flow.",
    "implementation internal review": "Run deterministic internal implementation review iterations.",
    "evidence presentation gate": "Present the full governance review package for final decision.",
    "workflow complete": "Governance approval is complete; implementation can start.",
    "implementation execution in progress": "Implementation work is actively running.",
    "implementation self review": "Inspect implementation quality and derive findings.",
    "implementation revision": "Apply revisions from implementation review findings.",
    "implementation verification": "Verify the revised implementation with checks.",
    "implementation presentation gate": "Present implementation evidence for final implementation decision.",
    "implementation blocked": "Execution is blocked by hard findings that must be resolved.",
    "implementation rework clarification gate": "Clarify requested implementation changes before rerun.",
    "implementation accepted": "Implementation outcome is accepted.",
    "rework clarification gate": "Clarify requested governance changes before rerouting.",
}


def _display_phase(phase: object) -> str:
    """Convert phase token to display name."""
    token = str(phase or "").strip()
    lower = token.lower()
    if lower == "4":
        return "Phase 4 - Ticket Intake"
    if lower.startswith("5.4"):
        return "Phase 5 - Business Rules"
    if lower.startswith("5.5"):
        return "Phase 5 - Technical Debt"
    if lower.startswith("5.6"):
        return "Phase 5 - Rollback Safety"
    if lower.startswith("5"):
        return "Phase 5 - Architecture Review"
    if lower.startswith("6"):
        return "Phase 6 - Post Flight"
    if lower.startswith("1"):
        return "Phase 1 - Bootstrap"
    return token or "unknown"


def _section(lines: list[str], title: str) -> None:
    """Add a section header to the output lines."""
    if lines:
        lines.append("")
    lines.append(title)


def _append_list(lines: list[str], prefix: str, items: object) -> None:
    """Append a list item to the output lines."""
    if not isinstance(items, list) or not items:
        lines.append(f"- {prefix}: none")
        return
    lines.append(f"- {prefix}:")
    for item in items:
        lines.append(f"  - {str(item)}")


def _render_current_state(snapshot: dict) -> list[str]:
    """Render the current state section."""
    phase = _display_phase(snapshot.get("phase"))
    gate = str(snapshot.get("active_gate") or "none")
    purpose = _GATE_PURPOSES.get(gate.strip().lower(), "Guide the operator to the next deterministic governance step.")
    return [
        "Current state",
        f"- Phase: {phase}",
        f"- Active gate: {gate}",
        f"- Gate purpose: {purpose}",
    ]


def _render_what_now(snapshot: dict) -> list[str]:
    """Render the 'what this means now' section."""
    condition = str(snapshot.get("next_gate_condition") or "none")
    return [
        "What this means now",
        f"- {condition}",
    ]


def _render_presented_review_content(snapshot: dict) -> list[str]:
    """Render the presented review content section."""
    gate = str(snapshot.get("active_gate") or "").strip().lower()
    lines: list[str] = ["Presented review content"]
    if gate == "evidence presentation gate":
        lines.append(f"- Review object: {snapshot.get('review_package_review_object') or 'none'}")
        lines.append(f"- Ticket: {snapshot.get('review_package_ticket') or 'none'}")
        lines.append("- Approved plan for review:")
        plan_body = str(snapshot.get("review_package_plan_body") or "none")
        if plan_body.strip() and plan_body.strip().lower() != "none":
            for raw in plan_body.splitlines():
                text = raw.rstrip()
                lines.append(f"  {text}" if text else "  ")
        else:
            lines.append("  none")
        lines.append(f"- Evidence summary: {snapshot.get('review_package_evidence_summary') or 'none'}")
        lines.append("- Decision semantics:")
        lines.append("  - approve: governance complete and implementation authorized")
        lines.append("  - changes_requested: enter rework clarification gate")
        lines.append("  - reject: return to phase 4 ticket input gate")
        return lines

    if gate == "implementation presentation gate":
        lines.append(f"- Implementation review object: {snapshot.get('implementation_package_review_object') or 'none'}")
        lines.append(f"- Approved plan reference: {snapshot.get('implementation_package_plan_reference') or 'none'}")
        _append_list(lines, "Changed files / artifact summary", snapshot.get("implementation_package_changed_files"))
        _append_list(lines, "Findings fixed", snapshot.get("implementation_package_findings_fixed"))
        _append_list(lines, "Findings open", snapshot.get("implementation_package_findings_open"))
        _append_list(lines, "Verification evidence", snapshot.get("implementation_package_checks"))
        lines.append(f"- Quality verdict: {snapshot.get('implementation_package_stability') or 'unknown'}")
        lines.append("- Decision semantics:")
        lines.append("  - approve: implementation accepted")
        lines.append("  - changes_requested: implementation rework clarification")
        lines.append("  - reject: implementation blocked")
        return lines

    lines.append("- No review presentation content is active in this gate.")
    return lines


def _render_execution_progress(snapshot: dict) -> list[str]:
    """Render the execution progress section."""
    lines = ["Execution progress"]
    gate = str(snapshot.get("active_gate") or "").strip().lower()
    if gate == "implementation internal review":
        lines.append(
            "- Internal review loop: "
            f"iteration={_coerce_int(snapshot.get('phase6_review_iterations'))}/"
            f"{_coerce_int(snapshot.get('phase6_max_review_iterations') or 3)}"
        )
        lines.append(f"- Revision delta: {snapshot.get('phase6_revision_delta') or 'changed'}")
        lines.append(f"- Decision availability: {snapshot.get('phase6_decision_availability') or 'not yet available'}")
        return lines

    if gate == "business rules validation":
        lines.append(f"- Business Rules Validation: {str(snapshot.get('p54_evaluated_status') or 'unknown').upper()}")
        lines.append(f"- Invalid rules detected: {int(snapshot.get('p54_invalid_rules') or 0)}")
        lines.append(f"- Dropped candidates: {int(snapshot.get('p54_dropped_candidates') or 0)}")
        lines.append(f"- Code candidates: {int(snapshot.get('p54_code_candidate_count') or 0)}")
        lines.append(f"- Code surfaces scanned: {int(snapshot.get('p54_code_surface_count') or 0)}")
        quality_codes = snapshot.get("p54_quality_reason_codes")
        if isinstance(quality_codes, list) and quality_codes:
            lines.append(f"- Reason codes: {', '.join(str(code) for code in quality_codes)}")
        return lines

    changed_files = snapshot.get("implementation_changed_files")
    if isinstance(changed_files, list) and changed_files:
        _append_list(lines, "Changed files", changed_files)
    else:
        lines.append("- No file-level execution evidence is available for this gate.")

    if "implementation_execution_summary" in snapshot:
        lines.append(f"- Execution summary: {snapshot.get('implementation_execution_summary')}")
    return lines


def _has_blocker(snapshot: dict) -> bool:
    """Check if the snapshot indicates a blocker."""
    status = str(snapshot.get("status") or "").strip().lower()
    if status in {"error", "blocked"}:
        return True
    gates_blocked = snapshot.get("gates_blocked")
    if isinstance(gates_blocked, list) and gates_blocked:
        return True
    next_condition = str(snapshot.get("next_gate_condition") or "").strip().lower()
    return "blocked" in next_condition or "error" in next_condition


def _render_blocker(snapshot: dict) -> list[str]:
    """Render the blocker section."""
    lines = ["Blocker"]
    lines.append(f"- Status: {snapshot.get('status') or 'unknown'}")
    lines.append(f"- Evidence: {snapshot.get('next_gate_condition') or 'No blocker detail provided.'}")
    phase = str(snapshot.get("phase") or "").strip().lower()
    if phase.startswith("5.4"):
        lines.append(
            f"- Business Rules Validation: {'FAILED' if str(snapshot.get('p54_evaluated_status')).strip().lower() != 'compliant' else 'PASSED'}"
        )
        lines.append(f"- Invalid rules detected: {int(snapshot.get('p54_invalid_rules') or 0)}")
        lines.append(f"- Dropped candidates: {int(snapshot.get('p54_dropped_candidates') or 0)}")
        reason = str(snapshot.get("p54_reason_code") or "none")
        lines.append(f"- Reason code: {reason}")
        quality_codes = snapshot.get("p54_quality_reason_codes")
        if isinstance(quality_codes, list) and quality_codes:
            lines.append(f"- Quality diagnostics: {', '.join(str(c) for c in quality_codes)}")
        lines.append(f"- Code extraction run: {'true' if bool(snapshot.get('p54_has_code_extraction')) else 'false'}")
        lines.append(
            f"- Code coverage sufficient: {'true' if bool(snapshot.get('p54_code_coverage_sufficient')) else 'false'}"
        )
        lines.append(f"- Code candidates: {int(snapshot.get('p54_code_candidate_count') or 0)}")
        lines.append(f"- Code surfaces scanned: {int(snapshot.get('p54_code_surface_count') or 0)}")
        missing_surfaces = snapshot.get("p54_missing_code_surfaces")
        if isinstance(missing_surfaces, list) and missing_surfaces:
            lines.append(f"- Missing code surfaces: {', '.join(str(s) for s in missing_surfaces)}")
    implementation_reasons = snapshot.get("implementation_reason_codes")
    if isinstance(implementation_reasons, list) and implementation_reasons:
        lines.append(
            f"- Implementation Validation: {'FAILED' if str(snapshot.get('active_gate')).strip().lower() == 'implementation blocked' else 'PASSED'}"
        )
        lines.append(f"- Executor invoked: {'true' if bool(snapshot.get('implementation_executor_invoked')) else 'false'}")
        lines.append(
            f"- Changed files: {len(snapshot.get('implementation_changed_files') or [])}"
        )
        lines.append(
            f"- Domain files changed: {len(snapshot.get('implementation_domain_changed_files') or [])}"
        )
        lines.append(f"- Reason codes: {', '.join(str(r) for r in implementation_reasons)}")
    gates_blocked = snapshot.get("gates_blocked")
    if isinstance(gates_blocked, list) and gates_blocked:
        lines.append(f"- Blocked gates: {', '.join(str(g) for g in gates_blocked)}")
    return lines


def _should_emit_continue_next_action(snapshot: dict) -> bool:
    """Determine whether to append 'Next action: run /continue.' to output.

    The rule is symmetric across all phases (Fix 1.3):
    1. Never emit when status is error/blocked.
    2. Never emit when the kernel signals a user-input gate (ticket intake,
       plan draft, rulebook load, etc.) — those require /ticket or manual action.
    3. Always emit when the condition explicitly contains '/continue'.
    4. Otherwise emit for any OK-status snapshot where the condition does
       not match a known user-input or blocking pattern.
    """
    status = str(snapshot.get("status", "")).strip().lower()
    if status in {"", "error", "blocked"}:
        return False

    next_condition = str(snapshot.get("next_gate_condition", "")).strip().lower()

    # Explicit /continue mention is an unconditional yes.
    if "/continue" in next_condition or "resume via /continue" in next_condition:
        return True

    # Evidence Presentation Gate directs user to /review-decision, not /continue.
    if "/review-decision" in next_condition:
        return False

    # Conditions that require user-provided input or are explicitly blocked.
    if any(
        token in next_condition
        for token in (
            "provide ticket/task",
            "collect ticket",
            "create and persist",
            "produce a plan draft",
            "load required rulebooks",
            "phase_blocked",
            "blocked",
            "wait for",
            "run bootstrap",
        )
    ):
        return False

    # For any other non-error, non-blocked state the user should /continue
    # to re-enter the kernel and advance.  This covers Phase 5 review loops,
    # Phase 6 implementation loops, and all intermediate stay-strategy phases
    # symmetrically without hardcoding specific phase/gate combinations.
    return True


# -- Blocking patterns that indicate the user should work in chat, not run /continue.
_GATE_WORK_PATTERNS: tuple[str, ...] = (
    "phase-transition-evidence-required",
    "phase-5-self-review-required",
    "implementation-review-pending",
)


def _resolve_next_action_line(snapshot: dict) -> str:
    """Determine the next action line for guided output."""
    from governance_runtime.engine.next_action_resolver import resolve_next_action

    render = resolve_next_action(snapshot)
    label = str(render.label or "").strip()
    phase = str(snapshot.get("phase") or "").strip().lower()
    gate = str(snapshot.get("active_gate") or "").strip().lower()
    if (phase.startswith("4") or gate == "ticket input gate") and "/review" not in label.lower():
        label = (
            "run /ticket with the ticket/task details. "
            "Alternative: run /review for read-only feedback (no state change)."
        )
    return f"Next action: {label}"


def format_snapshot(snapshot: dict) -> str:
    """Format debug/diagnostic key-value output (non-guided surface)."""
    lines = [f"# {SNAPSHOT_SCHEMA}"]
    for key, value in snapshot.items():
        if key == "schema":
            continue
        if isinstance(value, list):
            lines.append(f"{key}: {_format_list(value)}")
        else:
            lines.append(f"{key}: {_quote_if_needed(_safe_str(value))}")
    return "\n".join(lines) + "\n"


def format_guided_snapshot(snapshot: dict) -> str:
    """Format guided operator-facing output with sections."""
    lines: list[str] = []
    lines.extend(_render_current_state(snapshot))
    _section(lines, "What this means now")
    lines.append(f"- {str(snapshot.get('next_gate_condition') or 'none')}")

    gate = str(snapshot.get("active_gate") or "").strip().lower()
    if _has_blocker(snapshot):
        _section(lines, "Blocker")
        lines.extend(_render_blocker(snapshot)[1:])
    elif gate in {"evidence presentation gate", "implementation presentation gate"}:
        _section(lines, "Presented review content")
        lines.extend(_render_presented_review_content(snapshot)[1:])
    else:
        _section(lines, "Execution progress")
        lines.extend(_render_execution_progress(snapshot)[1:])

    action_line = _resolve_next_action_line(snapshot)
    lines.append("")
    lines.append(action_line)
    return "\n".join(lines).rstrip() + "\n"
