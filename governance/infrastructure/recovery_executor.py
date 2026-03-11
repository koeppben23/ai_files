"""Recovery Executor — orchestrated failure recovery actions.

Bridges failure-model recovery strategies to executable infrastructure hooks.
This module is intentionally fail-closed: unsupported or unconfigured actions
return deterministic non-success results instead of silent no-ops.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Callable

from governance.domain.failure_model import FailureReport, RecoveryStrategy


@dataclass(frozen=True)
class RecoveryExecutionResult:
    strategy: RecoveryStrategy
    attempted: bool
    succeeded: bool
    message: str
    resume_token: str


def build_resume_token(*, run_id: str, repo_fingerprint: str, observed_at: str) -> str:
    payload = f"{repo_fingerprint}:{run_id}:{observed_at}"
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]
    return f"resume::{run_id}::{digest}"


def execute_recovery(
    *,
    report: FailureReport,
    observed_at: str,
    retry_by_overwrite: Callable[[], bool] | None = None,
    invalidate_and_rearchive: Callable[[], bool] | None = None,
    escalate_to_operator: Callable[[str], bool] | None = None,
) -> RecoveryExecutionResult:
    if not report.recovery_actions:
        token = build_resume_token(
            run_id=report.run_id,
            repo_fingerprint=report.repo_fingerprint,
            observed_at=observed_at,
        )
        return RecoveryExecutionResult(
            strategy=RecoveryStrategy.NO_RECOVERY,
            attempted=False,
            succeeded=False,
            message="no recovery actions in failure report",
            resume_token=token,
        )

    primary = report.recovery_actions[0].strategy
    token = build_resume_token(
        run_id=report.run_id,
        repo_fingerprint=report.repo_fingerprint,
        observed_at=observed_at,
    )

    if primary == RecoveryStrategy.RETRY_BY_OVERWRITE:
        if retry_by_overwrite is None:
            return RecoveryExecutionResult(primary, False, False, "retry hook not configured", token)
        ok = bool(retry_by_overwrite())
        return RecoveryExecutionResult(primary, True, ok, "retry attempted" if ok else "retry failed", token)

    if primary == RecoveryStrategy.INVALIDATE_AND_REARCHIVE:
        if invalidate_and_rearchive is None:
            return RecoveryExecutionResult(primary, False, False, "invalidate/rearchive hook not configured", token)
        ok = bool(invalidate_and_rearchive())
        return RecoveryExecutionResult(
            primary,
            True,
            ok,
            "invalidate+rearchive attempted" if ok else "invalidate+rearchive failed",
            token,
        )

    if primary == RecoveryStrategy.ESCALATE_TO_OPERATOR:
        if escalate_to_operator is None:
            return RecoveryExecutionResult(primary, False, False, "escalation hook not configured", token)
        ok = bool(escalate_to_operator(token))
        return RecoveryExecutionResult(primary, True, ok, "escalation attempted" if ok else "escalation failed", token)

    if primary in {RecoveryStrategy.MANUAL_INTERVENTION, RecoveryStrategy.NO_RECOVERY}:
        return RecoveryExecutionResult(primary, False, False, "manual intervention required", token)

    return RecoveryExecutionResult(primary, False, False, "unsupported recovery strategy", token)


__all__ = [
    "RecoveryExecutionResult",
    "build_resume_token",
    "execute_recovery",
]
