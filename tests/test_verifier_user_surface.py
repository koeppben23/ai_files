from __future__ import annotations

from pathlib import Path

from governance.verification.user_surface_verifier import run_user_surface_verification


def test_user_surface_verifier_marks_unverified_without_registry_tests(tmp_path: Path) -> None:
    requirements = ({"id": "R1", "verification_methods": ["user_surface_verification"]},)
    registry = {"requirements": {"R1": {}}}
    cache: dict[str, bool] = {}
    result = run_user_surface_verification(
        requirements=requirements,
        registry=registry,
        python_bin="python3",
        repo_root=tmp_path,
        cache=cache,
        run_pytest_node=lambda python_bin, repo_root, nodeid: True,
    )
    assert result["R1"] == "UNVERIFIED"
