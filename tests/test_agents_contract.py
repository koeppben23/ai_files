from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_agents_contract_baseline_exists():
    root = _repo_root()
    agents = root / "AGENTS.md"
    assert agents.exists(), "AGENTS.md must exist at repo root"


def test_agents_contract_forbidden_tokens():
    text = ( _repo_root() / "AGENTS.md" ).read_text(encoding="utf-8").lower()
    # Ensure no host-binding tokens appear in AGENTS.md (no cluster-specific paths in content)
    assert "${" not in text
    assert "governance.paths.json" not in text


def test_agents_contract_alignment():
    text = ( _repo_root() / "AGENTS.md" ).read_text(encoding="utf-8").lower()
    assert "kernel wins" in text or "kernel" in text
    assert "bootstrap" in text or "evidence" in text
    assert "phases" in text
