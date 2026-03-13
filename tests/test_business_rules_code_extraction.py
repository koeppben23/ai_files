from __future__ import annotations

from pathlib import Path

from governance.engine.business_rules_code_extraction import (
    discover_code_surfaces,
    extract_code_rule_candidates,
)
from governance.engine.business_rules_validation import (
    REASON_CODE_DOC_CONFLICT,
    extract_validated_business_rules_with_diagnostics,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_happy_extracts_code_rules_from_python_and_has_provenance(tmp_path: Path) -> None:
    _write(
        tmp_path / "src" / "policy.py",
        "def check_access(user):\n"
        "    if not user.has_permission('read'):\n"
        "        raise PermissionError('forbidden')\n",
    )

    report, diagnostics, ok = extract_validated_business_rules_with_diagnostics(tmp_path)

    assert ok is True
    assert report.has_code_extraction is True
    assert report.code_candidate_count >= 1
    assert report.code_valid_rule_count >= 1
    assert report.code_extraction_sufficient is True
    assert report.is_compliant is True
    assert diagnostics["code_extraction"]["is_sufficient"] is True


def test_happy_extracts_code_rules_from_go_and_typescript(tmp_path: Path) -> None:
    _write(
        tmp_path / "service" / "policy.go",
        "func Validate(amount int) error {\n"
        "    if amount > 1000 { return errors.New(\"exceeds\") }\n"
        "    return nil\n"
        "}\n",
    )
    _write(
        tmp_path / "web" / "workflow.ts",
        "export function transition(status: string) {\n"
        "  if (status === 'archived') throw new Error('invalid transition')\n"
        "}\n",
    )

    candidates, ok = extract_code_rule_candidates(tmp_path)
    surfaces = discover_code_surfaces(tmp_path)

    assert ok is True
    assert len(candidates) >= 2
    assert any(surface.language == "go" for surface in surfaces)
    assert any(surface.language == "typescript" for surface in surfaces)


def test_bad_code_repo_without_detectable_rules_fails_coverage(tmp_path: Path) -> None:
    _write(
        tmp_path / "src" / "plain.py",
        "def helper(x):\n"
        "    return x + 1\n",
    )

    report, diagnostics, ok = extract_validated_business_rules_with_diagnostics(tmp_path)

    assert ok is True
    assert report.has_code_extraction is True
    assert report.code_candidate_count == 0
    assert report.code_extraction_sufficient is False
    assert report.has_code_coverage_gap is True
    assert report.is_compliant is False
    assert "BUSINESS_RULES_CODE_COVERAGE_INSUFFICIENT" in report.reason_codes
    assert diagnostics["code_extraction"]["is_sufficient"] is False


def test_corner_doc_vs_code_conflict_blocks(tmp_path: Path) -> None:
    _write(
        tmp_path / "docs" / "rules.md",
        "# Business Rules\n"
        "- BR-001: Audit is optional for admin actions\n",
    )
    _write(
        tmp_path / "src" / "audit.py",
        "def save_audit(payload):\n"
        "    assert payload\n"
        "    log_event('audit')\n",
    )

    report, _, _ = extract_validated_business_rules_with_diagnostics(tmp_path)

    assert report.is_compliant is False
    assert report.has_code_doc_conflict is True
    assert REASON_CODE_DOC_CONFLICT in report.reason_codes


def test_edge_ignores_test_sources_for_code_extraction(tmp_path: Path) -> None:
    _write(
        tmp_path / "tests" / "test_policy.py",
        "def test_rule():\n"
        "    assert True\n",
    )

    report, diagnostics, ok = extract_validated_business_rules_with_diagnostics(tmp_path)

    assert ok is True
    assert report.code_surface_count == 0
    assert report.code_candidate_count == 0
    assert diagnostics["code_extraction"]["scanned_file_count"] == 0
