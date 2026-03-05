"""Deterministic formatter for governance response envelopes."""

from __future__ import annotations

import json
import sys
from typing import Any, Literal

from governance.application.dto.phase_next_action_contract import (
    extract_phase_token,
    phase_requires_ticket_input,
    validate_phase_next_action_contract,
)
from governance.domain.phase_state_machine import resolve_phase_output_policy
from governance.application.use_cases.target_path_helpers import classify_output_class


OutputFormat = Literal["auto", "markdown", "plain", "json"]
ResolvedFormat = Literal["markdown", "plain", "json"]


def resolve_output_format(
    requested: OutputFormat,
    *,
    is_tty: bool | None = None,
    markdown_supported: bool | None = None,
) -> ResolvedFormat:
    """Resolve the effective output format for rendering."""

    if requested != "auto":
        return requested

    tty = sys.stdout.isatty() if is_tty is None else is_tty
    if not tty:
        return "json"

    # Use plain as the deterministic interactive default so output remains
    # visually stable across hosts (including Windows terminals without markdown rendering).
    _ = markdown_supported
    return "plain"


def _pretty_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=True, sort_keys=True)


def _normalize_next_action(next_action: Any) -> dict[str, Any]:
    if not isinstance(next_action, dict):
        return {}

    normalized: dict[str, Any] = {}
    key_map = {
        "Status": "status",
        "Next": "next",
        "Why": "why",
        "Command": "command",
        "Type": "type",
    }
    for key, value in next_action.items():
        mapped = key_map.get(str(key), str(key))
        normalized[mapped] = value
    if "command" not in normalized and isinstance(next_action.get("command"), str):
        normalized["command"] = next_action["command"]
    return normalized


def _canonical_status(value: object) -> str:
    if not isinstance(value, str):
        return ""
    raw = value.strip().lower()
    mapping = {
        "ok": "normal",
        "warn": "degraded",
        "not_verified": "degraded",
        "blocked": "blocked",
        "normal": "normal",
        "degraded": "degraded",
        "draft": "draft",
    }
    return mapping.get(raw, raw)


def _enforce_phase_contract(payload: dict[str, Any]) -> None:
    session_state = payload.get("session_state")
    if not isinstance(session_state, dict):
        return
    next_action = _normalize_next_action(payload.get("next_action"))
    next_action_type = str(next_action.get("type", "")).strip().lower()
    next_text = next_action.get("next")
    why_text = next_action.get("why")
    if not isinstance(next_text, str):
        next_text = next_action.get("command")
    if not isinstance(why_text, str):
        why_text = ""

    phase_token = extract_phase_token(session_state.get("phase") or session_state.get("Phase"))
    if phase_token and not phase_requires_ticket_input(phase_token):
        if next_action_type and next_action_type != "command":
            raise ValueError(
                "invalid phase/next_action contract: next_action type must be command before phase 4"
            )

    errors = validate_phase_next_action_contract(
        status=_canonical_status(payload.get("status", "")),
        session_state=session_state,
        next_text=next_text,
        why_text=why_text,
    )
    if errors:
        raise ValueError("invalid phase/next_action contract: " + "; ".join(errors))

    # Defense-in-depth: validate output class against phase output policy (SSOT: phase_api.yaml)
    if phase_token:
        policy = resolve_phase_output_policy(phase_token)
        if policy is not None:
            requested_action = str(next_text or "").strip() if next_text else None
            output_class = classify_output_class(requested_action)
            if output_class != "unknown" and output_class in policy.forbidden_output_classes:
                raise ValueError(
                    f"defense-in-depth: output class '{output_class}' forbidden in phase {phase_token} "
                    f"(phase_api.yaml output_policy)"
                )


def _render_markdown(payload: dict[str, Any]) -> str:
    status = str(payload.get("status", "unknown"))
    mode = str(payload.get("mode", "unknown"))
    lines = [f"# Governance Response ({mode})", "", f"Status: `{status}`", ""]

    next_action = _normalize_next_action(payload.get("next_action"))
    session_state = payload.get("session_state")
    snapshot = payload.get("snapshot")

    lines.extend(
        [
            "## Next Action",
            "```json",
            _pretty_json(next_action),
            "```",
            "",
        ]
    )

    if isinstance(session_state, dict):
        lines.extend(
            [
                "## Session State",
                "```json",
                _pretty_json(session_state),
                "```",
                "",
            ]
        )

    if isinstance(snapshot, dict):
        lines.extend(
            [
                "## Snapshot",
                "```json",
                _pretty_json(snapshot),
                "```",
                "",
            ]
        )

    if isinstance(payload.get("reason_payload"), dict):
        lines.extend(
            [
                "## Reason Payload",
                "```json",
                _pretty_json(payload["reason_payload"]),
                "```",
                "",
            ]
        )

    if isinstance(payload.get("session_state_full"), dict):
        lines.extend(
            [
                "## Session State Full",
                "```json",
                _pretty_json(payload["session_state_full"]),
                "```",
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def _render_plain(payload: dict[str, Any]) -> str:
    status = str(payload.get("status", "unknown"))
    mode = str(payload.get("mode", "unknown"))
    blocks = [f"GOVERNANCE RESPONSE ({mode})", f"status: {status}"]

    next_action = _normalize_next_action(payload.get("next_action"))
    blocks.append("next_action:")
    blocks.append(_pretty_json(next_action))

    if isinstance(payload.get("session_state"), dict):
        blocks.append("session_state:")
        blocks.append(_pretty_json(payload["session_state"]))

    if isinstance(payload.get("snapshot"), dict):
        blocks.append("snapshot:")
        blocks.append(_pretty_json(payload["snapshot"]))

    if isinstance(payload.get("reason_payload"), dict):
        blocks.append("reason_payload:")
        blocks.append(_pretty_json(payload["reason_payload"]))

    if isinstance(payload.get("session_state_full"), dict):
        blocks.append("session_state_full:")
        blocks.append(_pretty_json(payload["session_state_full"]))

    return "\n\n".join(blocks).rstrip() + "\n"


def render_response(payload: dict[str, Any], *, output_format: OutputFormat = "auto") -> str:
    """Render response envelope using requested format contract."""

    _enforce_phase_contract(payload)

    resolved = resolve_output_format(output_format)
    if resolved == "json":
        return _pretty_json(payload) + "\n"
    if resolved == "markdown":
        return _render_markdown(payload)
    return _render_plain(payload)
