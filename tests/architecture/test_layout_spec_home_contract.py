from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from governance_runtime.infrastructure.binding_evidence_resolver import BindingEvidenceResolver


def _write_binding(
    *,
    config_root: Path,
    local_root: Path,
    commands_home: Path,
    workspaces_home: Path,
    spec_home: Path,
) -> None:
    payload = {
        "schema": "opencode-governance.paths.v1",
        "paths": {
            "configRoot": str(config_root),
            "localRoot": str(local_root),
            "commandsHome": str(commands_home),
            "workspacesHome": str(workspaces_home),
            "specHome": str(spec_home),
            "pythonCommand": sys.executable,
        },
    }
    (config_root / "governance.paths.json").write_text(
        json.dumps(payload, ensure_ascii=True),
        encoding="utf-8",
    )


@pytest.mark.governance
def test_binding_evidence_happy_spec_home_under_local_root(tmp_path: Path) -> None:
    config_root = tmp_path / "config"
    local_root = tmp_path / "local"
    commands_home = config_root / "commands"
    workspaces_home = config_root / "workspaces"
    spec_home = local_root / "governance_spec"

    commands_home.mkdir(parents=True, exist_ok=True)
    workspaces_home.mkdir(parents=True, exist_ok=True)
    spec_home.mkdir(parents=True, exist_ok=True)

    _write_binding(
        config_root=config_root,
        local_root=local_root,
        commands_home=commands_home,
        workspaces_home=workspaces_home,
        spec_home=spec_home,
    )

    resolver = BindingEvidenceResolver(config_root=config_root)
    evidence = resolver.resolve()

    assert evidence.source == "canonical"
    assert evidence.binding_ok is True
    assert evidence.spec_home == spec_home
    assert evidence.local_root == local_root


@pytest.mark.governance
def test_binding_evidence_blocks_spec_home_under_config_root(tmp_path: Path) -> None:
    """Spec layout contract: specHome must be under localRoot, not configRoot."""
    config_root = tmp_path / "config"
    local_root = tmp_path / "local"
    commands_home = config_root / "commands"
    workspaces_home = config_root / "workspaces"
    bad_spec_home = config_root / "governance_spec"

    commands_home.mkdir(parents=True, exist_ok=True)
    workspaces_home.mkdir(parents=True, exist_ok=True)
    bad_spec_home.mkdir(parents=True, exist_ok=True)

    _write_binding(
        config_root=config_root,
        local_root=local_root,
        commands_home=commands_home,
        workspaces_home=workspaces_home,
        spec_home=bad_spec_home,
    )

    resolver = BindingEvidenceResolver(config_root=config_root)
    evidence = resolver.resolve()

    assert evidence.source == "canonical"
    assert evidence.binding_ok is False
    assert "binding.paths.specHome.parent-mismatch" in evidence.issues


@pytest.mark.governance
def test_runtime_code_has_no_config_root_governance_spec_path_assumption() -> None:
    """Architecture guard: runtime must not hardcode configRoot/governance_spec."""
    repo_root = Path(__file__).resolve().parents[2]
    runtime_root = repo_root / "governance_runtime"

    forbidden_snippets = (
        '.config/opencode/governance_spec',
        '~/.config/opencode/governance_spec',
        'config_root / "governance_spec"',
        "config_root / 'governance_spec'",
        'cfg / "governance_spec"',
        "cfg / 'governance_spec'",
    )

    offenders: list[str] = []
    for file_path in runtime_root.rglob("*.py"):
        text = file_path.read_text(encoding="utf-8")
        for snippet in forbidden_snippets:
            if snippet in text:
                offenders.append(f"{file_path}:{snippet}")

    assert not offenders, "\n".join(offenders)
