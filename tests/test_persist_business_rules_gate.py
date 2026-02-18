from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from .util import REPO_ROOT


def _load_module():
    script = REPO_ROOT / "diagnostics" / "persist_workspace_artifacts.py"
    spec = importlib.util.spec_from_file_location("persist_workspace_artifacts", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.governance
def test_business_rules_inventory_writes_when_business_rules_gate_active():
    module = _load_module()
    session = {
        "Phase": "2.1-DecisionPack",
        "active_gate": "business_rules_persist",
        "Scope": {"BusinessRules": "not-applicable"},
    }

    assert module._should_write_business_rules_inventory(session) is True


@pytest.mark.governance
def test_business_rules_inventory_not_written_without_phase_or_gate_signal():
    module = _load_module()
    session = {
        "Phase": "2-RepoDiscovery",
        "active_gate": "none",
        "Scope": {"BusinessRules": "not-applicable"},
    }

    assert module._should_write_business_rules_inventory(session) is False
