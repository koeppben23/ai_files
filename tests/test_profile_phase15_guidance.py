"""Tests for Phase 1.5 Business Rules Discovery guidance in stack profiles.

Validates that backend-java, backend-python, and postgres-liquibase profiles
contain correctly structured Phase 1.5 sections with stack-specific patterns.

Categories: Happy (structural correctness), Bad (exclusion enforcement),
Corner (cross-profile consistency), Edge (format/encoding robustness).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.util import get_profiles_path

PROFILES_DIR = get_profiles_path()

JAVA_PROFILE = PROFILES_DIR / "rules.backend-java.md"
PYTHON_PROFILE = PROFILES_DIR / "rules.backend-python.md"
POSTGRES_PROFILE = PROFILES_DIR / "rules.postgres-liquibase.md"

PHASE_15_HEADING = "### Phase 1.5: Business Rules Discovery"


def _read_profile(path: Path) -> str:
    assert path.exists(), f"Profile not found: {path}"
    return path.read_text(encoding="utf-8")


def _extract_phase15_section(content: str) -> str:
    """Extract the Phase 1.5 section body (from heading to next ## or ### heading)."""
    pattern = re.compile(
        r"^### Phase 1\.5: Business Rules Discovery\s*\n(.*?)(?=\n##|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m = pattern.search(content)
    assert m is not None, "Phase 1.5 section not found"
    return m.group(1)


# ---------------------------------------------------------------------------
# Happy path: structural correctness
# ---------------------------------------------------------------------------


class TestHappyStructure:
    """Verify each profile contains a well-formed Phase 1.5 section."""

    def test_java_has_phase15_heading(self):
        content = _read_profile(JAVA_PROFILE)
        assert PHASE_15_HEADING in content

    def test_python_has_phase15_heading(self):
        content = _read_profile(PYTHON_PROFILE)
        assert PHASE_15_HEADING in content

    def test_postgres_has_phase15_heading(self):
        content = _read_profile(POSTGRES_PROFILE)
        assert PHASE_15_HEADING in content

    def test_java_phase15_under_phase_integration(self):
        content = _read_profile(JAVA_PROFILE)
        phase_int_pos = content.index("## Phase integration (binding)")
        phase15_pos = content.index(PHASE_15_HEADING)
        # Phase 1.5 must be nested under Phase integration
        assert phase15_pos > phase_int_pos
        # And before the next top-level section
        next_h2_match = re.search(
            r"\n## ", content[phase15_pos + len(PHASE_15_HEADING):]
        )
        assert next_h2_match is not None, "Expected a ## section after Phase 1.5"

    def test_python_phase15_under_phase_integration(self):
        content = _read_profile(PYTHON_PROFILE)
        phase_int_pos = content.index("## Phase integration (binding)")
        phase15_pos = content.index(PHASE_15_HEADING)
        assert phase15_pos > phase_int_pos
        next_h2_match = re.search(
            r"\n## ", content[phase15_pos + len(PHASE_15_HEADING):]
        )
        assert next_h2_match is not None

    def test_java_has_bullet_list_of_patterns(self):
        content = _read_profile(JAVA_PROFILE)
        section = _extract_phase15_section(content)
        bullets = [l for l in section.splitlines() if l.strip().startswith("- ")]
        # At least 6 Java pattern bullets (annotations, validators, JPA, enums, exceptions, guards)
        assert len(bullets) >= 6, f"Expected >=6 pattern bullets, got {len(bullets)}"

    def test_python_has_bullet_list_of_patterns(self):
        content = _read_profile(PYTHON_PROFILE)
        section = _extract_phase15_section(content)
        bullets = [l for l in section.splitlines() if l.strip().startswith("- ")]
        # At least 6 Python pattern bullets
        assert len(bullets) >= 6, f"Expected >=6 pattern bullets, got {len(bullets)}"

    def test_java_references_business_rule_candidates(self):
        content = _read_profile(JAVA_PROFILE)
        section = _extract_phase15_section(content)
        assert "BusinessRuleCandidates" in section

    def test_python_references_business_rule_candidates(self):
        content = _read_profile(PYTHON_PROFILE)
        section = _extract_phase15_section(content)
        assert "BusinessRuleCandidates" in section


# ---------------------------------------------------------------------------
# Happy path: stack-specific pattern keywords
# ---------------------------------------------------------------------------


class TestHappyJavaPatterns:
    """Verify Java profile mentions key Java-specific patterns."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.section = _extract_phase15_section(_read_profile(JAVA_PROFILE))

    def test_bean_validation_annotations(self):
        assert "@NotNull" in self.section
        assert "@Min" in self.section or "@Max" in self.section

    def test_constraint_validator(self):
        assert "ConstraintValidator" in self.section

    def test_spring_validator(self):
        assert "Validator" in self.section

    def test_jpa_column_constraints(self):
        assert "@Column" in self.section or "@UniqueConstraint" in self.section

    def test_enum_state_machines(self):
        assert "Enum" in self.section or "enum" in self.section

    def test_domain_exceptions(self):
        assert "throw" in self.section.lower() or "exception" in self.section.lower()

    def test_guard_clauses(self):
        assert "guard" in self.section.lower() or "Guard" in self.section

    def test_spring_security(self):
        assert "@PreAuthorize" in self.section or "@Secured" in self.section


class TestHappyPythonPatterns:
    """Verify Python profile mentions key Python-specific patterns."""

    @pytest.fixture(autouse=True)
    def _load(self):
        self.section = _extract_phase15_section(_read_profile(PYTHON_PROFILE))

    def test_pydantic_validators(self):
        assert "Pydantic" in self.section or "pydantic" in self.section
        assert "@validator" in self.section or "@field_validator" in self.section

    def test_django_constraints(self):
        assert "Django" in self.section or "django" in self.section
        assert "CheckConstraint" in self.section or "UniqueConstraint" in self.section

    def test_fastapi_validation(self):
        assert "FastAPI" in self.section or "fastapi" in self.section

    def test_sqlalchemy_validates(self):
        assert "SQLAlchemy" in self.section or "sqlalchemy" in self.section

    def test_dataclass_post_init(self):
        assert "__post_init__" in self.section

    def test_domain_exceptions(self):
        assert "raise" in self.section.lower() or "exception" in self.section.lower()

    def test_guard_clauses(self):
        assert "guard" in self.section.lower() or "Guard" in self.section

    def test_enum_state_machines(self):
        assert "Enum" in self.section or "enum" in self.section


# ---------------------------------------------------------------------------
# Bad path: exclusion enforcement
# ---------------------------------------------------------------------------


class TestBadExclusions:
    """Verify exclusion lists are present and correct."""

    def test_java_has_exclusions_section(self):
        content = _read_profile(JAVA_PROFILE)
        section = _extract_phase15_section(content)
        assert "Exclusions" in section or "do NOT extract" in section

    def test_python_has_exclusions_section(self):
        content = _read_profile(PYTHON_PROFILE)
        section = _extract_phase15_section(content)
        assert "Exclusions" in section or "do NOT extract" in section

    def test_java_excludes_todo_fixme(self):
        content = _read_profile(JAVA_PROFILE)
        section = _extract_phase15_section(content)
        assert "TODO" in section and "FIXME" in section

    def test_python_excludes_todo_fixme(self):
        content = _read_profile(PYTHON_PROFILE)
        section = _extract_phase15_section(content)
        assert "TODO" in section and "FIXME" in section

    def test_java_excludes_generic_exceptions(self):
        content = _read_profile(JAVA_PROFILE)
        section = _extract_phase15_section(content)
        assert "NullPointerException" in section or "generic" in section.lower()

    def test_python_excludes_generic_exceptions(self):
        content = _read_profile(PYTHON_PROFILE)
        section = _extract_phase15_section(content)
        assert "ValueError" in section or "TypeError" in section

    def test_java_excludes_infrastructure_annotations(self):
        content = _read_profile(JAVA_PROFILE)
        section = _extract_phase15_section(content)
        assert "@Autowired" in section or "infrastructure" in section.lower()

    def test_python_excludes_infrastructure_decorators(self):
        content = _read_profile(PYTHON_PROFILE)
        section = _extract_phase15_section(content)
        assert "@app.route" in section or "infrastructure" in section.lower()


# ---------------------------------------------------------------------------
# Corner cases: cross-profile consistency
# ---------------------------------------------------------------------------


class TestCornerCrossProfile:
    """Verify structural consistency across all three profiles with Phase 1.5."""

    def test_all_profiles_use_same_heading_text(self):
        """All profiles must use the exact same heading text."""
        for profile in (JAVA_PROFILE, PYTHON_PROFILE, POSTGRES_PROFILE):
            content = _read_profile(profile)
            assert PHASE_15_HEADING in content, f"{profile.name} missing heading"

    def test_heading_is_h3(self):
        """Phase 1.5 heading must be ### (h3), not ## or #."""
        for profile in (JAVA_PROFILE, PYTHON_PROFILE, POSTGRES_PROFILE):
            content = _read_profile(profile)
            # Must start with exactly ### (not #### or ##)
            match = re.search(r"^(#{1,6})\s+Phase 1\.5:", content, re.MULTILINE)
            assert match is not None, f"{profile.name}: heading not found"
            assert match.group(1) == "###", (
                f"{profile.name}: expected h3, got h{len(match.group(1))}"
            )

    def test_java_and_python_both_reference_schema_section(self):
        """Both stack profiles should reference SESSION_STATE_SCHEMA.md §7.5.1."""
        for profile in (JAVA_PROFILE, PYTHON_PROFILE):
            content = _read_profile(profile)
            section = _extract_phase15_section(content)
            assert "SESSION_STATE_SCHEMA.md" in section, (
                f"{profile.name}: missing schema reference"
            )

    def test_no_duplicate_phase15_sections(self):
        """Each profile must have exactly one Phase 1.5 heading."""
        for profile in (JAVA_PROFILE, PYTHON_PROFILE, POSTGRES_PROFILE):
            content = _read_profile(profile)
            count = content.count(PHASE_15_HEADING)
            assert count == 1, (
                f"{profile.name}: expected 1 Phase 1.5 heading, found {count}"
            )

    def test_java_patterns_differ_from_python(self):
        """Java and Python sections must have stack-specific content (not identical)."""
        java_section = _extract_phase15_section(_read_profile(JAVA_PROFILE))
        python_section = _extract_phase15_section(_read_profile(PYTHON_PROFILE))
        assert java_section != python_section

    def test_all_profiles_have_at_least_one_bullet(self):
        for profile in (JAVA_PROFILE, PYTHON_PROFILE, POSTGRES_PROFILE):
            content = _read_profile(profile)
            section = _extract_phase15_section(content)
            bullets = [l for l in section.splitlines() if l.strip().startswith("- ")]
            assert len(bullets) >= 1, f"{profile.name}: no bullets in Phase 1.5"


# ---------------------------------------------------------------------------
# Edge cases: format and encoding robustness
# ---------------------------------------------------------------------------


class TestEdgeFormatRobustness:
    """Edge cases for format, encoding, and structural resilience."""

    def test_profiles_are_valid_utf8(self):
        """All profile files must be valid UTF-8."""
        for profile in (JAVA_PROFILE, PYTHON_PROFILE, POSTGRES_PROFILE):
            raw = profile.read_bytes()
            raw.decode("utf-8")  # raises on invalid UTF-8

    def test_no_trailing_whitespace_in_heading(self):
        """Phase 1.5 heading line must not have trailing whitespace."""
        for profile in (JAVA_PROFILE, PYTHON_PROFILE, POSTGRES_PROFILE):
            content = _read_profile(profile)
            for line in content.splitlines():
                if "Phase 1.5: Business Rules Discovery" in line:
                    assert line == line.rstrip(), (
                        f"{profile.name}: trailing whitespace on heading"
                    )

    def test_phase15_section_not_empty(self):
        """Phase 1.5 section body must contain at least 50 characters of content."""
        for profile in (JAVA_PROFILE, PYTHON_PROFILE, POSTGRES_PROFILE):
            content = _read_profile(profile)
            section = _extract_phase15_section(content)
            stripped = section.strip()
            assert len(stripped) >= 50, (
                f"{profile.name}: Phase 1.5 body too short ({len(stripped)} chars)"
            )

    def test_backtick_code_spans_are_balanced(self):
        """All inline code spans in Phase 1.5 sections must have balanced backticks."""
        for profile in (JAVA_PROFILE, PYTHON_PROFILE):
            content = _read_profile(profile)
            section = _extract_phase15_section(content)
            for i, line in enumerate(section.splitlines(), 1):
                backtick_count = line.count("`")
                assert backtick_count % 2 == 0, (
                    f"{profile.name} line {i}: unbalanced backticks: {line!r}"
                )

    def test_exclusion_list_follows_pattern_list(self):
        """Exclusions must appear after the positive pattern list in each profile."""
        for profile in (JAVA_PROFILE, PYTHON_PROFILE):
            content = _read_profile(profile)
            section = _extract_phase15_section(content)
            lines = section.splitlines()
            first_bullet_idx = None
            exclusion_idx = None
            for i, line in enumerate(lines):
                if line.strip().startswith("- ") and first_bullet_idx is None:
                    first_bullet_idx = i
                if "Exclusion" in line or "do NOT extract" in line:
                    exclusion_idx = i
                    break
            assert first_bullet_idx is not None, f"{profile.name}: no bullets found"
            assert exclusion_idx is not None, f"{profile.name}: no exclusion marker"
            assert exclusion_idx > first_bullet_idx, (
                f"{profile.name}: exclusions before pattern bullets"
            )
