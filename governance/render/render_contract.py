"""Two-layer output contract builder for deterministic governance responses."""

from __future__ import annotations

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
) -> dict[str, object]:
    """Build deterministic two-layer response with budget-guarded details."""

    safe_details = apply_token_budget(mode=mode, details=details or {})
    return {
        "header": {
            "status": status.strip(),
            "phase_gate": phase_gate.strip(),
            "primary_next_action": primary_action.strip(),
        },
        "details": safe_details,
        "delta": build_delta_state(
            previous_state_hash=previous_state_hash,
            current_state_hash=current_state_hash,
        ),
    }
