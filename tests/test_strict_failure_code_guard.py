"""Static guard: all failure_codes referenced in shared rulebook YAMLs must
be members of the canonical reason-code registry.

This prevents YAML authors from inventing free-form codes that the engine
cannot recognise or route.
"""
from __future__ import annotations

from pathlib import Path
import re

import pytest

from governance.domain.reason_codes import CANONICAL_REASON_CODES
from tests.util import get_ruleset_profiles_path

SHARED_YAMLS = sorted(
    get_ruleset_profiles_path().glob("rules.*.yml")
)


def _extract_failure_codes(path: Path) -> list[str]:
    """Extract ``failure_codes[].code`` values from rulebook YAML text.

    The spec-guards CI lane installs only ``pytest`` for speed, so this parser
    intentionally avoids external YAML dependencies.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    in_failure_codes = False
    codes: list[str] = []

    for line in lines:
        if re.match(r"^failure_codes:\s*$", line):
            in_failure_codes = True
            continue
        if not in_failure_codes:
            continue
        if line and not line.startswith(" ") and not line.startswith("-"):
            break

        match = re.match(r"^\s*-\s*code:\s*(\S.*?)\s*$", line)
        if match:
            codes.append(match.group(1).strip().strip('"').strip("'"))

    return codes


def _collect_pass_criteria_violations(path: Path) -> list[str]:
    """Validate pass_criteria entries in constrained rulebook YAML layout."""
    lines = path.read_text(encoding="utf-8").splitlines()
    violations: list[str] = []

    current_phase = "?"
    in_pass_criteria = False
    pass_indent = -1

    item_active = False
    item_has_criterion_key = False

    def flush_item() -> None:
        nonlocal item_active, item_has_criterion_key
        if item_active and not item_has_criterion_key:
            violations.append(
                f"{path.name} ({current_phase}): pass_criterion missing required 'criterion_key'"
            )
        item_active = False
        item_has_criterion_key = False

    for raw in lines:
        phase_match = re.match(r"^\s*-\s*phase:\s*(\S.*?)\s*$", raw)
        if phase_match:
            flush_item()
            current_phase = phase_match.group(1).strip().strip('"').strip("'")
            in_pass_criteria = False
            pass_indent = -1
            continue

        if not in_pass_criteria:
            pass_match = re.match(r"^(\s*)pass_criteria:\s*$", raw)
            if pass_match:
                in_pass_criteria = True
                pass_indent = len(pass_match.group(1))
                flush_item()
            continue

        # Leaving the pass_criteria block (dedent to same-or-less indent)
        if raw.strip() and (len(raw) - len(raw.lstrip(" "))) <= pass_indent:
            flush_item()
            in_pass_criteria = False
            pass_indent = -1
            continue

        item_match = re.match(r"^\s*-\s*criterion_key:\s*(\S.*?)\s*$", raw)
        if item_match:
            flush_item()
            item_active = True
            item_has_criterion_key = True
            continue

        # New list item under pass_criteria that is not criterion_key.
        if re.match(r"^\s*-\s*\S", raw):
            flush_item()
            item_active = True

        if "criterion_id:" in raw:
            violations.append(
                f"{path.name} ({current_phase}): uses deprecated 'criterion_id' — must be 'criterion_key'"
            )
        if "evidence_artifact:" in raw:
            violations.append(
                f"{path.name} ({current_phase}): uses deprecated 'evidence_artifact' — must be 'artifact_kind'"
            )
        if "criterion_key:" in raw:
            item_has_criterion_key = True

    flush_item()
    return violations


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

    def test_pass_criteria_use_criterion_key_not_criterion_id(self) -> None:
        """v1.2.0 schema renamed criterion_id → criterion_key and
        evidence_artifact → artifact_kind.  No YAML may use the old names."""
        violations: list[str] = []
        for yml_path in SHARED_YAMLS:
            violations.extend(_collect_pass_criteria_violations(yml_path))
        assert violations == [], (
            "Deprecated or missing fields in pass_criteria:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )
