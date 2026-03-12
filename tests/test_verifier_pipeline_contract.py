from __future__ import annotations

from governance.verification.pipeline import run_verifier_pipeline


def test_verifier_pipeline_happy_all_pass() -> None:
    requirements = ({"id": "R1", "criticality": "release_blocking"},)
    result = run_verifier_pipeline(
        requirements=requirements,
        static_results={"R1": "PASS"},
        behavioral_results={"R1": "PASS"},
        user_surface_results={"R1": "PASS"},
        live_flow_results={"R1": "PASS"},
        receipts_results={"R1": "PASS"},
    )
    assert result.status == "PASS"
    assert result.matrix.overall_status == "PASS"


def test_pipeline_status_pass_when_matrix_pass() -> None:
    requirements = ({"id": "R1", "criticality": "release_blocking"},)
    result = run_verifier_pipeline(
        requirements=requirements,
        static_results={"R1": "PASS"},
        behavioral_results={"R1": "PASS"},
        user_surface_results={"R1": "PASS"},
        live_flow_results={"R1": "PASS"},
        receipts_results={"R1": "PASS"},
    )
    assert result.matrix.overall_status == "PASS"
    assert result.status == "PASS"


def test_verifier_pipeline_bad_missing_dimensions_defaults_unverified() -> None:
    requirements = ({"id": "R1", "criticality": "release_blocking"},)
    result = run_verifier_pipeline(
        requirements=requirements,
        static_results={"R1": "PASS"},
        behavioral_results={},
        user_surface_results={},
        live_flow_results={},
        receipts_results={},
    )
    assert result.status == "UNVERIFIED"
    assert result.matrix.overall_status == "UNVERIFIED"
    assert result.matrix.completion_matrix[0]["overall"] == "UNVERIFIED"


def test_pipeline_status_unverified_when_matrix_unverified() -> None:
    requirements = ({"id": "R1", "criticality": "release_blocking"},)
    result = run_verifier_pipeline(
        requirements=requirements,
        static_results={"R1": "PASS"},
        behavioral_results={},
        user_surface_results={},
        live_flow_results={},
        receipts_results={},
    )
    assert result.matrix.overall_status == "UNVERIFIED"
    assert result.status == "UNVERIFIED"


def test_verifier_pipeline_corner_fail_propagates() -> None:
    requirements = ({"id": "R1", "criticality": "release_blocking"},)
    result = run_verifier_pipeline(
        requirements=requirements,
        static_results={"R1": "FAIL"},
        behavioral_results={"R1": "PASS"},
        user_surface_results={"R1": "PASS"},
        live_flow_results={"R1": "PASS"},
        receipts_results={"R1": "PASS"},
    )
    assert result.matrix.completion_matrix[0]["overall"] == "FAIL"
    assert result.status == "FAIL"


def test_pipeline_status_fail_when_matrix_fail() -> None:
    requirements = ({"id": "R1", "criticality": "release_blocking"},)
    result = run_verifier_pipeline(
        requirements=requirements,
        static_results={"R1": "FAIL"},
        behavioral_results={"R1": "PASS"},
        user_surface_results={"R1": "PASS"},
        live_flow_results={"R1": "PASS"},
        receipts_results={"R1": "PASS"},
    )
    assert result.matrix.overall_status == "FAIL"
    assert result.status == "FAIL"


def test_verifier_pipeline_edge_multiple_requirements() -> None:
    requirements = (
        {"id": "R1", "criticality": "release_blocking"},
        {"id": "R2", "criticality": "normal"},
    )
    result = run_verifier_pipeline(
        requirements=requirements,
        static_results={"R1": "PASS", "R2": "PASS"},
        behavioral_results={"R1": "PASS", "R2": "PASS"},
        user_surface_results={"R1": "PASS", "R2": "PASS"},
        live_flow_results={"R1": "PASS", "R2": "UNVERIFIED"},
        receipts_results={"R1": "PASS", "R2": "PASS"},
    )
    assert result.matrix.overall_status == "UNVERIFIED"
    assert any(row["id"] == "R2" and row["overall"] == "UNVERIFIED" for row in result.matrix.completion_matrix)
