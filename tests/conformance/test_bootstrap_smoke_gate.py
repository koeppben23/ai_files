from __future__ import annotations

from pathlib import Path

import scripts.bootstrap_smoke_gate as bootstrap_smoke_gate


def test_bootstrap_smoke_gate_happy(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], cwd: Path) -> tuple[int, str, str]:
        calls.append(cmd)
        return 0, "", ""

    monkeypatch.setattr(bootstrap_smoke_gate, "_run", fake_run)
    issues = bootstrap_smoke_gate.run_bootstrap_smoke(tmp_path, "python")
    assert issues == []
    assert len(calls) == 3


def test_bootstrap_smoke_gate_bad_install(monkeypatch, tmp_path: Path) -> None:
    def fake_run(cmd: list[str], cwd: Path) -> tuple[int, str, str]:
        if "install.py" in cmd and "--uninstall" not in cmd:
            return 1, "", "install failed"
        return 0, "", ""

    monkeypatch.setattr(bootstrap_smoke_gate, "_run", fake_run)
    issues = bootstrap_smoke_gate.run_bootstrap_smoke(tmp_path, "python")
    assert any("install phase failed" in item for item in issues)


def test_bootstrap_smoke_gate_corner_bootstrap_failure(monkeypatch, tmp_path: Path) -> None:
    def fake_run(cmd: list[str], cwd: Path) -> tuple[int, str, str]:
        if "cli/bootstrap.py" in cmd:
            return 2, "", "bootstrap failed"
        return 0, "", ""

    monkeypatch.setattr(bootstrap_smoke_gate, "_run", fake_run)
    issues = bootstrap_smoke_gate.run_bootstrap_smoke(tmp_path, "python")
    assert any("bootstrap phase failed" in item for item in issues)


def test_bootstrap_smoke_gate_edge_still_uninstalls(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], cwd: Path) -> tuple[int, str, str]:
        calls.append(cmd)
        if "cli/bootstrap.py" in cmd:
            return 3, "", "boom"
        return 0, "", ""

    monkeypatch.setattr(bootstrap_smoke_gate, "_run", fake_run)
    issues = bootstrap_smoke_gate.run_bootstrap_smoke(tmp_path, "python")
    assert issues
    assert any("--uninstall" in call for call in calls)
