from __future__ import annotations

from pathlib import Path

from governance_runtime.verification.live_flow_verifier import run_live_flow_verification


def test_live_flow_verifier_fails_when_live_test_fails(tmp_path: Path) -> None:
    requirements = ({"id": "R1", "verification_methods": ["live_flow_verification"]},)
    registry = {"requirements": {"R1": {"live_flow_verification": ["tests/test_live.py::test_flow"]}}}
    cache: dict[str, bool] = {}
    result = run_live_flow_verification(
        requirements=requirements,
        registry=registry,
        python_bin="python3",
        repo_root=tmp_path,
        cache=cache,
        run_pytest_node=lambda python_bin, repo_root, nodeid: False,
    )
    assert result["R1"] == "FAIL"
