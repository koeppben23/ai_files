"""Plan compliance validation at Phase 6 entry.

Compares the persisted plan-record (touched_surface, test_strategy,
contracts) against actual implementation evidence to detect drift
between planned and actual changes.

Validation runs automatically at Phase 6 entry with tiered results:
- compliant: no significant deviations detected
- drift-detected: minor deviations (WARN, non-blocking)
- major-deviation: significant deviations (BLOCKED in pipeline,
  override-able in user mode)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PlanComplianceReport:
    """Full compliance report for plan-vs-implementation validation."""

    status: str  # "compliant" | "drift-detected" | "major-deviation" | "no-plan"
    reason: str
    plan_version: int | None
    files_planned: tuple[str, ...]
    files_actual: tuple[str, ...]
    files_unplanned: tuple[str, ...]
    files_missing: tuple[str, ...]
    contracts_planned: tuple[str, ...]
    contracts_actual: tuple[str, ...]
    contracts_unplanned: tuple[str, ...]
    contracts_missing: tuple[str, ...]
    test_strategy_present: bool
    test_files_found: tuple[str, ...]
    drift_details: tuple[str, ...] = field(default=())


# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------

# If more than this fraction of actual files are unplanned, it's major drift
_UNPLANNED_FILE_RATIO_MAJOR = 0.5
# If any planned contract is missing from actual, it's always major drift
_MISSING_CONTRACT_IS_MAJOR = True
# Minimum number of unplanned files to trigger drift (ignore trivial additions)
_UNPLANNED_FILE_MIN_COUNT = 3


# ---------------------------------------------------------------------------
# Core validation
# ---------------------------------------------------------------------------

def validate_plan_compliance(
    *,
    plan_record: Mapping[str, Any] | None,
    actual_files_changed: Sequence[str],
    actual_contracts_changed: Sequence[str] | None = None,
    test_files_found: Sequence[str] | None = None,
) -> PlanComplianceReport:
    """Validate implementation against persisted plan-record.

    Args:
        plan_record: The loaded plan-record.json dict (or None if
            no plan record exists).
        actual_files_changed: Files actually changed (from git diff
            or equivalent).
        actual_contracts_changed: API/contract files actually changed
            (optional; empty list if not provided).
        test_files_found: Test files found in the changeset (optional).

    Returns:
        PlanComplianceReport with tiered status and details.
    """
    if plan_record is None:
        return PlanComplianceReport(
            status="no-plan",
            reason="no-plan-record-found",
            plan_version=None,
            files_planned=(),
            files_actual=tuple(actual_files_changed),
            files_unplanned=(),
            files_missing=(),
            contracts_planned=(),
            contracts_actual=tuple(actual_contracts_changed or []),
            contracts_unplanned=(),
            contracts_missing=(),
            test_strategy_present=False,
            test_files_found=tuple(test_files_found or []),
        )

    versions = plan_record.get("versions", [])
    if not versions:
        return PlanComplianceReport(
            status="no-plan",
            reason="plan-record-has-no-versions",
            plan_version=None,
            files_planned=(),
            files_actual=tuple(actual_files_changed),
            files_unplanned=(),
            files_missing=(),
            contracts_planned=(),
            contracts_actual=tuple(actual_contracts_changed or []),
            contracts_unplanned=(),
            contracts_missing=(),
            test_strategy_present=False,
            test_files_found=tuple(test_files_found or []),
        )

    # Use the latest version
    latest = versions[-1]
    plan_version_num = latest.get("version", 0)

    # Extract planned surfaces
    touched = latest.get("touched_surface") or {}
    planned_files = set(_normalize_paths(touched.get("files_planned", [])))
    planned_contracts = set(_normalize_paths(touched.get("contracts_planned", [])))

    # Normalize actuals
    actual_files = set(_normalize_paths(actual_files_changed))
    actual_contracts = set(_normalize_paths(actual_contracts_changed or []))
    test_files = tuple(test_files_found or [])

    # Compute deviations
    files_unplanned = actual_files - planned_files
    files_missing = planned_files - actual_files
    contracts_unplanned = actual_contracts - planned_contracts
    contracts_missing = planned_contracts - actual_contracts

    # Check test strategy
    test_strategy = latest.get("test_strategy", [])
    test_strategy_present = bool(test_strategy)

    # Collect drift details
    drift_details: list[str] = []

    if files_unplanned:
        drift_details.append(
            f"{len(files_unplanned)} file(s) changed but not in plan: "
            + ", ".join(sorted(files_unplanned)[:5])
        )
    if files_missing:
        drift_details.append(
            f"{len(files_missing)} planned file(s) not changed: "
            + ", ".join(sorted(files_missing)[:5])
        )
    if contracts_unplanned:
        drift_details.append(
            f"{len(contracts_unplanned)} contract(s) changed but not in plan: "
            + ", ".join(sorted(contracts_unplanned)[:5])
        )
    if contracts_missing:
        drift_details.append(
            f"{len(contracts_missing)} planned contract(s) not changed: "
            + ", ".join(sorted(contracts_missing)[:5])
        )

    # Determine status
    status = _determine_status(
        files_unplanned=files_unplanned,
        files_missing=files_missing,
        contracts_unplanned=contracts_unplanned,
        contracts_missing=contracts_missing,
        actual_files_count=len(actual_files),
        planned_files_count=len(planned_files),
    )

    reason = "compliant" if status == "compliant" else "; ".join(drift_details) if drift_details else "unknown-drift"

    return PlanComplianceReport(
        status=status,
        reason=reason,
        plan_version=plan_version_num,
        files_planned=tuple(sorted(planned_files)),
        files_actual=tuple(sorted(actual_files)),
        files_unplanned=tuple(sorted(files_unplanned)),
        files_missing=tuple(sorted(files_missing)),
        contracts_planned=tuple(sorted(planned_contracts)),
        contracts_actual=tuple(sorted(actual_contracts)),
        contracts_unplanned=tuple(sorted(contracts_unplanned)),
        contracts_missing=tuple(sorted(contracts_missing)),
        test_strategy_present=test_strategy_present,
        test_files_found=tuple(test_files),
        drift_details=tuple(drift_details),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_paths(paths: Sequence[str]) -> list[str]:
    """Normalize file paths for comparison (forward slashes, lowercase)."""
    result: list[str] = []
    for p in paths:
        if not isinstance(p, str):
            continue
        normalized = p.replace("\\", "/").strip().rstrip("/")
        result.append(normalized)
    return result


def _determine_status(
    *,
    files_unplanned: set[str],
    files_missing: set[str],
    contracts_unplanned: set[str],
    contracts_missing: set[str],
    actual_files_count: int,
    planned_files_count: int,
) -> str:
    """Determine the compliance status based on deviation severity.

    Tiered logic:
    - compliant: no deviations
    - drift-detected: minor deviations (small number of unplanned files,
      no missing contracts)
    - major-deviation: significant deviations (high unplanned ratio,
      missing contracts, or many missing planned files)
    """
    has_file_drift = bool(files_unplanned) or bool(files_missing)
    has_contract_drift = bool(contracts_unplanned) or bool(contracts_missing)

    if not has_file_drift and not has_contract_drift:
        return "compliant"

    # Missing contracts are always major (contracts are critical boundaries)
    if _MISSING_CONTRACT_IS_MAJOR and contracts_missing:
        return "major-deviation"

    # Unplanned contracts are major
    if contracts_unplanned:
        return "major-deviation"

    # Check unplanned file ratio
    if files_unplanned and actual_files_count > 0:
        unplanned_ratio = len(files_unplanned) / actual_files_count
        if (
            unplanned_ratio >= _UNPLANNED_FILE_RATIO_MAJOR
            and len(files_unplanned) >= _UNPLANNED_FILE_MIN_COUNT
        ):
            return "major-deviation"

    # Check if most planned files are missing (plan was abandoned)
    if files_missing and planned_files_count > 0:
        missing_ratio = len(files_missing) / planned_files_count
        if missing_ratio >= _UNPLANNED_FILE_RATIO_MAJOR:
            return "major-deviation"

    # Everything else is drift but not major
    return "drift-detected"
