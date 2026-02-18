"""Deterministic phase/next-action alignment contract checks."""

from __future__ import annotations

import re


def normalize_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.strip().lower().split())


def contains_ticket_prompt(text: object) -> bool:
    normalized = normalize_text(text)
    if not normalized:
        return False
    return any(token in normalized for token in ("task/ticket", "ticket", "change request"))


def contains_scope_prompt(text: object) -> bool:
    normalized = normalize_text(text)
    if not normalized:
        return False
    return any(token in normalized for token in ("working set", "component scope", "set scope", "scope"))


def contains_any(text: object, needles: tuple[str, ...]) -> bool:
    normalized = normalize_text(text)
    if not normalized:
        return False
    return any(needle in normalized for needle in needles)


def extract_phase_token(value: object) -> str:
    if not isinstance(value, str):
        return ""
    raw = value.strip()
    if not raw:
        return ""
    normalized = raw.upper()
    patterns = (
        ("3B-2", r"^3B-2"),
        ("3B-1", r"^3B-1"),
        ("3A", r"^3A"),
        ("2.1", r"^2\.1"),
        ("1.5", r"^1\.5"),
        ("1.3", r"^1\.3"),
        ("1.2", r"^1\.2"),
        ("1.1", r"^1\.1"),
        ("6", r"^6(?:\b|-)"),
        ("5.6", r"^5\.6"),
        ("5.5", r"^5\.5"),
        ("5.4", r"^5\.4"),
        ("5.3", r"^5\.3"),
        ("5", r"^5(?:\b|-)"),
        ("4", r"^4(?:\b|-)"),
        ("2", r"^2(?:\b|-)"),
        ("1", r"^1(?:\b|-)"),
    )
    for token, pattern in patterns:
        if re.match(pattern, normalized):
            return token
    return ""


def phase_requires_ticket_input(phase_token: str) -> bool:
    match = re.match(r"^(\d+)", phase_token)
    if match is None:
        return False
    return int(match.group(1)) >= 4


def _extract_phase(session_state: dict[str, object]) -> str:
    for key in ("phase", "Phase"):
        token = extract_phase_token(session_state.get(key))
        if token:
            return token
    return ""


def _extract_previous_phase_tokens(session_state: dict[str, object]) -> tuple[str, ...]:
    tokens: list[str] = []
    for key in ("previous_phase", "PreviousPhase", "phase_previous", "from_phase"):
        token = extract_phase_token(session_state.get(key))
        if token:
            tokens.append(token)

    history = session_state.get("phase_history")
    if isinstance(history, list):
        for entry in history:
            token = extract_phase_token(entry)
            if token:
                tokens.append(token)
    return tuple(tokens)


def _extract_next_gate_condition(session_state: dict[str, object]) -> str:
    for key in ("next_gate_condition", "NextGateCondition", "nextGateCondition", "Next"):
        value = session_state.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _validate_phase_progression_semantics(phase_token: str, next_text: object, why_text: object) -> tuple[str, ...]:
    expectations: dict[str, tuple[str, ...]] = {
        "2": ("discovery", "decision pack", "2.1", "working set", "component scope", "scope"),
        "2.1": ("1.5", "business rules", "decision", "3a", "api", "routing", "scope"),
        "1.5": ("3a", "api", "routing", "phase 4", "business rules"),
        "3A": ("3b-1", "api logical validation", "3b"),
        "3B-1": ("3b-2", "contract validation", "phase 3b-2"),
        "3B-2": ("phase 4", "planning", "implement"),
    }
    required = expectations.get(phase_token)
    if not required:
        return ()
    if contains_any(next_text, required) or contains_any(why_text, required):
        return ()
    return (f"next_action must align with phase {phase_token} progression semantics",)


def validate_phase_next_action_contract(
    *,
    status: str,
    session_state: dict[str, object],
    next_text: object,
    why_text: object,
) -> tuple[str, ...]:
    errors: list[str] = []
    phase_token = _extract_phase(session_state)

    if status.strip().lower() != "blocked":
        if not phase_requires_ticket_input(phase_token):
            if contains_ticket_prompt(next_text) or contains_ticket_prompt(why_text):
                errors.append("next_action must not request task/ticket input before phase 4")

        errors.extend(_validate_phase_progression_semantics(phase_token, next_text, why_text))

    next_gate_condition = _extract_next_gate_condition(session_state)
    gate_lower = normalize_text(next_gate_condition)
    if gate_lower and ("working set" in gate_lower or "component scope" in gate_lower):
        if not (contains_scope_prompt(next_text) or contains_scope_prompt(why_text)):
            errors.append("next_action must align with next_gate_condition scope/working-set requirements")

    previous_phase_tokens = _extract_previous_phase_tokens(session_state)
    if phase_token == "1.5":
        if previous_phase_tokens:
            immediate_prev = previous_phase_tokens[0]
            allowed_prev = {"2.1", "3A", "3B-1", "3B-2", "4", "5", "5.3", "5.4", "5.5", "5.6", "6"}
            if immediate_prev not in allowed_prev:
                errors.append("phase 1.5 may only follow phase 2.1 or explicit later-phase reopen")

        phase_history = session_state.get("phase_history")
        if isinstance(phase_history, list):
            history_tokens = [extract_phase_token(value) for value in phase_history]
            history_tokens = [token for token in history_tokens if token]
            if "1.5" in history_tokens and "2.1" in history_tokens:
                if history_tokens.index("1.5") < history_tokens.index("2.1"):
                    errors.append("phase history invalid: 1.5 cannot occur before 2.1")

    return tuple(errors)
