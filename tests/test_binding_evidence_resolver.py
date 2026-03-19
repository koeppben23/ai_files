from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from governance.infrastructure.binding_evidence_resolver import BindingEvidenceResolver


def _write_paths(commands: Path, *, schema: str, paths: dict[str, str], command_profiles: dict[str, object] | None = None) -> None:
    payload: dict[str, object] = {"schema": schema, "paths": paths}
    if command_profiles is not None:
        payload["commandProfiles"] = command_profiles
    (commands / "governance.paths.json").write_text(json.dumps(payload), encoding="utf-8")


def _resolver(config_root: Path, commands_home: Path | None = None) -> BindingEvidenceResolver:
    env = {"COMMANDS_HOME": str(commands_home)} if commands_home is not None else {}
    return BindingEvidenceResolver(env=env, config_root=config_root)


@pytest.mark.governance
def test_binding_resolver_returns_missing_when_no_file(tmp_path: Path):
    resolver = _resolver(tmp_path)
    evidence = resolver.resolve()
    assert evidence.binding_ok is False
    assert evidence.source == "missing"
    assert evidence.python_command == ""


@pytest.mark.governance
def test_binding_resolver_rejects_relative_paths(tmp_path: Path):
    commands = tmp_path / "commands"
    commands.mkdir(parents=True, exist_ok=True)
    _write_paths(
        commands,
        schema="opencode-governance.paths.v1",
        paths={
            "commandsHome": "./commands",
            "workspacesHome": "./workspaces",
        },
    )
    resolver = _resolver(tmp_path, commands)
    evidence = resolver.resolve()
    assert evidence.binding_ok is False
    assert evidence.source == "invalid"


@pytest.mark.governance
def test_binding_resolver_keeps_canonical_source(tmp_path: Path):
    commands = tmp_path / "commands"
    commands.mkdir(parents=True, exist_ok=True)
    _write_paths(
        commands,
        schema="opencode-governance.paths.v1",
        paths={
            "configRoot": str(tmp_path),
            "localRoot": str(tmp_path),
            "commandsHome": str(commands),
            "runtimeHome": str(tmp_path / "governance_runtime"),
            "governanceHome": str(tmp_path / "governance"),
            "contentHome": str(tmp_path / "governance_content"),
            "specHome": str(tmp_path / "governance_spec"),
            "profilesHome": str(tmp_path / "governance_content" / "profiles"),
            "workspacesHome": str(tmp_path / "workspaces"),
            "pythonCommand": sys.executable,
        },
    )

    resolver = _resolver(tmp_path, commands)
    evidence = resolver.resolve(mode="user")
    assert evidence.binding_ok is True
    assert evidence.source == "canonical"
    assert evidence.audit_marker is None
    assert evidence.audit_event is None


@pytest.mark.governance
def test_binding_resolver_accepts_legacy_schema_for_backward_compat(tmp_path: Path):
    commands = tmp_path / "commands"
    commands.mkdir(parents=True, exist_ok=True)
    _write_paths(
        commands,
        schema="governance.paths.v1",
        paths={
            "configRoot": str(tmp_path),
            "commandsHome": str(commands),
            "workspacesHome": str(tmp_path / "workspaces"),
            "pythonCommand": sys.executable,
        },
    )

    resolver = _resolver(tmp_path, commands)
    evidence = resolver.resolve(mode="user")

    assert evidence.binding_ok is True
    assert evidence.source == "canonical"


@pytest.mark.governance
def test_binding_resolver_is_canonical_only_when_config_root_missing(tmp_path: Path):
    resolver = _resolver(tmp_path / "missing-home")
    evidence = resolver.resolve(mode="user")
    assert evidence.binding_ok is False
    assert evidence.source == "missing"


@pytest.mark.governance
def test_binding_resolver_rejects_non_string_command_profiles(tmp_path: Path):
    commands = tmp_path / "commands"
    commands.mkdir(parents=True, exist_ok=True)
    _write_paths(
        commands,
        schema="opencode-governance.paths.v1",
        paths={
            "commandsHome": str(commands),
            "workspacesHome": str(tmp_path / "workspaces"),
            "pythonCommand": sys.executable,
        },
        command_profiles={"safe": {"cmd": "python3"}},
    )

    resolver = _resolver(tmp_path, commands)
    evidence = resolver.resolve(mode="user")

    assert evidence.binding_ok is False
    assert evidence.source == "invalid"
