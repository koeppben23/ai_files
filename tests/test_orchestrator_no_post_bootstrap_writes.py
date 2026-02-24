from pathlib import Path
import re


def test_orchestrator_has_no_post_bootstrap_state_write() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    orchestrator_file = repo_root / "diagnostics" / "bootstrap_session_state_orchestrator.py"
    content = orchestrator_file.read_text(encoding="utf-8")

    assert re.search(r"if\s+result\.ok\s*:\s*return\s+0", content), "orchestrator must return immediately on success"
    assert "repo_state.write_text(" not in content
