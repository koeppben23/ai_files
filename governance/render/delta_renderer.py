"""Delta-state renderer for deterministic no-change signaling."""

from __future__ import annotations


def build_delta_state(*, previous_state_hash: str, current_state_hash: str) -> dict[str, object]:
    """Return deterministic delta metadata from two canonical state hashes."""

    unchanged = previous_state_hash.strip() == current_state_hash.strip() and bool(current_state_hash.strip())
    return {
        "state_unchanged": unchanged,
        "delta_mode": "no-delta" if unchanged else "delta-only",
    }
