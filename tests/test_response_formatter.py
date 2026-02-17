from __future__ import annotations

import json

from governance.render.response_formatter import render_response, resolve_output_format


def _sample_payload() -> dict[str, object]:
    return {
        "mode": "STRICT",
        "status": "OK",
        "session_state": {
            "phase": "2",
            "effective_operating_mode": "ok",
            "active_gate.status": "OK",
            "active_gate.reason_code": "none",
        },
        "snapshot": {
            "confidence": "HIGH",
            "risk": "LOW",
            "scope": "repo",
        },
        "next_action": {
            "Type": "command",
            "Status": "OK",
            "Next": "continue",
            "Why": "phase advanced",
            "Command": "/continue",
        },
    }


def test_resolve_output_format_auto_prefers_markdown_when_interactive():
    assert resolve_output_format("auto", is_tty=True, markdown_supported=True) == "markdown"


def test_resolve_output_format_auto_prefers_json_when_non_tty():
    assert resolve_output_format("auto", is_tty=False, markdown_supported=True) == "json"


def test_render_response_markdown_uses_headings_and_code_fences():
    rendered = render_response(_sample_payload(), output_format="markdown")
    assert "# Governance Response (STRICT)" in rendered
    assert "## Next Action" in rendered
    assert "## Session State" in rendered
    assert "```json" in rendered


def test_render_response_plain_pretty_prints_multiline_blocks():
    rendered = render_response(_sample_payload(), output_format="plain")
    assert "next_action:" in rendered
    assert "session_state:" in rendered
    assert "{\n" in rendered
    assert '"status": "OK"' in rendered


def test_render_response_json_is_valid_and_pretty():
    rendered = render_response(_sample_payload(), output_format="json")
    payload = json.loads(rendered)
    assert payload["status"] == "OK"
    assert rendered.count("\n") > 3
