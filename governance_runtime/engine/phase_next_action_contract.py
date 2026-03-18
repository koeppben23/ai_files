"""Backward-compatible import surface for phase next-action contract."""

from governance.application.dto.phase_next_action_contract import (  # noqa: F401
    contains_any,
    contains_scope_prompt,
    contains_ticket_prompt,
    extract_phase_token,
    normalize_text,
    phase_requires_ticket_input,
    validate_phase_next_action_contract,
)
