from __future__ import annotations

from pathlib import Path

from governance_runtime.infrastructure.logging.global_error_handler import emit_error_event


def test_fp_unknown_logs_to_commands_home(tmp_path: Path) -> None:
    commands_home = tmp_path / "commands"
    workspaces_home = tmp_path / "workspaces"
    commands_home.mkdir(parents=True, exist_ok=True)
    workspaces_home.mkdir(parents=True, exist_ok=True)

    ok = emit_error_event(
        severity="HIGH",
        code="TEST_FP_UNKNOWN",
        message="fallback",
        commands_home=commands_home,
        workspaces_home=workspaces_home,
        repo_fingerprint=None,
    )

    assert ok is True
    assert (commands_home / "logs" / "error.log.jsonl").exists()
    assert not any((workspaces_home).rglob("error.log.jsonl"))
