from __future__ import annotations

import importlib.util

import pytest

from .util import REPO_ROOT


def _load_module():
    """Load diagnostics/start_preflight_persistence.py as a module for testing."""

    script = REPO_ROOT / "diagnostics" / "start_preflight_persistence.py"
    spec = importlib.util.spec_from_file_location("start_preflight_persistence", script)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load start_preflight_persistence module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.governance
def test_engine_shadow_snapshot_is_available_and_reports_parity_fields(monkeypatch: pytest.MonkeyPatch):
    """Shadow snapshot should expose deterministic parity fields when available."""

    monkeypatch.delenv("CI", raising=False)
    monkeypatch.chdir(REPO_ROOT)
    monkeypatch.setenv("OPENCODE_REPO_ROOT", str(REPO_ROOT))
    module = _load_module()
    snapshot = module.build_engine_shadow_snapshot()
    assert snapshot["available"] is True
    assert snapshot["runtime_mode"] == "shadow"
    assert snapshot["selfcheck_ok"] is True
    assert snapshot["repo_context_source"].startswith("env:")
    assert snapshot["effective_operating_mode"] == "user"
    assert isinstance(snapshot["capabilities_hash"], str) and len(snapshot["capabilities_hash"]) == 16
    assert snapshot["mode_downgraded"] is False
    assert snapshot["deviation"] is None
    assert snapshot["parity"] == {
        "status": "ok",
        "phase": "1.1-Bootstrap",
        "reason_code": "none",
        "next_action.command": "none",
    }


@pytest.mark.governance
def test_engine_shadow_snapshot_accepts_pipeline_operating_mode(monkeypatch: pytest.MonkeyPatch):
    """Shadow snapshot should accept explicit pipeline mode request."""

    monkeypatch.chdir(REPO_ROOT)
    monkeypatch.setenv("OPENCODE_REPO_ROOT", str(REPO_ROOT))
    monkeypatch.setenv("OPENCODE_OPERATING_MODE", "pipeline")
    module = _load_module()
    snapshot = module.build_engine_shadow_snapshot()
    assert snapshot["available"] is True
    assert snapshot["effective_operating_mode"] in {"pipeline", "user"}
