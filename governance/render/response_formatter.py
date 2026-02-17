"""Deterministic formatter for governance response envelopes."""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Literal

from governance.engine.phase_next_action_contract import validate_phase_next_action_contract


OutputFormat = Literal["auto", "markdown", "plain", "json"]
ResolvedFormat = Literal["markdown", "plain", "json"]


def _supports_markdown_rendering() -> bool:
    """Return True when host is likely to present markdown readably."""

    forced = os.getenv("GOVERNANCE_MARKDOWN")
    if isinstance(forced, str):
        value = forced.strip().lower()
        if value in {"0", "false", "no", "off"}:
            return False
        if value in {"1", "true", "yes", "on"}:
            return True

    term = os.getenv("TERM", "").strip().lower()
    if term in {"", "dumb"} and not os.getenv("WT_SESSION"):
        return False
    return True


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
    _ = _supports_markdown_rendering() if markdown_supported is None else markdown_supported
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
    next_text = next_action.get("next")
    why_text = next_action.get("why")
    if not isinstance(next_text, str):
        next_text = next_action.get("command")
    if not isinstance(why_text, str):
        why_text = ""

    errors = validate_phase_next_action_contract(
        status=_canonical_status(payload.get("status", "")),
        session_state=session_state,
        next_text=next_text,
        why_text=why_text,
    )
    if errors:
        raise ValueError("invalid phase/next_action contract: " + "; ".join(errors))


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
