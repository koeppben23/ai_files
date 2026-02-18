from __future__ import annotations

import json
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
