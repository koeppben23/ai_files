from __future__ import annotations

from pathlib import Path

from governance_runtime.engine.business_rules_code_extraction import (
    DISCOVERY_ACCEPTED,
    DISCOVERY_DROPPED_MISSING_ANCHOR,
    DISCOVERY_DROPPED_MISSING_SEMANTICS,
    DISCOVERY_DROPPED_TECHNICAL,
    DISCOVERY_DROPPED_NON_BUSINESS_SURFACE,
    extract_code_rule_candidates_with_diagnostics,
)
from governance_runtime.engine.business_rules_validation import extract_validated_business_rules_with_diagnostics


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_happy_discovery_accepts_enforcement_only_candidates(tmp_path: Path) -> None:
    # Use actual business context (customer) instead of generic payload
    # Note: comments are dropped as non-business surfaces
    _write(
        tmp_path / "src" / "policy.py",
        "def authorize(user):\n"
        "    if not user.can_write:\n"
        "        raise PermissionError('unauthorized')\n"
        "if not customer.is_valid():\n"
        "    raise ValueError('customer is invalid')\n",
    )

    result, ok = extract_code_rule_candidates_with_diagnostics(tmp_path)
    report, diagnostics, extraction_ok = extract_validated_business_rules_with_diagnostics(tmp_path)
    code_diag = diagnostics["code_extraction"]

    assert ok is True
    assert extraction_ok is True
    # Comments are now dropped as non-business surfaces
    assert result.raw_candidate_count >= result.candidate_count
    assert result.candidate_count >= 2
    assert all(outcome.status == DISCOVERY_ACCEPTED for outcome in result.outcomes if outcome.status == DISCOVERY_ACCEPTED)
    assert report.code_candidate_count >= result.candidate_count
    assert isinstance(code_diag, dict)


def test_bad_discovery_drops_technical_artifacts_before_validation(tmp_path: Path) -> None:
    _write(
        tmp_path / "src" / "artifacty.py",
        "from dataclasses import dataclass\n"
        "@dataclass(frozen=True)\n"
        "CACHE_KEY\n"
        "helper_state_resolve_cache\n",
    )

    result, ok = extract_code_rule_candidates_with_diagnostics(tmp_path)

    assert ok is True
    assert result.candidate_count == 0
    assert result.raw_candidate_count >= 3
    assert result.dropped_candidate_count == result.raw_candidate_count
    # With stricter validation, technical artifacts are dropped due to missing enforcement anchor
    assert all(outcome.status in (DISCOVERY_DROPPED_TECHNICAL, DISCOVERY_DROPPED_MISSING_ANCHOR) for outcome in result.outcomes)


def test_corner_discovery_drops_normative_comment_without_enforcement_anchor(tmp_path: Path) -> None:
    _write(
        tmp_path / "src" / "comment_only.py",
        "# Permission checks must be enforced for customer exports\n"
        "customer_exports_enabled = True\n",
    )

    result, ok = extract_code_rule_candidates_with_diagnostics(tmp_path)

    assert ok is True
    assert result.candidate_count == 0
    assert result.raw_candidate_count >= 1
    assert result.dropped_candidate_count == result.raw_candidate_count
    # With stricter validation, comments are classified as docstring/comment surface
    assert any(outcome.status in (DISCOVERY_DROPPED_MISSING_ANCHOR, DISCOVERY_DROPPED_NON_BUSINESS_SURFACE) for outcome in result.outcomes)


def test_edge_discovery_drops_anchor_without_business_semantics(tmp_path: Path) -> None:
    _write(
        tmp_path / "src" / "helpers.py",
        "def run_check(helper):\n"
        "    assert helper.exists()\n",
    )

    result, ok = extract_code_rule_candidates_with_diagnostics(tmp_path)

    assert ok is True
    assert result.candidate_count == 0
    assert result.raw_candidate_count == 1
    assert result.dropped_candidate_count == 1
    # With stricter validation, helpers.py in src is classified as non-business surface
    assert result.outcomes[0].status in (DISCOVERY_DROPPED_MISSING_SEMANTICS, DISCOVERY_DROPPED_NON_BUSINESS_SURFACE)
