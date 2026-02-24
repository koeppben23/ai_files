from __future__ import annotations

import importlib


def test_opencode_mode_overrides_ci_pipeline_heuristic(monkeypatch) -> None:
    monkeypatch.setenv("CI", "1")
    monkeypatch.setenv("OPENCODE_MODE", "user")
    monkeypatch.delenv("OPENCODE_DIAGNOSTICS_FORCE_READ_ONLY", raising=False)

    mod = importlib.import_module("diagnostics.write_policy")
    importlib.reload(mod)

    assert mod.EFFECTIVE_MODE == "user"
    assert mod.writes_allowed() is True


def test_force_read_only_always_blocks(monkeypatch) -> None:
    monkeypatch.setenv("OPENCODE_MODE", "user")
    monkeypatch.setenv("OPENCODE_DIAGNOSTICS_FORCE_READ_ONLY", "1")
    mod = importlib.import_module("diagnostics.write_policy")
    importlib.reload(mod)

    assert mod.writes_allowed() is False
    assert "force-read-only" in mod.write_policy_reasons()


def test_pipeline_mode_uses_pipeline_semantics(monkeypatch) -> None:
    monkeypatch.setenv("CI", "1")
    monkeypatch.setenv("OPENCODE_MODE", "pipeline")
    monkeypatch.delenv("OPENCODE_DIAGNOSTICS_FORCE_READ_ONLY", raising=False)

    mod = importlib.import_module("diagnostics.write_policy")
    importlib.reload(mod)

    assert mod.EFFECTIVE_MODE == "pipeline"
    assert mod.writes_allowed() is True
    assert "explicit-pipeline-mode-allow" in mod.write_policy_reasons()
