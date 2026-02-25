from __future__ import annotations

from pathlib import Path


def test_no_secondary_phase_execution_policy_file() -> None:
    root = Path(__file__).resolve().parents[1]
    legacy = root / "governance" / "assets" / "config" / "phase_execution_config.yaml"
    assert not legacy.exists(), "phase_api.yaml must remain the only phase-routing control-plane source"
