from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.governance
def test_bootstrap_guide_does_not_inject_phase_parameters():
    text = (REPO_ROOT / "BOOTSTRAP.md").read_text(encoding="utf-8")
    forbidden = ["phase=", "active_gate=", "next_gate_condition="]
    hits = [token for token in forbidden if token in text]
    assert not hits, f"BOOTSTRAP.md must not inject phase routing parameters: {hits}"


@pytest.mark.governance
def test_bootstrap_guide_exposes_canonical_init_profile_surface():
    text = (REPO_ROOT / "BOOTSTRAP.md").read_text(encoding="utf-8")
    assert "init --profile" in text
    assert "--set-operating-mode" in text
