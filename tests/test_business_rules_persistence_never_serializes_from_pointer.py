from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from governance_runtime.engine.business_rules_hydration import POINTER_AS_SESSION_STATE_ERROR

from .util import REPO_ROOT


def _load_orchestrator_module():
    script = REPO_ROOT / "governance_runtime" / "entrypoints" / "persist_workspace_artifacts_orchestrator.py"
    spec = importlib.util.spec_from_file_location("persist_workspace_artifacts_orchestrator", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=True) + "\n", encoding="utf-8")


def _update_kwargs() -> dict[str, object]:
    return {
        "dry_run": False,
        "extractor_ran": False,
        "extracted_rule_count": 0,
        "extraction_evidence": False,
        "business_rules_inventory_action": "withheld",
        "repo_cache_action": "kept",
        "repo_map_digest_action": "kept",
        "decision_pack_action": "kept",
        "workspace_memory_action": "kept",
        "business_rules_inventory_sha256": "",
        "business_rules_rules": [],
        "business_rules_source_phase": "1.5-BusinessRules",
        "business_rules_extractor_version": "hybrid-br-v1",
        "business_rules_evidence_paths": [],
        "read_only": False,
    }


def test_happy_persistence_updates_materialized_session_state(tmp_path: Path) -> None:
    module = _load_orchestrator_module()
    session_path = tmp_path / "SESSION_STATE.json"
    _write_json(session_path, {"SESSION_STATE": {"Scope": {}, "BusinessRules": {}}})

    result = module._update_session_state(session_path=session_path, **_update_kwargs())

    assert result == "updated"


def test_bad_persistence_rejects_canonical_pointer_source(tmp_path: Path) -> None:
    module = _load_orchestrator_module()
    session_path = tmp_path / "SESSION_STATE.json"
    _write_json(
        session_path,
        {
            "schema": "opencode-session-pointer.v1",
            "activeSessionStateFile": str(tmp_path / "workspaces" / "abc123" / "SESSION_STATE.json"),
        },
    )

    with pytest.raises(ValueError, match=POINTER_AS_SESSION_STATE_ERROR):
        module._update_session_state(session_path=session_path, **_update_kwargs())


def test_corner_persistence_rejects_legacy_pointer_source(tmp_path: Path) -> None:
    module = _load_orchestrator_module()
    session_path = tmp_path / "SESSION_STATE.json"
    _write_json(
        session_path,
        {
            "schema": "active-session-pointer.v1",
            "active_session_state_relative_path": "workspaces/abc123/SESSION_STATE.json",
        },
    )

    with pytest.raises(ValueError, match=POINTER_AS_SESSION_STATE_ERROR):
        module._update_session_state(session_path=session_path, **_update_kwargs())


def test_edge_persistence_keeps_non_pointer_invalid_shape_result(tmp_path: Path) -> None:
    module = _load_orchestrator_module()
    session_path = tmp_path / "SESSION_STATE.json"
    _write_json(session_path, {"not_session_state": True})

    result = module._update_session_state(session_path=session_path, **_update_kwargs())

    assert result == "invalid-session-shape"
