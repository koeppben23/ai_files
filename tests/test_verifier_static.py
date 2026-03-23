from __future__ import annotations

from pathlib import Path

from governance_runtime.verification.static_verifier import run_static_verification


def test_static_verifier_checks_hotspot_presence(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x=1\n", encoding="utf-8")
    requirements = ({"id": "R1", "code_hotspots": ["a.py"]}, {"id": "R2", "code_hotspots": ["missing.py"]})
    result = run_static_verification(requirements=requirements, repo_root=tmp_path)
    assert result["R1"] == "PASS"
    assert result["R2"] == "FAIL"
