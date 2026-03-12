from __future__ import annotations

import json
from pathlib import Path

from governance.verification import runner


def test_runner_happy_with_stubbed_pytest(monkeypatch) -> None:
    root = Path(__file__).resolve().parents[1]

    monkeypatch.setattr(runner, "_run_pytest_node", lambda python_bin, repo_root, nodeid: True)
    result = runner.run_contract_verification(repo_root=root)
    assert result["status"] == "PASS"
    assert result["merge_allowed"] is True


def test_runner_bad_when_pytest_node_fails(monkeypatch) -> None:
    root = Path(__file__).resolve().parents[1]

    def _run(python_bin: str, repo_root: Path, nodeid: str) -> bool:
        return "test_main_happy_approve" not in nodeid

    monkeypatch.setattr(runner, "_run_pytest_node", _run)
    result = runner.run_contract_verification(repo_root=root)
    assert result["status"] == "FAIL"
    assert result["merge_allowed"] is False


def test_runner_corner_missing_registry_method_is_unverified(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path
    (repo / "governance" / "contracts" / "requirements").mkdir(parents=True)
    (repo / "governance" / "contracts" / "verification_registry.json").write_text(
        json.dumps({"schema": "governance-verification-registry.v1", "requirements": {}}, ensure_ascii=True),
        encoding="utf-8",
    )
    (repo / "governance" / "contracts" / "requirements" / "R-X.json").write_text(
        json.dumps(
            {
                "id": "R-X",
                "title": "X",
                "criticality": "release_blocking",
                "owner_test": "tests/test_x.py::test_owner",
                "live_proof_key": "LP-X",
                "required_behavior": ["x"],
                "forbidden_behavior": ["no decision without x"],
                "user_visible_expectation": ["x"],
                "state_expectation": ["x"],
                "code_hotspots": ["README.md"],
                "verification_methods": [
                    "static_verification",
                    "behavioral_verification",
                    "user_surface_verification",
                    "live_flow_verification",
                    "receipts_verification"
                ],
                "acceptance_tests": ["tests/test_x.py::test_owner"],
                "done_rule": {
                    "require_all_verifications_pass": True,
                    "fail_closed_on_missing_evidence": True,
                    "fail_on_forbidden_observation": True
                }
            },
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )
    (repo / "README.md").write_text("ok\n", encoding="utf-8")
    monkeypatch.setattr(runner, "_run_pytest_node", lambda python_bin, repo_root, nodeid: True)
    result = runner.run_contract_verification(repo_root=repo)
    assert result["status"] == "UNVERIFIED"
    matrix_obj = result.get("matrix")
    assert isinstance(matrix_obj, dict)
    rows_obj = matrix_obj.get("completion_matrix")
    assert isinstance(rows_obj, list) and rows_obj
    row = rows_obj[0]
    assert isinstance(row, dict)
    assert row["behavioral_verification"] == "UNVERIFIED"


def test_runner_edge_contract_validation_failure() -> None:
    root = Path(__file__).resolve().parents[1]
    bad = runner.run_contract_verification(repo_root=root / "non-existent")
    assert bad["status"] == "FAIL"
    assert bad["reason"] == "verification_registry_load_failed"
