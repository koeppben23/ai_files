"""Static guard: all failure_codes referenced in shared rulebook YAMLs must
be members of the canonical reason-code registry.

This prevents YAML authors from inventing free-form codes that the engine
cannot recognise or route.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from governance.domain.reason_codes import CANONICAL_REASON_CODES

REPO_ROOT = Path(__file__).resolve().parents[1]
SHARED_YAMLS = sorted(
    (REPO_ROOT / "rulesets" / "profiles").glob("rules.*.yml")
)


def _extract_failure_codes(path: Path) -> list[str]:
    """Extract all ``failure_codes[].code`` values from a YAML rulebook."""
    text = path.read_text(encoding="utf-8")
    doc = yaml.safe_load(text)
    if not isinstance(doc, dict):
        return []
    codes: list[str] = []
    for entry in doc.get("failure_codes") or []:
        if isinstance(entry, dict) and "code" in entry:
            codes.append(str(entry["code"]).strip())
    return codes


@pytest.mark.governance
class TestFailureCodeGuard:
    """Every failure_code referenced in shared YAMLs must exist in the canonical registry."""

    def test_shared_yamls_exist(self) -> None:
        """Sanity: at least the 3 shared rulebooks should be found."""
        assert len(SHARED_YAMLS) >= 3, f"Expected >=3 shared YAMLs, found {len(SHARED_YAMLS)}"

    def test_all_failure_codes_are_canonical(self) -> None:
        """No YAML may reference a failure_code that is not in CANONICAL_REASON_CODES."""
        canonical_set = set(CANONICAL_REASON_CODES)
        violations: list[str] = []
        for yml_path in SHARED_YAMLS:
            codes = _extract_failure_codes(yml_path)
            for code in codes:
                if code not in canonical_set:
                    violations.append(f"{yml_path.name}: {code}")
        assert violations == [], (
            f"Non-canonical failure_codes found in YAMLs:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )

    def test_no_duplicate_failure_codes_per_yaml(self) -> None:
        """Each YAML should not list the same failure_code twice."""
        duplicates: list[str] = []
        for yml_path in SHARED_YAMLS:
            codes = _extract_failure_codes(yml_path)
            seen: set[str] = set()
            for code in codes:
                if code in seen:
                    duplicates.append(f"{yml_path.name}: duplicate {code}")
                seen.add(code)
        assert duplicates == [], (
            f"Duplicate failure_codes found:\n"
            + "\n".join(f"  - {d}" for d in duplicates)
        )
