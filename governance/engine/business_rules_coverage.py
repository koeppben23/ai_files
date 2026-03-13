from __future__ import annotations

from dataclasses import dataclass

from governance.engine.business_rules_code_extraction import CodeSurface


RC_CODE_EXTRACTION_NOT_RUN = "BUSINESS_RULES_CODE_EXTRACTION_NOT_RUN"
RC_CODE_COVERAGE_INSUFFICIENT = "BUSINESS_RULES_CODE_COVERAGE_INSUFFICIENT"
RC_CODE_PROVENANCE_MISSING = "BUSINESS_RULES_CODE_PROVENANCE_MISSING"


@dataclass(frozen=True)
class CodeExtractionCoverage:
    scanned_surfaces: tuple[CodeSurface, ...]
    scanned_file_count: int
    candidate_count: int
    missing_expected_surfaces: tuple[str, ...]
    reason_codes: tuple[str, ...]
    is_sufficient: bool


def evaluate_code_extraction_coverage(
    *,
    scanned_surfaces: list[CodeSurface],
    candidate_count: int,
    extraction_ran: bool,
    has_provenance_gaps: bool = False,
) -> CodeExtractionCoverage:
    reasons: list[str] = []
    if not extraction_ran:
        reasons.append(RC_CODE_EXTRACTION_NOT_RUN)

    scanned_file_count = len(scanned_surfaces)
    missing_expected_surfaces: list[str] = []

    if scanned_file_count > 0 and candidate_count <= 0:
        reasons.append(RC_CODE_COVERAGE_INSUFFICIENT)

    # Expectation model: track strong domain-oriented surfaces.
    present_types = {surface.surface_type for surface in scanned_surfaces}
    expected_types = {"validator", "permissions", "workflow"}
    for expected in ("validator", "permissions", "workflow"):
        if expected not in present_types and scanned_file_count > 0:
            missing_expected_surfaces.append(expected)

    # Fail-closed in sensible coverage scenarios:
    # - If repo is non-trivial (>= 8 scanned code/config files), missing strong
    #   surfaces is a blocker.
    # - If at least one strong surface exists but others are missing, treat as
    #   partial-coverage gap and block.
    present_expected = len(present_types & expected_types)
    if missing_expected_surfaces and (
        scanned_file_count >= 8
        or present_expected >= 1
    ):
        reasons.append(RC_CODE_COVERAGE_INSUFFICIENT)

    if has_provenance_gaps:
        reasons.append(RC_CODE_PROVENANCE_MISSING)

    return CodeExtractionCoverage(
        scanned_surfaces=tuple(scanned_surfaces),
        scanned_file_count=scanned_file_count,
        candidate_count=max(candidate_count, 0),
        missing_expected_surfaces=tuple(sorted(set(missing_expected_surfaces))),
        reason_codes=tuple(dict.fromkeys(reasons)),
        is_sufficient=(len(reasons) == 0),
    )


def coverage_to_payload(coverage: CodeExtractionCoverage) -> dict[str, object]:
    return {
        "scanned_file_count": coverage.scanned_file_count,
        "candidate_count": coverage.candidate_count,
        "missing_expected_surfaces": list(coverage.missing_expected_surfaces),
        "reason_codes": list(coverage.reason_codes),
        "is_sufficient": coverage.is_sufficient,
        "scanned_surfaces": [
            {
                "path": item.path,
                "language": item.language,
                "surface_type": item.surface_type,
            }
            for item in coverage.scanned_surfaces
        ],
    }
