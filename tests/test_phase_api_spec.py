from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from governance_runtime.kernel.phase_api_spec import PhaseApiSpecError, load_phase_api


def _write_isolated_spec(tmp_path: Path, text: str, *, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Set up binding evidence with spec_home so the test spec is authoritative."""
    home = tmp_path / "home"
    cfg = home / ".config" / "opencode"
    commands_home = cfg / "commands"
    spec_home = tmp_path / "governance_spec"
    commands_home.mkdir(parents=True, exist_ok=True)
    spec_home.mkdir(parents=True, exist_ok=True)
    (spec_home / "phase_api.yaml").write_text(text, encoding="utf-8")
    payload = {
        "schema": "opencode-governance.paths.v1",
        "paths": {
            "configRoot": str(cfg),
            "commandsHome": str(commands_home),
            "workspacesHome": str(cfg / "workspaces"),
            "specHome": str(spec_home),
            "pythonCommand": sys.executable,
        },
    }
    (cfg / "governance.paths.json").write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    return commands_home


def test_load_phase_api_reads_authoritative_spec(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    commands_home = _write_isolated_spec(
        tmp_path,
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
        monkeypatch=monkeypatch,
    )

    spec = load_phase_api(commands_home)
    assert spec.start_token == "1.1"
    assert "2" in spec.entries
    assert spec.loaded_at


def test_load_phase_api_rejects_unknown_next_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    commands_home = _write_isolated_spec(
        tmp_path,
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
        monkeypatch=monkeypatch,
    )

    with pytest.raises(PhaseApiSpecError):
        load_phase_api(commands_home)


def test_load_phase_api_requires_binding_when_commands_home_omitted(monkeypatch: pytest.MonkeyPatch) -> None:
    import governance_runtime.kernel.phase_api_spec as runtime_module

    class _Resolver:
        def resolve(self, *, mode: str = "kernel"):
            _ = mode
            return SimpleNamespace(binding_ok=False, commands_home=None, issues=["binding.file.missing"])

    monkeypatch.setattr(runtime_module, "BindingEvidenceResolver", _Resolver)
    with pytest.raises(PhaseApiSpecError):
        load_phase_api()
