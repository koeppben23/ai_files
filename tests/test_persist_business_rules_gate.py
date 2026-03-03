from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from .util import REPO_ROOT


def _load_module():
    script = REPO_ROOT / "governance" / "entrypoints" / "persist_workspace_artifacts.py"
    spec = importlib.util.spec_from_file_location("persist_workspace_artifacts", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_orchestrator_module():
    script = REPO_ROOT / "governance" / "entrypoints" / "persist_workspace_artifacts_orchestrator.py"
    spec = importlib.util.spec_from_file_location("persist_workspace_artifacts_orchestrator", script)
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


@pytest.mark.governance
def test_business_rules_outcome_is_persisted_when_inventory_not_applicable(tmp_path: Path):
    module = _load_orchestrator_module()
    session_path = tmp_path / "SESSION_STATE.json"
    payload = {
        "SESSION_STATE": {
            "Scope": {"BusinessRules": "not-applicable"},
            "BusinessRules": {"Decision": "skip"},
        }
    }
    session_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    result = module._update_session_state(
        session_path=session_path,
        dry_run=False,
        business_rules_inventory_written=False,
        business_rules_inventory_action="not-applicable",
        repo_cache_action="kept",
        repo_map_digest_action="kept",
        decision_pack_action="kept",
        workspace_memory_action="kept",
        read_only=False,
    )
    assert result == "updated"

    updated = json.loads(session_path.read_text(encoding="utf-8"))
    rules = updated["SESSION_STATE"]["BusinessRules"]
    assert rules["Outcome"] == "not-applicable"
    assert rules["InventoryFileStatus"] == "unknown"
    assert rules["OutcomeSource"] == "scope"


@pytest.mark.governance
def test_business_rules_status_renderer_reports_visible_status_for_not_applicable():
    module = _load_orchestrator_module()

    outcome, source = module._resolve_business_rules_outcome(
        session={"Scope": {"BusinessRules": "not-applicable"}},
        business_rules_inventory_written=False,
        business_rules_inventory_action="not-applicable",
    )
    content = module._render_business_rules_status(
        date="2026-03-03",
        repo_name="demo",
        outcome=outcome,
        source=source,
    )

    assert "Outcome: not-applicable" in content
    assert "business-rules-status.md (always)" in content
    assert "business-rules.md (outcome=extracted only)" in content


@pytest.mark.governance
def test_resolve_python_command_prefers_binding_value() -> None:
    module = _load_orchestrator_module()
    resolved = module._resolve_python_command({"pythonCommand": "py -3"})
    assert resolved == "py -3"


@pytest.mark.governance
def test_resolve_python_command_falls_back_to_sys_executable() -> None:
    module = _load_orchestrator_module()
    resolved = module._resolve_python_command({})
    assert resolved == str(module.sys.executable)


@pytest.mark.governance
def test_python_argv_from_command_uses_sys_executable_when_python_alias_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_orchestrator_module()

    def _fake_which(name: str):
        if name == "python":
            return None
        return f"/usr/bin/{name}"

    monkeypatch.setattr(module.shutil, "which", _fake_which)
    argv = module._python_argv_from_command("python")
    assert argv == [str(module.sys.executable)]
