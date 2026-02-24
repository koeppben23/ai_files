from pathlib import Path


def test_orchestrator_has_no_post_bootstrap_state_write() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    orchestrator_file = repo_root / "diagnostics" / "bootstrap_session_state_orchestrator.py"
    content = orchestrator_file.read_text(encoding="utf-8")

    assert "if result.ok:\n        return 0" in content
    assert "repo_state.write_text(" not in content
