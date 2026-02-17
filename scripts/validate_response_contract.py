#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def _is_nonempty_string(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _phase_requires_ticket_input(phase_value: object) -> bool:
    """Return True only for Phase 4+ where ticket-goal input is valid."""

    if not isinstance(phase_value, str):
        return False
    phase = phase_value.strip()
    if not phase:
        return False
    match = re.match(r"^(\d+)", phase)
    if match is None:
        return False
    return int(match.group(1)) >= 4


def _contains_ticket_prompt(text: object) -> bool:
    if not isinstance(text, str):
        return False
    normalized = text.strip().lower()
    if not normalized:
        return False
    if "task/ticket" in normalized:
        return True
    if "ticket" in normalized:
        return True
    if "change request" in normalized:
        return True
    return False


def _normalize_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.strip().lower().split())


def _contains_scope_prompt(text: object) -> bool:
    normalized = _normalize_text(text)
    if not normalized:
        return False
    return (
        "working set" in normalized
        or "component scope" in normalized
        or "set scope" in normalized
        or "scope" in normalized
    )


def _extract_next_gate_condition(session: dict) -> str:
    for key in ("next_gate_condition", "NextGateCondition", "nextGateCondition", "Next"):
        value = session.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _extract_phase_token(value: object) -> str:
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


def _extract_phase(session: dict) -> str:
    for key in ("phase", "Phase"):
        token = _extract_phase_token(session.get(key))
        if token:
            return token
    return ""


def _phase_rank(phase_token: str) -> int:
    order = {
        "1": 10,
        "1.1": 11,
        "1.2": 12,
        "1.3": 13,
        "2": 20,
        "2.1": 21,
        "1.5": 22,
        "3A": 30,
        "3B-1": 31,
        "3B-2": 32,
        "4": 40,
        "5": 50,
        "5.3": 53,
        "5.4": 54,
        "5.5": 55,
        "5.6": 56,
        "6": 60,
    }
    return order.get(phase_token, -1)


def _extract_previous_phase_tokens(session: dict) -> tuple[str, ...]:
    tokens: list[str] = []
    for key in ("previous_phase", "PreviousPhase", "phase_previous", "from_phase"):
        token = _extract_phase_token(session.get(key))
        if token:
            tokens.append(token)

    history = session.get("phase_history")
    if isinstance(history, list):
        for entry in history:
            token = _extract_phase_token(entry)
            if token:
                tokens.append(token)
    return tuple(tokens)


def _contains_any(text: object, needles: tuple[str, ...]) -> bool:
    normalized = _normalize_text(text)
    if not normalized:
        return False
    return any(needle in normalized for needle in needles)


def _validate_phase_next_action_alignment(
    *,
    status: object,
    phase_token: str,
    next_text: object,
    why_text: object,
) -> list[str]:
    if not isinstance(status, str) or status.strip().lower() == "blocked":
        return []

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
        return []

    if _contains_any(next_text, required) or _contains_any(why_text, required):
        return []
    return [f"next_action must align with phase {phase_token} progression semantics"]


