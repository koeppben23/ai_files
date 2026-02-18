from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from governance.infrastructure.binding_evidence_resolver import BindingEvidenceResolver


@pytest.mark.governance
def test_binding_resolver_returns_missing_when_no_file(tmp_path: Path):
    resolver = BindingEvidenceResolver(env={}, config_root=tmp_path)
    evidence = resolver.resolve()
    assert evidence.binding_ok is False
    assert evidence.source == "missing"


@pytest.mark.governance
def test_binding_resolver_rejects_relative_paths(tmp_path: Path):
    commands = tmp_path / "commands"
    commands.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "governance.paths.v1",
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
            "schema": "governance.paths.v1",
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


@pytest.mark.governance
def test_binding_resolver_keeps_canonical_source_when_cwd_search_enabled_but_unused(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    (tmp_path / "commands").mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "governance.paths.v1",
        "paths": {
            "commandsHome": str(tmp_path / "commands"),
            "workspacesHome": str(tmp_path / "workspaces"),
        },
    }
    (tmp_path / "commands" / "governance.paths.json").write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setenv("OPENCODE_ALLOW_CWD_BINDINGS", "1")
    resolver = BindingEvidenceResolver(env=dict(os.environ), config_root=tmp_path)
    evidence = resolver.resolve(mode="user")
    assert evidence.binding_ok is True
    assert evidence.source == "canonical"
    assert evidence.audit_marker is None
