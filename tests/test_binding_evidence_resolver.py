from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

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
def test_binding_resolver_marks_trusted_override_source_and_audit(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    canonical = tmp_path / "canonical"
    trusted = tmp_path / "trusted"
    for root in (canonical, trusted):
        (root / "commands").mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": "opencode-governance.paths.v1",
            "paths": {
                "commandsHome": str(root / "commands"),
                "workspacesHome": str(root / "workspaces"),
                "pythonCommand": "python3",
            },
        }
        (root / "commands" / "governance.paths.json").write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setenv("OPENCODE_ALLOW_TRUSTED_BINDING_OVERRIDE", "1")
    monkeypatch.setenv("OPENCODE_TRUSTED_COMMANDS_HOME", str(trusted / "commands"))
    resolver = BindingEvidenceResolver(env=dict(os.environ), config_root=canonical)
    evidence = resolver.resolve(mode="user")

    assert evidence.binding_ok is True
    assert evidence.source == "trusted_override"
    assert evidence.audit_marker == "POLICY_PRECEDENCE_APPLIED"
    assert evidence.audit_event is not None
    assert evidence.audit_event.get("source") == "trusted_override"
    assert evidence.audit_event.get("mode") == "user"


@pytest.mark.governance
def test_binding_resolver_keeps_canonical_source_when_cwd_search_enabled_but_unused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    (tmp_path / "commands").mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "opencode-governance.paths.v1",
        "paths": {
            "commandsHome": str(tmp_path / "commands"),
            "workspacesHome": str(tmp_path / "workspaces"),
            "pythonCommand": "python3",
        },
    }
    (tmp_path / "commands" / "governance.paths.json").write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setenv("OPENCODE_ALLOW_CWD_BINDINGS", "1")
    resolver = BindingEvidenceResolver(env=dict(os.environ), config_root=tmp_path)
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
            "commandsHome": str(commands),
            "workspacesHome": str(tmp_path / "workspaces"),
            "pythonCommand": "python3",
        },
    }
    (commands / "governance.paths.json").write_text(json.dumps(payload), encoding="utf-8")

    resolver = BindingEvidenceResolver(env={}, config_root=tmp_path)
    evidence = resolver.resolve(mode="user")

    assert evidence.binding_ok is True
    assert evidence.source == "canonical"


@pytest.mark.governance
def test_binding_resolver_requires_host_caps_for_dev_cwd_search(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    (tmp_path / "commands").mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "opencode-governance.paths.v1",
        "paths": {
            "commandsHome": str(tmp_path / "commands"),
            "workspacesHome": str(tmp_path / "workspaces"),
            "pythonCommand": "python3",
        },
    }
    (tmp_path / "commands" / "governance.paths.json").write_text(json.dumps(payload), encoding="utf-8")

    nested = tmp_path / "repo" / "nested"
    nested.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(nested)
    monkeypatch.setenv("OPENCODE_ALLOW_CWD_BINDINGS", "1")

    resolver = BindingEvidenceResolver(env=dict(os.environ), config_root=tmp_path / "missing-home")
    without_caps = resolver.resolve(mode="user")
    assert without_caps.binding_ok is False
    assert without_caps.source == "missing"

    with_caps = resolver.resolve(
        mode="user",
        host_caps=SimpleNamespace(fs_read_commands_home=True, fs_write_commands_home=False),
    )
    assert with_caps.binding_ok is True
    assert with_caps.source == "dev_cwd_search"
    assert with_caps.audit_marker == "POLICY_PRECEDENCE_APPLIED"
    assert with_caps.audit_event is not None


@pytest.mark.governance
def test_binding_resolver_rejects_non_string_command_profiles(tmp_path: Path):
    commands = tmp_path / "commands"
    commands.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "opencode-governance.paths.v1",
        "paths": {
            "commandsHome": str(commands),
            "workspacesHome": str(tmp_path / "workspaces"),
            "pythonCommand": "python3",
        },
        "commandProfiles": {"safe": {"cmd": "python3"}},
    }
    (commands / "governance.paths.json").write_text(json.dumps(payload), encoding="utf-8")

    resolver = BindingEvidenceResolver(env={}, config_root=tmp_path)
    evidence = resolver.resolve(mode="user")

    assert evidence.binding_ok is False
    assert evidence.source == "invalid"
