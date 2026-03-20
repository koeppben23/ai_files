from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from governance_runtime.engine.business_rules_hydration import hydrate_business_rules_state_from_artifacts

from .util import REPO_ROOT


def _load_module():
    script = REPO_ROOT / "governance_runtime" / "entrypoints" / "persist_workspace_artifacts.py"
    spec = importlib.util.spec_from_file_location("persist_workspace_artifacts", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_orchestrator_module():
    script = REPO_ROOT / "governance_runtime" / "entrypoints" / "persist_workspace_artifacts_orchestrator.py"
    spec = importlib.util.spec_from_file_location("persist_workspace_artifacts_orchestrator", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.governance
def test_business_rules_inventory_writes_when_business_rules_gate_active():
    module = _load_module()
    assert module._should_write_business_rules_inventory(outcome="extracted", extraction_evidence=True) is True


@pytest.mark.governance
def test_business_rules_inventory_written_without_phase_or_gate_signal():
    module = _load_module()
    assert module._should_write_business_rules_inventory(outcome="unresolved", extraction_evidence=True) is False


@pytest.mark.governance
def test_business_rules_outcome_is_persisted_when_inventory_signal_is_present(tmp_path: Path):
    module = _load_orchestrator_module()
    session_path = tmp_path / "SESSION_STATE.json"
    payload = {
        "SESSION_STATE": {
            "Scope": {"BusinessRules": "unresolved"},
            "BusinessRules": {"Decision": "skip"},
        }
    }
    session_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    result = module._update_session_state(
        session_path=session_path,
        dry_run=False,
        extractor_ran=True,
        extracted_rule_count=0,
        extraction_evidence=True,
        business_rules_inventory_action="withheld",
        repo_cache_action="kept",
        repo_map_digest_action="kept",
        decision_pack_action="kept",
        workspace_memory_action="kept",
        business_rules_inventory_sha256="abc123",
        business_rules_rules=["Rule A", "Rule B"],
        business_rules_source_phase="1.5-BusinessRules",
        business_rules_extractor_version="deterministic-br-v1",
        business_rules_evidence_paths=["README.md:1"],
        read_only=False,
    )
    assert result == "updated"

    updated = json.loads(session_path.read_text(encoding="utf-8"))
    rules = updated["SESSION_STATE"]["BusinessRules"]
    assert rules["Outcome"] == "gap-detected"
    assert rules["InventoryFileStatus"] == "withheld"
    assert rules["OutcomeSource"] == "scope"
    assert rules["ExecutionEvidence"] is True
    assert rules["Inventory"]["sha256"] == "abc123"
    assert rules["Inventory"]["count"] == 2


@pytest.mark.governance
def test_business_rules_status_renderer_reports_visible_status_for_unresolved():
    module = _load_orchestrator_module()

    outcome, source = module._resolve_business_rules_outcome(
        session={"Scope": {"BusinessRules": "unresolved"}},
        extractor_ran=False,
        extracted_rule_count=0,
        extraction_evidence=False,
        business_rules_inventory_action="withheld",
    )
    content = module._render_business_rules_status(
        date="2026-03-03",
        repo_name="demo",
        outcome=outcome,
        source=source,
        source_phase="2.1-DecisionPack",
        execution_evidence=False,
        extractor_version="deterministic-br-v1",
        rules_hash="",
    )

    assert "Outcome: unresolved" in content
    assert "business-rules-status.md (always)" in content
    assert "business-rules.md (written: no)" in content


@pytest.mark.governance
def test_business_rules_outcome_unresolved_without_extraction_evidence():
    module = _load_orchestrator_module()
    outcome, source = module._resolve_business_rules_outcome(
        session={"Scope": {"BusinessRules": "pending"}},
        extractor_ran=False,
        extracted_rule_count=0,
        extraction_evidence=False,
        business_rules_inventory_action="withheld",
    )

    assert outcome == "unresolved"
    assert source == "scope"


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
        # Simulate no python, no py launcher — force fallback to sys.executable
        if name in ("python", "py"):
            return None
        return f"/usr/bin/{name}"

    monkeypatch.setattr(module.shutil, "which", _fake_which)
    argv = module._python_argv_from_command("python")
    assert argv == [str(module.sys.executable)]


@pytest.mark.governance
def test_hydrate_business_rules_state_from_artifacts_happy_path(tmp_path: Path) -> None:
    status = tmp_path / "business-rules-status.md"
    inventory = tmp_path / "business-rules.md"
    status.write_text(
        "\n".join(
            [
                "Outcome: extracted",
                "ExecutionEvidence: true",
                "SourcePhase: 1.5-BusinessRules",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    inventory.write_text(
        "\n".join(["## BR-001", "Rule: BR-001: Access must be checked", "Rule: BR-002: Audit required"]) + "\n",
        encoding="utf-8",
    )

    state: dict[str, object] = {"Scope": {}, "BusinessRules": {}}
    applied = hydrate_business_rules_state_from_artifacts(
        state=state,
        status_path=status,
        inventory_path=inventory,
    )

    assert applied is True
    assert state["Scope"]["BusinessRules"] == "extracted"  # type: ignore[index]
    rules = state["BusinessRules"]  # type: ignore[assignment]
    assert rules["Outcome"] == "extracted"  # type: ignore[index]
    assert rules["ExecutionEvidence"] is True  # type: ignore[index]
    assert rules["InventoryLoaded"] is True  # type: ignore[index]
    assert rules["ExtractedCount"] == 2  # type: ignore[index]


@pytest.mark.governance
def test_hydrate_business_rules_state_from_artifacts_corner_missing_inventory(tmp_path: Path) -> None:
    status = tmp_path / "business-rules-status.md"
    status.write_text("Outcome: not-applicable\nExecutionEvidence: true\n", encoding="utf-8")

    state: dict[str, object] = {"Scope": {}, "BusinessRules": {}}
    applied = hydrate_business_rules_state_from_artifacts(
        state=state,
        status_path=status,
        inventory_path=tmp_path / "business-rules.md",
    )

    assert applied is True
    rules = state["BusinessRules"]  # type: ignore[assignment]
    assert rules["Outcome"] == "gap-detected"  # type: ignore[index]
    assert rules["InventoryLoaded"] is False  # type: ignore[index]
    assert rules["ExtractedCount"] == 0  # type: ignore[index]


@pytest.mark.governance
def test_hydrate_business_rules_state_from_artifacts_bad_extracted_without_evidence(tmp_path: Path) -> None:
    status = tmp_path / "business-rules-status.md"
    inventory = tmp_path / "business-rules.md"
    status.write_text("Outcome: extracted\nExecutionEvidence: false\n", encoding="utf-8")
    inventory.write_text("Rule: BR-001: must hold\n", encoding="utf-8")

    state: dict[str, object] = {
        "Scope": {"BusinessRules": "unresolved"},
        "BusinessRules": {"Outcome": "unresolved", "ExecutionEvidence": False},
    }
    applied = hydrate_business_rules_state_from_artifacts(
        state=state,
        status_path=status,
        inventory_path=inventory,
    )

    assert applied is True
    rules = state["BusinessRules"]  # type: ignore[assignment]
    assert rules["Outcome"] == "gap-detected"  # type: ignore[index]


@pytest.mark.governance
def test_update_session_state_hydrates_from_artifacts_edge(tmp_path: Path) -> None:
    module = _load_orchestrator_module()
    session_path = tmp_path / "SESSION_STATE.json"
    payload = {"SESSION_STATE": {"Scope": {"BusinessRules": "pending"}, "BusinessRules": {}}}
    session_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    (tmp_path / "business-rules-status.md").write_text(
        "Outcome: extracted\nExecutionEvidence: true\n",
        encoding="utf-8",
    )
    (tmp_path / "business-rules.md").write_text(
        "Rule: BR-100: Do not delete invoices\n",
        encoding="utf-8",
    )

    result = module._update_session_state(
        session_path=session_path,
        dry_run=False,
        extractor_ran=False,
        extracted_rule_count=0,
        extraction_evidence=False,
        business_rules_inventory_action="kept",
        repo_cache_action="kept",
        repo_map_digest_action="kept",
        decision_pack_action="kept",
        workspace_memory_action="kept",
        business_rules_inventory_sha256="",
        business_rules_rules=[],
        business_rules_source_phase="1.5-BusinessRules",
        business_rules_extractor_version="deterministic-br-v1",
        business_rules_evidence_paths=[],
        read_only=False,
    )
    assert result == "updated"

    updated = json.loads(session_path.read_text(encoding="utf-8"))
    rules = updated["SESSION_STATE"]["BusinessRules"]
    assert updated["SESSION_STATE"]["Scope"]["BusinessRules"] == "extracted"
    assert rules["ExecutionEvidence"] is True
    assert rules["InventoryLoaded"] is True
    assert rules["ExtractedCount"] == 1
