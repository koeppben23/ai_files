from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from governance.infrastructure.binding_evidence_resolver import BindingEvidenceResolver


@pytest.mark.governance
def test_binding_resolver_returns_missing_when_no_file(tmp_path: Path):
    resolver = BindingEvidenceResolver(env={}, config_root=tmp_path)
    evidence = resolver.resolve()
    assert evidence.binding_ok is False
    assert evidence.source == "missing"
    assert evidence.python_command == ""


@pytest.mark.governance
def test_binding_resolver_rejects_relative_paths(tmp_path: Path):
    commands = tmp_path / "commands"
    commands.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "opencode-governance.paths.v1",
        "paths": {
            "commandsHome": "./commands",
            "workspacesHome": "./workspaces",
        },
    }
    (commands / "governance.paths.json").write_text(json.dumps(payload), encoding="utf-8")
    resolver = BindingEvidenceResolver(env={}, config_root=tmp_path)
    evidence = resolver.resolve()
    assert evidence.binding_ok is False
    assert evidence.source == "invalid"


@pytest.mark.governance
def test_binding_resolver_keeps_canonical_source(tmp_path: Path):
    (tmp_path / "commands").mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "opencode-governance.paths.v1",
        "paths": {
            "configRoot": str(tmp_path),
            "commandsHome": str(tmp_path / "commands"),
            "workspacesHome": str(tmp_path / "workspaces"),
            "pythonCommand": sys.executable,
        },
    }
    (tmp_path / "commands" / "governance.paths.json").write_text(json.dumps(payload), encoding="utf-8")

    resolver = BindingEvidenceResolver(env={}, config_root=tmp_path)
    evidence = resolver.resolve(mode="user")
    assert evidence.binding_ok is True
    assert evidence.source == "canonical"
    assert evidence.audit_marker is None
    assert evidence.audit_event is None


@pytest.mark.governance
def test_binding_resolver_accepts_legacy_schema_for_backward_compat(tmp_path: Path):
    commands = tmp_path / "commands"
    commands.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "governance.paths.v1",
        "paths": {
            "configRoot": str(tmp_path),
            "commandsHome": str(commands),
            "workspacesHome": str(tmp_path / "workspaces"),
            "pythonCommand": sys.executable,
        },
    }
    (commands / "governance.paths.json").write_text(json.dumps(payload), encoding="utf-8")

    resolver = BindingEvidenceResolver(env={}, config_root=tmp_path)
    evidence = resolver.resolve(mode="user")

    assert evidence.binding_ok is True
    assert evidence.source == "canonical"


@pytest.mark.governance
def test_binding_resolver_is_canonical_only_when_config_root_missing(tmp_path: Path):
    resolver = BindingEvidenceResolver(env={}, config_root=tmp_path / "missing-home")
    evidence = resolver.resolve(mode="user")
    assert evidence.binding_ok is False
    assert evidence.source == "missing"


@pytest.mark.governance
def test_binding_resolver_rejects_non_string_command_profiles(tmp_path: Path):
    commands = tmp_path / "commands"
    commands.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "opencode-governance.paths.v1",
        "paths": {
            "commandsHome": str(commands),
            "workspacesHome": str(tmp_path / "workspaces"),
            "pythonCommand": sys.executable,
        },
        "commandProfiles": {"safe": {"cmd": "python3"}},
    }
    (commands / "governance.paths.json").write_text(json.dumps(payload), encoding="utf-8")

    resolver = BindingEvidenceResolver(env={}, config_root=tmp_path)
    evidence = resolver.resolve(mode="user")

    assert evidence.binding_ok is False
    assert evidence.source == "invalid"