def validate(payload: dict) -> list[str]:
    errors: list[str] = []

    for key in ("status", "session_state", "next_action", "snapshot"):
        if key not in payload:
            errors.append(f"missing required top-level field: {key}")

    status = payload.get("status")
    if status not in {"normal", "degraded", "draft", "blocked"}:
        errors.append("status must be one of normal|degraded|draft|blocked")

    session = payload.get("session_state")
    if not isinstance(session, dict):
        errors.append("session_state must be an object")
        session = {}

    next_action = payload.get("next_action")
    if not isinstance(next_action, dict):
        errors.append("next_action must be an object")
        next_action = {}
    else:
        na_type = next_action.get("type")
        if na_type not in {"command", "reply_with_one_number", "manual_step"}:
            errors.append("next_action.type must be one of command|reply_with_one_number|manual_step")
        for key in ("Status", "Next", "Why", "Command"):
            if not _is_nonempty_string(next_action.get(key)):
                errors.append(f"next_action.{key} must be a non-empty string")
        if na_type == "command":
            if str(next_action.get("Command", "")).strip().lower() == "none":
                errors.append("next_action.Command must not be none when next_action.type=command")
        elif na_type in {"reply_with_one_number", "manual_step"}:
            if str(next_action.get("Command", "")).strip().lower() != "none":
                errors.append("next_action.Command must be none when next_action.type is reply_with_one_number|manual_step")

    phase_token = _extract_phase(session) if isinstance(session, dict) else ""

    if not _phase_requires_ticket_input(phase_token):
        next_text = next_action.get("Next") if isinstance(next_action, dict) else None
        why_text = next_action.get("Why") if isinstance(next_action, dict) else None
        if _contains_ticket_prompt(next_text) or _contains_ticket_prompt(why_text):
            errors.append("next_action must not request task/ticket input before phase 4")

    next_text = next_action.get("Next") if isinstance(next_action, dict) else None
    why_text = next_action.get("Why") if isinstance(next_action, dict) else None
    errors.extend(
        _validate_phase_next_action_alignment(
            status=status,
            phase_token=phase_token,
            next_text=next_text,
            why_text=why_text,
        )
    )

    next_gate_condition = _extract_next_gate_condition(session) if isinstance(session, dict) else ""
    if next_gate_condition:
        gate_lower = _normalize_text(next_gate_condition)
        if (
            ("working set" in gate_lower or "component scope" in gate_lower)
            and not (_contains_scope_prompt(next_text) or _contains_scope_prompt(why_text))
        ):
            errors.append("next_action must align with next_gate_condition scope/working-set requirements")

    previous_phase_tokens = _extract_previous_phase_tokens(session) if isinstance(session, dict) else ()
    if phase_token == "1.5":
        if previous_phase_tokens:
            immediate_prev = previous_phase_tokens[0]
            allowed_prev = {"2.1", "3A", "3B-1", "3B-2", "4", "5", "5.3", "5.4", "5.5", "5.6", "6"}
            if immediate_prev not in allowed_prev:
                errors.append("phase 1.5 may only follow phase 2.1 or explicit later-phase reopen")

        phase_history = session.get("phase_history") if isinstance(session, dict) else None
        if isinstance(phase_history, list):
            history_tokens = [_extract_phase_token(value) for value in phase_history]
            history_tokens = [token for token in history_tokens if token]
            if "1.5" in history_tokens and "2.1" in history_tokens:
                if history_tokens.index("1.5") < history_tokens.index("2.1"):
                    errors.append("phase history invalid: 1.5 cannot occur before 2.1")

    snapshot = payload.get("snapshot")
    if not isinstance(snapshot, dict):
        errors.append("snapshot must be an object")
    else:
        if not _is_nonempty_string(snapshot.get("Confidence")):
            errors.append("snapshot.Confidence must be present")
        if snapshot.get("Risk") not in {"LOW", "MEDIUM", "HIGH"}:
            errors.append("snapshot.Risk must be LOW|MEDIUM|HIGH")
        if not _is_nonempty_string(snapshot.get("Scope")):
            errors.append("snapshot.Scope must be present")

    loaded = session.get("LoadedRulebooks") if isinstance(session, dict) else {}
    evidence = session.get("RulebookLoadEvidence") if isinstance(session, dict) else {}
    if isinstance(loaded, dict):
        populated = False
        for key in ("core", "profile", "templates"):
            value = loaded.get(key)
            if isinstance(value, str) and value.strip():
                populated = True
        addons = loaded.get("addons")
        if isinstance(addons, dict) and any(isinstance(v, str) and v.strip() for v in addons.values()):
            populated = True
        if populated:
            if not isinstance(evidence, dict) or len(evidence) == 0:
                errors.append("RulebookLoadEvidence must be present when LoadedRulebooks contains loaded entries")

    if status == "blocked":
        reason = payload.get("reason_payload")
        quick = payload.get("quick_fix_commands")
        if not isinstance(reason, dict):
            errors.append("blocked status requires reason_payload object")
            reason = {}
        else:
            if reason.get("status") != "blocked":
                errors.append("reason_payload.status must be blocked")
            reason_code = reason.get("reason_code")
            if not (isinstance(reason_code, str) and reason_code.startswith("BLOCKED-")):
                errors.append("reason_payload.reason_code must start with BLOCKED-")
            if not isinstance(reason.get("missing_evidence"), list):
                errors.append("reason_payload.missing_evidence must be an array")
            recovery = reason.get("recovery_steps")
            if not isinstance(recovery, list) or len(recovery) > 3:
                errors.append("reason_payload.recovery_steps must be an array with max 3 entries")
            if not _is_nonempty_string(reason.get("next_command")):
                errors.append("reason_payload.next_command must be a non-empty string")

        if not isinstance(quick, list) or not (1 <= len(quick) <= 3) or not all(isinstance(x, str) for x in quick):
            errors.append("blocked status requires quick_fix_commands array with 1-3 string entries")
            quick = []

        cmd = next_action.get("Command") if isinstance(next_action, dict) else None
        next_command = reason.get("next_command") if isinstance(reason, dict) else None
        q0 = quick[0] if quick else None
        if isinstance(cmd, str) and isinstance(next_command, str) and q0 is not None:
            if not (cmd == next_command == q0):
                errors.append("command coherence violated: next_action.Command, reason_payload.next_command, and quick_fix_commands[0] must match")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate canonical governance response envelope payload.")
    parser.add_argument("--input", required=True, type=Path, help="Path to response envelope JSON payload.")
    args = parser.parse_args()

    payload = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        print("FAIL: payload root must be JSON object")
        return 1

    errors = validate(payload)
    if errors:
        print("FAIL: response contract violations")
        for error in errors:
            print(f"- {error}")
        return 1

    print("OK: response contract valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
