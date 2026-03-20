from __future__ import annotations

from pathlib import Path

import pytest

from governance_runtime.kernel.phase_api_spec import PhaseApiSpecError, load_phase_api


def _write_spec(tmp_path: Path, text: str) -> Path:
    commands_home = tmp_path / "commands"
    commands_home.mkdir(parents=True, exist_ok=True)
    (commands_home / "phase_api.yaml").write_text(text.strip() + "\n", encoding="utf-8")
    return commands_home


def test_rejects_duplicate_tokens(tmp_path: Path) -> None:
    commands_home = _write_spec(
        tmp_path,
        """
version: 1
start_token: "1"
phases:
  - token: "1"
    phase: "1-A"
    active_gate: "G"
    next_gate_condition: "N"
  - token: "1"
    phase: "1-B"
    active_gate: "G"
    next_gate_condition: "N"
""",
    )
    with pytest.raises(PhaseApiSpecError, match="duplicate token"):
        load_phase_api(commands_home)


def test_rejects_missing_phase_field(tmp_path: Path) -> None:
    commands_home = _write_spec(
        tmp_path,
        """
version: 1
start_token: "1"
phases:
  - token: "1"
    active_gate: "G"
    next_gate_condition: "N"
""",
    )
    with pytest.raises(PhaseApiSpecError, match="missing phase"):
        load_phase_api(commands_home)


def test_rejects_invalid_route_strategy(tmp_path: Path) -> None:
    commands_home = _write_spec(
        tmp_path,
        """
version: 1
start_token: "1"
phases:
  - token: "1"
    phase: "1-A"
    active_gate: "G"
    next_gate_condition: "N"
    route_strategy: "jump"
""",
    )
    with pytest.raises(PhaseApiSpecError, match="route_strategy"):
        load_phase_api(commands_home)


def test_rejects_transition_with_unknown_target(tmp_path: Path) -> None:
    commands_home = _write_spec(
        tmp_path,
        """
version: 1
start_token: "1"
phases:
  - token: "1"
    phase: "1-A"
    active_gate: "G"
    next_gate_condition: "N"
    transitions:
      - when: default
        next: "9"
  - token: "2"
    phase: "2-B"
    active_gate: "G"
    next_gate_condition: "N"
""",
    )
    with pytest.raises(PhaseApiSpecError, match="unknown transition next token"):
        load_phase_api(commands_home)


def test_rejects_transition_missing_next(tmp_path: Path) -> None:
    commands_home = _write_spec(
        tmp_path,
        """
version: 1
start_token: "1"
phases:
  - token: "1"
    phase: "1-A"
    active_gate: "G"
    next_gate_condition: "N"
    transitions:
      - when: default
""",
    )
    with pytest.raises(PhaseApiSpecError, match="transition missing 'next'"):
        load_phase_api(commands_home)


def test_rejects_transitions_wrong_type(tmp_path: Path) -> None:
    commands_home = _write_spec(
        tmp_path,
        """
version: 1
start_token: "1"
phases:
  - token: "1"
    phase: "1-A"
    active_gate: "G"
    next_gate_condition: "N"
    transitions: "not-a-list"
""",
    )
    with pytest.raises(PhaseApiSpecError, match="transitions must be a list"):
        load_phase_api(commands_home)


def test_rejects_start_token_that_is_not_defined(tmp_path: Path) -> None:
    commands_home = _write_spec(
        tmp_path,
        """
version: 1
start_token: "2"
phases:
  - token: "1"
    phase: "1-A"
    active_gate: "G"
    next_gate_condition: "N"
""",
    )
    with pytest.raises(PhaseApiSpecError, match="start_token"):
        load_phase_api(commands_home)


def test_unknown_extra_fields_are_ignored_but_spec_loads(tmp_path: Path) -> None:
    commands_home = _write_spec(
        tmp_path,
        """
version: 1
start_token: "1"
phases:
  - token: "1"
    phase: "1-A"
    active_gate: "G"
    next_gate_condition: "N"
    custom_unknown_key: "x"
    transitions:
      - when: default
        next: "1"
        unknown_transition_key: true
""",
    )
    spec = load_phase_api(commands_home)
    assert spec.start_token == "1"
    assert "1" in spec.entries
