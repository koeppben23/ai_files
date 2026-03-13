from __future__ import annotations

from pathlib import Path

from governance.engine.business_rules_hydration import hydrate_business_rules_state_from_artifacts


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_happy_hydration_accepts_valid_business_rules_inventory(tmp_path: Path) -> None:
    status = tmp_path / "business-rules-status.md"
    inv = tmp_path / "business-rules.md"
    _write(status, "Outcome: extracted\nExecutionEvidence: true\n")
    _write(inv, "- BR-001: Access must be checked\n- BR-002: Audit is mandatory\n")
    state: dict[str, object] = {}

    ok = hydrate_business_rules_state_from_artifacts(state=state, status_path=status, inventory_path=inv)

    assert ok is True
    business = state["BusinessRules"]
    assert isinstance(business, dict)
    assert business["ExtractedCount"] == 2


def test_corner_hydration_rejects_non_rule_fragments(tmp_path: Path) -> None:
    status = tmp_path / "business-rules-status.md"
    inv = tmp_path / "business-rules.md"
    _write(status, "Outcome: extracted\nExecutionEvidence: true\n")
    _write(inv, "- tests/test_engine_boundaries.py:173\n- artifacts/writers/business_rules.py:12\n")
    state: dict[str, object] = {}

    ok = hydrate_business_rules_state_from_artifacts(state=state, status_path=status, inventory_path=inv)

    assert ok is True
    assert state["BusinessRules"]["Outcome"] == "gap-detected"  # type: ignore[index]


def test_edge_hydration_accepts_rule_prefix_lines(tmp_path: Path) -> None:
    status = tmp_path / "business-rules-status.md"
    inv = tmp_path / "business-rules.md"
    _write(status, "Outcome: extracted\nExecutionEvidence: true\n")
    _write(inv, "Rule: BR-010: Invoices must remain immutable\n")
    state: dict[str, object] = {}

    ok = hydrate_business_rules_state_from_artifacts(state=state, status_path=status, inventory_path=inv)

    assert ok is True
    business = state["BusinessRules"]
    assert isinstance(business, dict)
    assert business["ExtractedCount"] == 1


def test_bad_hydration_requires_execution_evidence_for_extracted(tmp_path: Path) -> None:
    status = tmp_path / "business-rules-status.md"
    inv = tmp_path / "business-rules.md"
    _write(status, "Outcome: extracted\nExecutionEvidence: false\n")
    _write(inv, "- BR-900: Audit entries are immutable\n")
    state: dict[str, object] = {}

    ok = hydrate_business_rules_state_from_artifacts(state=state, status_path=status, inventory_path=inv)

    assert ok is True
    assert state["BusinessRules"]["Outcome"] == "gap-detected"  # type: ignore[index]


def test_bad_hydration_rejects_known_artifact_patterns(tmp_path: Path) -> None:
    status = tmp_path / "business-rules-status.md"
    inv = tmp_path / "business-rules.md"
    _write(status, "Outcome: extracted\nExecutionEvidence: true\n")
    _write(
        inv,
        "- BR-001: Inventory scaffold\n"
        '- BR-002: Access must be checked\\n- BR-003: Audit is mandatory\\n")\n',
    )
    state: dict[str, object] = {}

    ok = hydrate_business_rules_state_from_artifacts(state=state, status_path=status, inventory_path=inv)

    assert ok is True
    assert state["BusinessRules"]["Outcome"] == "gap-detected"  # type: ignore[index]


def test_corner_hydration_records_validation_report_fields(tmp_path: Path) -> None:
    status = tmp_path / "business-rules-status.md"
    inv = tmp_path / "business-rules.md"
    _write(status, "Outcome: extracted\nExecutionEvidence: true\n")
    _write(inv, "- BR-010: A release must require four eyes before production deploy\n")
    state: dict[str, object] = {}

    ok = hydrate_business_rules_state_from_artifacts(state=state, status_path=status, inventory_path=inv)

    assert ok is True
    business = state["BusinessRules"]
    assert isinstance(business, dict)
    assert business["QualityGate"] == "passed"
    assert business["ValidationReport"]["is_compliant"] is True


def test_bad_hydration_blocks_when_code_coverage_is_insufficient(tmp_path: Path) -> None:
    status = tmp_path / "business-rules-status.md"
    inv = tmp_path / "business-rules.md"
    _write(
        status,
        "Outcome: extracted\n"
        "ExecutionEvidence: true\n"
        "CodeExtractionRun: true\n"
        "CodeCoverageSufficient: false\n"
        "CodeCandidateCount: 0\n"
        "CodeSurfaceCount: 5\n"
        "MissingCodeSurfaces: validator, permissions\n",
    )
    _write(inv, "- BR-010: A release must require four eyes before production deploy\n")
    state: dict[str, object] = {}

    ok = hydrate_business_rules_state_from_artifacts(state=state, status_path=status, inventory_path=inv)

    assert ok is True
    assert state["BusinessRules"]["Outcome"] == "gap-detected"  # type: ignore[index]


def test_edge_hydration_persists_code_coverage_fields(tmp_path: Path) -> None:
    status = tmp_path / "business-rules-status.md"
    inv = tmp_path / "business-rules.md"
    _write(
        status,
        "Outcome: extracted\n"
        "ExecutionEvidence: true\n"
        "CodeExtractionRun: true\n"
        "CodeCoverageSufficient: true\n"
        "CodeCandidateCount: 3\n"
        "CodeSurfaceCount: 7\n"
        "MissingCodeSurfaces: none\n",
    )
    _write(inv, "- BR-011: Audit entries must remain immutable\n")
    state: dict[str, object] = {}

    ok = hydrate_business_rules_state_from_artifacts(state=state, status_path=status, inventory_path=inv)

    assert ok is True
    business = state["BusinessRules"]
    assert isinstance(business, dict)
    assert business["CodeExtractionRun"] is True
    assert business["CodeCoverageSufficient"] is True
    assert business["CodeCandidateCount"] == 3
    assert business["CodeSurfaceCount"] == 7
