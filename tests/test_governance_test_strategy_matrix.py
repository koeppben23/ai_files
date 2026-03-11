from __future__ import annotations

from pathlib import Path


def test_recommended_contract_test_files_exist() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    expected = [
        "tests/test_run_manifest_contract.py",
        "tests/test_pr_record_contract.py",
        "tests/test_provenance_record_contract.py",
        "tests/test_ticket_record_contract.py",
        "tests/test_review_decision_record_contract.py",
        "tests/test_outcome_record_contract.py",
        "tests/test_evidence_index_contract.py",
        "tests/test_checksums_contract.py",
    ]
    for rel in expected:
        assert (repo_root / rel).is_file(), f"missing recommended test file: {rel}"


def test_coverage_has_happy_corner_edge_bad_buckets() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    coverage_sources = [
        repo_root / "tests/test_archive_export.py",
        repo_root / "tests/test_governance_orchestrator.py",
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in coverage_sources)
    assert "Happy" in text
    assert "Corner" in text
    assert "Edge" in text
    assert "Bad" in text
