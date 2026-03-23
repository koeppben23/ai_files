from __future__ import annotations

from pathlib import Path

from governance_runtime.verification.behavioral_verifier import run_behavioral_verification


def test_behavioral_verifier_uses_registry_and_pytest_runner(tmp_path: Path) -> None:
    requirements = ({"id": "R1", "verification_methods": ["behavioral_verification"]},)
    registry = {"requirements": {"R1": {"behavioral_verification": ["tests/test_x.py::test_y"]}}}
    cache: dict[str, bool] = {}

    result = run_behavioral_verification(
        requirements=requirements,
        registry=registry,
        python_bin="python3",
        repo_root=tmp_path,
        cache=cache,
        run_pytest_node=lambda python_bin, repo_root, nodeid: True,
    )
    assert result["R1"] == "PASS"
