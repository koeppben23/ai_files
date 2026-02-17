from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_render_response_envelope_script_markdown_output(tmp_path: Path):
    payload = {
        "mode": "STRICT",
        "status": "OK",
        "session_state": {"phase": "2", "activation_hash": "abc"},
        "next_action": {
            "Status": "OK",
            "Next": "Set working set and component scope",
            "Why": "Phase 2 exits through scoped routing",
            "Command": "set working set and component scope",
        },
        "snapshot": {"Confidence": "HIGH", "Risk": "LOW", "Scope": "repo"},
    }
    input_file = tmp_path / "payload.json"
    input_file.write_text(json.dumps(payload), encoding="utf-8")

    script = Path(__file__).resolve().parents[1] / "scripts" / "render_response_envelope.py"
    result = subprocess.run(
        [sys.executable, str(script), "--input", str(input_file), "--format", "markdown", "--output-mode", "STRICT"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "# Governance Response (STRICT)" in result.stdout
    assert "## Session State" in result.stdout


def test_render_response_envelope_script_mode_mismatch_fails(tmp_path: Path):
    payload = {
        "mode": "COMPAT",
        "status": "BLOCKED",
        "next_action": {"Status": "BLOCKED", "Next": "fix", "Why": "blocked", "Command": "none"},
    }
    input_file = tmp_path / "payload.json"
    input_file.write_text(json.dumps(payload), encoding="utf-8")

    script = Path(__file__).resolve().parents[1] / "scripts" / "render_response_envelope.py"
    result = subprocess.run(
        [sys.executable, str(script), "--input", str(input_file), "--output-mode", "STRICT"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "output mode mismatch" in result.stdout


def test_render_response_envelope_script_rejects_phase_contract_mismatch(tmp_path: Path):
    payload = {
        "mode": "STRICT",
        "status": "OK",
        "session_state": {"phase": "2.1-DecisionPack"},
        "next_action": {
            "Status": "WARN",
            "Next": "Provide the ticket/goal and scope to plan",
            "Why": "Phase 4 requires a concrete task and component scope",
            "Command": "none",
        },
        "snapshot": {"Confidence": "83%", "Risk": "MEDIUM", "Scope": "global"},
    }
    input_file = tmp_path / "payload.json"
    input_file.write_text(json.dumps(payload), encoding="utf-8")

    script = Path(__file__).resolve().parents[1] / "scripts" / "render_response_envelope.py"
    result = subprocess.run(
        [sys.executable, str(script), "--input", str(input_file), "--format", "plain"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "invalid phase/next_action contract" in result.stdout
