from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import pytest

from .util import REPO_ROOT, write_governance_paths

_POLICY_FILES = [
    "bootstrap_policy.yaml",
    "persistence_artifacts.yaml",
    "blocked_reason_catalog.yaml",
    "phase_execution_config.yaml",
]


def _copy_policy_files(dest_diagnostics: Path) -> None:
    src_diagnostics = REPO_ROOT / "diagnostics"
    for filename in _POLICY_FILES:
        src = src_diagnostics / filename
        if src.exists():
            dest_diagnostics.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest_diagnostics / filename)


def _load_module():
    """Load diagnostics/start_preflight_readonly.py as a module for testing."""

    script = REPO_ROOT / "diagnostics" / "start_preflight_readonly.py"
    spec = importlib.util.spec_from_file_location("start_preflight_readonly", script)
    if spec is None or spec.loader is None:
        raise RuntimeError("failed to load start_preflight_readonly module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.governance
def test_engine_shadow_snapshot_is_available_and_reports_parity_fields(
    monkeypatch: pytest.MonkeyPatch, tmp_path
):
    """Shadow snapshot should expose deterministic parity fields when available."""

    monkeypatch.delenv("CI", raising=False)
    monkeypatch.chdir(REPO_ROOT)
    monkeypatch.setenv("OPENCODE_REPO_ROOT", str(REPO_ROOT))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    config_root = tmp_path / ".config" / "opencode"
    write_governance_paths(config_root)
    _copy_policy_files(config_root / "commands" / "diagnostics")
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
def test_engine_shadow_snapshot_accepts_pipeline_operating_mode(
    monkeypatch: pytest.MonkeyPatch, tmp_path
):
    """Shadow snapshot should accept explicit pipeline mode request."""

    config_root = tmp_path / ".config" / "opencode"
    write_governance_paths(config_root)
    _copy_policy_files(config_root / "commands" / "diagnostics")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.chdir(REPO_ROOT)
    monkeypatch.setenv("OPENCODE_REPO_ROOT", str(REPO_ROOT))
    monkeypatch.setenv("OPENCODE_OPERATING_MODE", "pipeline")
    module = _load_module()
    snapshot = module.build_engine_shadow_snapshot()
    assert snapshot["available"] is True
    assert snapshot["effective_operating_mode"] in {"pipeline", "user"}
