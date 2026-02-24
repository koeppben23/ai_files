from __future__ import annotations

from pathlib import Path

import pytest

from governance.kernel.phase_api_spec import PhaseApiSpecError, load_phase_api


def test_load_phase_api_reads_commands_home_spec(tmp_path: Path) -> None:
    commands_home = tmp_path / "commands"
    commands_home.mkdir(parents=True, exist_ok=True)
    (commands_home / "phase_api.yaml").write_text(
        """
version: 1
start_token: "1.1"
phases:
  - token: "1.1"
    phase: "1.1-Bootstrap"
    active_gate: "Workspace Ready Gate"
    next_gate_condition: "Continue"
    next: "2"
  - token: "2"
    phase: "2-RepoDiscovery"
    active_gate: "Repo Discovery"
    next_gate_condition: "Continue"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    spec = load_phase_api(commands_home)

    assert spec.path == commands_home / "phase_api.yaml"
    assert spec.start_token == "1.1"
    assert "2" in spec.entries
    assert spec.loaded_at


def test_load_phase_api_rejects_unknown_next_token(tmp_path: Path) -> None:
    commands_home = tmp_path / "commands"
    commands_home.mkdir(parents=True, exist_ok=True)
    (commands_home / "phase_api.yaml").write_text(
        """
version: 1
start_token: "1.1"
phases:
  - token: "1.1"
    phase: "1.1-Bootstrap"
    active_gate: "Workspace Ready Gate"
    next_gate_condition: "Continue"
    next: "9"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(PhaseApiSpecError):
        load_phase_api(commands_home)


def test_load_phase_api_requires_binding_when_commands_home_omitted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENCODE_PHASE_API_REPO_FALLBACK_FOR_TESTS", raising=False)
    with pytest.raises(PhaseApiSpecError):
        load_phase_api()
