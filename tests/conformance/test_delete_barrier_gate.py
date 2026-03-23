from __future__ import annotations

from pathlib import Path

import scripts.delete_barrier_gate as delete_barrier_gate


def test_delete_barrier_gate_happy(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True)

    def fake_copy(src: Path, dst: Path) -> None:
        dst.mkdir(parents=True)

    def fake_run(cmd: list[str], cwd: Path) -> tuple[int, str, str]:
        return 0, "", ""

    monkeypatch.setattr(delete_barrier_gate, "_copy_repo", fake_copy)
    monkeypatch.setattr(delete_barrier_gate, "_run", fake_run)
    issues = delete_barrier_gate.run_delete_barrier(repo_root, "python")
    assert issues == []


def test_delete_barrier_gate_bad_failure(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True)

    def fake_copy(src: Path, dst: Path) -> None:
        dst.mkdir(parents=True)

    def fake_run(cmd: list[str], cwd: Path) -> tuple[int, str, str]:
        if "scripts/build.py" in cmd:
            return 1, "", "build fail"
        return 0, "", ""

    monkeypatch.setattr(delete_barrier_gate, "_copy_repo", fake_copy)
    monkeypatch.setattr(delete_barrier_gate, "_run", fake_run)
    issues = delete_barrier_gate.run_delete_barrier(repo_root, "python")
    assert any("build-smoke failed" in item for item in issues)


def test_delete_barrier_gate_corner_legacy_missing(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True)

    def fake_copy(src: Path, dst: Path) -> None:
        dst.mkdir(parents=True)

    monkeypatch.setattr(delete_barrier_gate, "_copy_repo", fake_copy)
    monkeypatch.setattr(delete_barrier_gate, "_run", lambda cmd, cwd: (0, "", ""))
    issues = delete_barrier_gate.run_delete_barrier(repo_root, "python")
    assert issues == []


def test_delete_barrier_gate_edge_multiple_failures(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True)

    def fake_copy(src: Path, dst: Path) -> None:
        dst.mkdir(parents=True)

    call_count = {"value": 0}

    def fake_run(cmd: list[str], cwd: Path) -> tuple[int, str, str]:
        call_count["value"] += 1
        if call_count["value"] in {1, 4}:
            return 2, "", "boom"
        return 0, "", ""

    monkeypatch.setattr(delete_barrier_gate, "_copy_repo", fake_copy)
    monkeypatch.setattr(delete_barrier_gate, "_run", fake_run)
    issues = delete_barrier_gate.run_delete_barrier(repo_root, "python")
    # Gate breaks on first failure (break-on-first contract).
    # fake_run fails on call 1 (import-smoke), so exactly 1 issue is expected.
    assert len(issues) == 1
    assert "import-smoke" in issues[0]
