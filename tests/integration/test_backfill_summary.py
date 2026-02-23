from kernel.use_cases.artifact_backfill import BackfillSummary


def test_backfill_summary_defaults_fail_closed() -> None:
    summary = BackfillSummary()
    assert summary.phase2_ok is False
