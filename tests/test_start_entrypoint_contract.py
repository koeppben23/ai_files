from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.governance
def test_start_entrypoint_uses_readonly_preflight_only():
    text = (REPO_ROOT / "start.md").read_text(encoding="utf-8")
    assert "start_preflight_readonly.py" in text
    assert "start_preflight_persistence.py" not in text


@pytest.mark.governance
def test_start_entrypoint_does_not_inject_phase_parameters():
    text = (REPO_ROOT / "start.md").read_text(encoding="utf-8")
    forbidden = ["phase=", "active_gate=", "next_gate_condition="]
    hits = [token for token in forbidden if token in text]
    assert not hits, f"start.md must not inject phase routing parameters: {hits}"
