"""Two-layer output contract builder for deterministic governance responses."""

from __future__ import annotations

from typing import Sequence

from governance.render.delta_renderer import build_delta_state
from governance.render.token_guard import apply_token_budget


def build_two_layer_output(
    *,
    status: str,
    phase_gate: str,
    primary_action: str,
    mode: str = "standard",
    details: dict[str, str] | None = None,
    previous_state_hash: str = "",
    current_state_hash: str = "",
    phase: str = "unknown",
    active_gate: str = "unknown",
    phase_progress_bar: str = "[------] 0/6",
    reason_code: str = "none",
    next_command: str = "none",
    missing_items: Sequence[str] | None = None,
    previous_blockers: Sequence[str] | None = None,
    current_blockers: Sequence[str] | None = None,
    previous_stale_claims: Sequence[str] | None = None,
    current_stale_claims: Sequence[str] | None = None,
    transition_events: Sequence[dict[str, str]] | None = None,
) -> dict[str, object]:
    """Build deterministic two-layer response with budget-guarded details."""

    safe_details = apply_token_budget(mode=mode, details=details or {})
    reason = reason_code.strip() or "none"
    command = next_command.strip() or "none"
    missing = tuple(sorted(item.strip() for item in (missing_items or ()) if item.strip()))
    old_blockers = {item.strip() for item in (previous_blockers or ()) if item.strip()}
    new_blockers = {item.strip() for item in (current_blockers or ()) if item.strip()}
    old_stale = {item.strip() for item in (previous_stale_claims or ()) if item.strip()}
    new_stale = {item.strip() for item in (current_stale_claims or ()) if item.strip()}

    diagnostics_delta = {
        "new_blockers": tuple(sorted(new_blockers - old_blockers)),
        "resolved_blockers": tuple(sorted(old_blockers - new_blockers)),
        "new_stale_claims": tuple(sorted(new_stale - old_stale)),
        "resolved_stale_claims": tuple(sorted(old_stale - new_stale)),
    }

    timeline_source = list(transition_events or ())[-3:]
    timeline: list[dict[str, str]] = []
    for item in timeline_source:
        phase_value = str(item.get("phase", "unknown")).strip() if isinstance(item, dict) else "unknown"
        gate_value = str(item.get("active_gate", "unknown")).strip() if isinstance(item, dict) else "unknown"
        status_value = str(item.get("status", "unknown")).strip() if isinstance(item, dict) else "unknown"
        reason_value = str(item.get("reason_code", "none")).strip() if isinstance(item, dict) else "none"
        hash_value = str(item.get("snapshot_hash", "")).strip() if isinstance(item, dict) else ""
        timeline.append(
            {
                "phase_gate": f"{phase_value}|{gate_value}",
                "status": status_value,
                "reason_code": reason_value or "none",
                "snapshot_hash": hash_value,
            }
        )

    operator_view = {
        "PHASE_GATE": f"{phase.strip()} | {active_gate.strip()} | {phase_progress_bar.strip()}",
        "STATUS": status.strip(),
        "PRIMARY_REASON": reason,
        "NEXT_COMMAND": command,
    }
    reason_to_action = {
        "why": reason,
        "what_missing": missing,
        "next_command": command,
    }
    return {
        "header": {
            "status": status.strip(),
            "phase_gate": phase_gate.strip(),
            "primary_next_action": primary_action.strip(),
        },
        "operator_view": operator_view,
        "reason_to_action": reason_to_action,
        "diagnostics_delta": diagnostics_delta,
        "timeline": tuple(timeline),
        "details": safe_details,
        "delta": build_delta_state(
            previous_state_hash=previous_state_hash,
            current_state_hash=current_state_hash,
        ),
    }
