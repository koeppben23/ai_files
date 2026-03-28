from __future__ import annotations

import json
from pathlib import Path

from governance_runtime.entrypoints import review_decision_persist as review_decision
from governance_runtime.entrypoints.session_reader import _resolve_next_action_line
from governance_runtime.shared.next_action import NextAction, render_next_action_line


def test_next_action_to_dict_omits_optional_command() -> None:
    action = NextAction(code="REVIEW_DECISION", text="Submit review decision.", command=None)
    payload = action.to_dict()
    assert payload == {
        "next_action_code": "REVIEW_DECISION",
        "next_action": "Submit review decision.",
    }
    assert "next_action_command" not in payload


def test_render_next_action_line_prefers_command() -> None:
    payload = {
        "next_action": "Describe requested changes in chat.",
        "next_action_command": "/continue",
    }
    assert render_next_action_line(payload) == "Next action: /continue"


def test_session_reader_does_not_derive_next_action_without_fields() -> None:
    snapshot = {
        "status": "OK",
        "phase": "6-PostFlight",
        "active_gate": "Workflow Complete",
        "next_gate_condition": "Workflow approved.",
    }
    assert _resolve_next_action_line(snapshot) == ""


def test_review_decision_main_quiet_mode_prints_json_only(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        review_decision,
        "_resolve_active_session_path",
        lambda: (Path("/tmp/SESSION_STATE.json"), Path("/tmp/events.jsonl")),
    )
    monkeypatch.setattr(
        review_decision,
        "apply_review_decision",
        lambda **_kwargs: {
            "status": "ok",
            "next_action_code": "IMPLEMENT_START",
            "next_action": "Start implementation.",
            "next_action_command": "/implement",
        },
    )

    rc = review_decision.main(["--decision", "approve", "--quiet"])
    assert rc == 0
    lines = [line for line in capsys.readouterr().out.strip().splitlines() if line]
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["next_action_command"] == "/implement"


def test_review_decision_main_normal_mode_renders_next_action_line(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        review_decision,
        "_resolve_active_session_path",
        lambda: (Path("/tmp/SESSION_STATE.json"), Path("/tmp/events.jsonl")),
    )
    monkeypatch.setattr(
        review_decision,
        "apply_review_decision",
        lambda **_kwargs: {
            "status": "ok",
            "next_action_code": "IMPLEMENT_START",
            "next_action": "Start implementation.",
            "next_action_command": "/implement",
        },
    )

    rc = review_decision.main(["--decision", "approve"])
    assert rc == 0
    lines = [line for line in capsys.readouterr().out.strip().splitlines() if line]
    assert len(lines) == 2
    assert lines[1] == "Next action: /implement"


def test_blocked_payload_without_safe_command_omits_next_action_command(tmp_path: Path) -> None:
    missing_session = tmp_path / "missing.json"
    payload = review_decision.apply_review_decision(
        decision="invalid-decision",
        session_path=missing_session,
        events_path=None,
    )
    assert payload["status"] == "error"
    assert payload["next_action_code"] == "REVIEW_DECISION"
    assert payload["next_action"] == "Submit review decision."
    assert "next_action_command" not in payload
