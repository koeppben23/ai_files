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
) -> dict[str, object]:
    """Build deterministic two-layer response with budget-guarded details."""

    safe_details = apply_token_budget(mode=mode, details=details or {})
    reason = reason_code.strip() or "none"
    command = next_command.strip() or "none"
    missing = tuple(sorted(item.strip() for item in (missing_items or ()) if item.strip()))
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
        "details": safe_details,
        "delta": build_delta_state(
            previous_state_hash=previous_state_hash,
            current_state_hash=current_state_hash,
        ),
    }
