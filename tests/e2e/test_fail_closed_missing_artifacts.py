from governance_runtime.application.use_cases.artifact_backfill import BackfillSummary


def test_fail_closed_missing_artifacts_placeholder() -> None:
    summary = BackfillSummary(actions={}, missing=("repo-cache.yaml",), phase2_ok=False)
    assert summary.phase2_ok is False
