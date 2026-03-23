from __future__ import annotations

from governance_runtime.domain.failure_model import (
    FailureReport,
    RecoveryAction,
    RecoveryStrategy,
)
from governance_runtime.infrastructure.recovery_executor import (
    build_resume_token,
    execute_recovery,
    resume_recovery,
    validate_resume_token,
)


def _report(*, strategy: RecoveryStrategy) -> FailureReport:
    return FailureReport(
        run_id="run-1",
        repo_fingerprint="abc123def456abc123def456",
        observed_at="2026-03-11T09:00:00Z",
        recovery_actions=(
            RecoveryAction(
                strategy=strategy,
                description="d",
                retryable=True,
                max_retries=1,
            ),
        ),
    )


def test_build_resume_token_is_deterministic() -> None:
    a = build_resume_token(
        run_id="run-1",
        repo_fingerprint="abc123def456abc123def456",
        observed_at="2026-03-11T09:01:00Z",
    )
    b = build_resume_token(
        run_id="run-1",
        repo_fingerprint="abc123def456abc123def456",
        observed_at="2026-03-11T09:01:00Z",
    )
    assert a == b
    assert a.startswith("resume::run-1::")


def test_retry_by_overwrite_executes_when_hook_configured() -> None:
    report = _report(strategy=RecoveryStrategy.RETRY_BY_OVERWRITE)
    called = {"value": False}

    def _hook() -> bool:
        called["value"] = True
        return True

    result = execute_recovery(
        report=report,
        observed_at="2026-03-11T09:02:00Z",
        retry_by_overwrite=_hook,
    )
    assert called["value"] is True
    assert result.attempted is True
    assert result.succeeded is True


def test_retry_by_overwrite_fails_closed_without_hook() -> None:
    report = _report(strategy=RecoveryStrategy.RETRY_BY_OVERWRITE)
    result = execute_recovery(report=report, observed_at="2026-03-11T09:03:00Z")
    assert result.attempted is False
    assert result.succeeded is False


def test_invalidate_and_rearchive_executes_when_hook_configured() -> None:
    report = _report(strategy=RecoveryStrategy.INVALIDATE_AND_REARCHIVE)
    result = execute_recovery(
        report=report,
        observed_at="2026-03-11T09:04:00Z",
        invalidate_and_rearchive=lambda: True,
    )
    assert result.attempted is True
    assert result.succeeded is True


def test_escalate_to_operator_passes_resume_token() -> None:
    report = _report(strategy=RecoveryStrategy.ESCALATE_TO_OPERATOR)
    seen = {"token": ""}

    def _hook(token: str) -> bool:
        seen["token"] = token
        return True

    result = execute_recovery(
        report=report,
        observed_at="2026-03-11T09:05:00Z",
        escalate_to_operator=_hook,
    )
    assert result.succeeded is True
    assert seen["token"] == result.resume_token


def test_manual_intervention_returns_non_attempted_result() -> None:
    report = _report(strategy=RecoveryStrategy.MANUAL_INTERVENTION)
    result = execute_recovery(report=report, observed_at="2026-03-11T09:06:00Z")
    assert result.attempted is False
    assert result.succeeded is False


def test_no_recovery_actions_fail_closed() -> None:
    report = FailureReport(
        run_id="run-1",
        repo_fingerprint="abc123def456abc123def456",
        observed_at="2026-03-11T09:00:00Z",
        recovery_actions=(),
    )
    result = execute_recovery(report=report, observed_at="2026-03-11T09:07:00Z")
    assert result.strategy == RecoveryStrategy.NO_RECOVERY
    assert result.succeeded is False


def test_validate_resume_token_true_for_matching_payload() -> None:
    token = build_resume_token(
        run_id="run-1",
        repo_fingerprint="abc123def456abc123def456",
        observed_at="2026-03-11T09:08:00Z",
    )
    assert validate_resume_token(
        resume_token=token,
        run_id="run-1",
        repo_fingerprint="abc123def456abc123def456",
        observed_at="2026-03-11T09:08:00Z",
    ) is True


def test_resume_recovery_executes_when_token_valid() -> None:
    report = _report(strategy=RecoveryStrategy.RETRY_BY_OVERWRITE)
    token = build_resume_token(
        run_id=report.run_id,
        repo_fingerprint=report.repo_fingerprint,
        observed_at="2026-03-11T09:09:00Z",
    )
    called = {"value": False}

    def _hook() -> bool:
        called["value"] = True
        return True

    result = resume_recovery(
        report=report,
        observed_at="2026-03-11T09:09:00Z",
        resume_token=token,
        retry_by_overwrite=_hook,
    )
    assert called["value"] is True
    assert result.succeeded is True


def test_resume_recovery_fails_closed_on_invalid_token() -> None:
    report = _report(strategy=RecoveryStrategy.RETRY_BY_OVERWRITE)
    called = {"value": False}

    def _hook() -> bool:
        called["value"] = True
        return True

    result = resume_recovery(
        report=report,
        observed_at="2026-03-11T09:10:00Z",
        resume_token="resume::run-1::badbadbadbadbadbadba",
        retry_by_overwrite=_hook,
    )
    assert called["value"] is False
    assert result.attempted is False
    assert result.succeeded is False
    assert result.message == "invalid resume token"
