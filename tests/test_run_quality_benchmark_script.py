from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_quality_benchmark.py"
PACK = Path(__file__).resolve().parents[1] / "diagnostics" / "PYTHON_QUALITY_BENCHMARK_PACK.json"


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=False,
        text=True,
        capture_output=True,
        cwd=str(SCRIPT.parents[1]),
    )


@pytest.mark.governance
def test_runner_not_verified_when_required_claim_missing():
    result = _run(
        [
            "--pack",
            str(PACK),
            "--observed-claim",
            "claim/tests-green",
            "--criterion-score",
            "PYR-1=1.0",
            "--criterion-score",
            "PYR-2=1.0",
            "--criterion-score",
            "PYR-3=1.0",
            "--criterion-score",
            "PYR-4=1.0",
            "--criterion-score",
            "PYR-5=1.0",
        ]
    )
    payload = json.loads(result.stdout)
    assert result.returncode == 2
    assert payload["status"] == "NOT_VERIFIED"
    assert "claim/static-clean" in payload["missing_required_claim_ids"]


@pytest.mark.governance
def test_runner_not_verified_when_required_claim_is_stale():
    result = _run(
        [
            "--pack",
            str(PACK),
            "--observed-claim",
            "claim/tests-green",
            "--observed-claim",
            "claim/static-clean",
            "--observed-claim",
            "claim/no-drift",
            "--stale-claim",
            "claim/no-drift",
            "--criterion-score",
            "PYR-1=1.0",
            "--criterion-score",
            "PYR-2=1.0",
            "--criterion-score",
            "PYR-3=1.0",
            "--criterion-score",
            "PYR-4=1.0",
            "--criterion-score",
            "PYR-5=1.0",
        ]
    )
    payload = json.loads(result.stdout)
    assert result.returncode == 2
    assert payload["status"] == "NOT_VERIFIED"
    assert payload["stale_required_claim_ids"] == ["claim/no-drift"]


@pytest.mark.governance
def test_runner_passes_with_full_claims_and_threshold_score(tmp_path: Path):
    output = tmp_path / "results" / "python-pack.json"
    result = _run(
        [
            "--pack",
            str(PACK),
            "--observed-claim",
            "claim/tests-green",
            "--observed-claim",
            "claim/static-clean",
            "--observed-claim",
            "claim/no-drift",
            "--criterion-score",
            "PYR-1=0.9",
            "--criterion-score",
            "PYR-2=0.9",
            "--criterion-score",
            "PYR-3=0.9",
            "--criterion-score",
            "PYR-4=0.9",
            "--criterion-score",
            "PYR-5=0.9",
            "--output",
            str(output),
        ]
    )
    payload = json.loads(result.stdout)
    assert result.returncode == 0
    assert payload["status"] == "PASS"
    assert payload["score_ratio"] >= 0.85
    assert output.exists()


@pytest.mark.governance
def test_runner_fails_closed_on_invalid_score_argument():
    result = _run(["--pack", str(PACK), "--criterion-score", "PYR-1=not-a-number"])
    payload = json.loads(result.stdout)
    assert result.returncode == 4
    assert payload["status"] == "BLOCKED"


@pytest.mark.governance
def test_runner_derives_claims_from_evidence_dir(tmp_path: Path):
    evidence = tmp_path / "evidence"
    evidence.mkdir(parents=True)
    (evidence / "pytest.exitcode").write_text("0\n", encoding="utf-8")
    (evidence / "governance_lint.exitcode").write_text("0\n", encoding="utf-8")
    (evidence / "drift.txt").write_text("", encoding="utf-8")

    result = _run(
        [
            "--pack",
            str(PACK),
            "--evidence-dir",
            str(evidence),
            "--review-mode",
            "--criterion-score",
            "PYR-1=0.9",
            "--criterion-score",
            "PYR-2=0.9",
            "--criterion-score",
            "PYR-3=0.9",
            "--criterion-score",
            "PYR-4=0.9",
            "--criterion-score",
            "PYR-5=0.9",
        ]
    )

    payload = json.loads(result.stdout)
    assert result.returncode == 0
    assert payload["status"] == "PASS"
    assert payload["missing_required_claim_ids"] == []


@pytest.mark.governance
def test_runner_blocks_review_mode_without_evidence_dir():
    result = _run(["--pack", str(PACK), "--review-mode", "--criterion-score", "PYR-1=0.9"])
    payload = json.loads(result.stdout)
    assert result.returncode == 4
    assert payload["status"] == "BLOCKED"
    assert "requires --evidence-dir" in payload["message"]
