"""Tests for hardened section signal detection (Fix 3).

Coverage: Happy, Bad, Corner, Edge cases for:
- Markdown ATX headings (original behavior preserved)
- RST underline-style headings (new)
- AsciiDoc heading syntax (new)
- HTML heading tags (new)
- Bold/emphasized pseudo-headings (new)
- Look-back window behaviour
- End-to-end extraction across all document formats
"""

from __future__ import annotations

from pathlib import Path

import pytest

from governance.engine.business_rules_validation import (
    RuleCandidate,
    _has_section_signal,
    _is_heading_line,
    extract_candidates_from_repo,
    extract_validated_business_rules_from_repo,
    validate_candidates,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# _is_heading_line unit tests
# ---------------------------------------------------------------------------


class TestIsHeadingLine:
    """Unit tests for the _is_heading_line helper."""

    def test_happy_markdown_atx(self) -> None:
        lines = ["# Business Rules"]
        assert _is_heading_line("# Business Rules", lines, 0) is True

    def test_happy_markdown_atx_h2(self) -> None:
        lines = ["## Policy"]
        assert _is_heading_line("## Policy", lines, 0) is True

    def test_happy_rst_underline(self) -> None:
        lines = ["Business Rules", "================"]
        assert _is_heading_line("================", lines, 1) is True

    def test_happy_rst_title_before_underline(self) -> None:
        lines = ["Business Rules", "================"]
        assert _is_heading_line("Business Rules", lines, 0) is True

    def test_happy_asciidoc_heading(self) -> None:
        lines = ["== Business Rules"]
        assert _is_heading_line("== Business Rules", lines, 0) is True

    def test_happy_html_heading(self) -> None:
        lines = ["<h2>Business Rules</h2>"]
        assert _is_heading_line("<h2>Business Rules</h2>", lines, 0) is True

    def test_happy_bold_pseudo_heading(self) -> None:
        lines = ["**Business Rules**"]
        assert _is_heading_line("**Business Rules**", lines, 0) is True

    def test_bad_plain_text_is_not_heading(self) -> None:
        lines = ["This is just text"]
        assert _is_heading_line("This is just text", lines, 0) is False

    def test_bad_empty_line_is_not_heading(self) -> None:
        lines = [""]
        assert _is_heading_line("", lines, 0) is False

    def test_bad_rst_underline_alone_at_start(self) -> None:
        """An underline at index 0 with no preceding title is not a heading."""
        lines = ["================"]
        assert _is_heading_line("================", lines, 0) is False

    def test_corner_rst_tilde_underline(self) -> None:
        lines = ["Policy", "~~~~~~"]
        assert _is_heading_line("~~~~~~", lines, 1) is True

    def test_corner_rst_caret_underline(self) -> None:
        lines = ["Requirements", "^^^^^^^^^^^^"]
        assert _is_heading_line("^^^^^^^^^^^^", lines, 1) is True

    def test_corner_asciidoc_h1(self) -> None:
        lines = ["= Top Level"]
        assert _is_heading_line("= Top Level", lines, 0) is True

    def test_corner_html_h1_with_attributes(self) -> None:
        lines = ['<h1 class="title">Policy</h1>']
        assert _is_heading_line(lines[0], lines, 0) is True

    def test_edge_bold_underscore_heading(self) -> None:
        lines = ["__Business Rules__"]
        assert _is_heading_line("__Business Rules__", lines, 0) is True

    def test_edge_short_underline_rejected(self) -> None:
        """Underlines shorter than 3 chars are not RST headings."""
        lines = ["AB", "=="]
        assert _is_heading_line("==", lines, 1) is False


# ---------------------------------------------------------------------------
# _has_section_signal integration tests
# ---------------------------------------------------------------------------


class TestHasSectionSignalHappy:
    """Happy path: section signal detected in various heading formats."""

    def test_happy_markdown_heading_with_signal(self) -> None:
        lines = ["# Business Rules", "", "BR-001: Access must be checked"]
        assert _has_section_signal(lines, 2) is True

    def test_happy_rst_heading_with_signal(self) -> None:
        lines = ["Business Rules", "==============", "", "BR-001: Access must be checked"]
        assert _has_section_signal(lines, 3) is True

    def test_happy_asciidoc_heading_with_signal(self) -> None:
        lines = ["== Business Rules", "", "BR-001: Access must be checked"]
        assert _has_section_signal(lines, 2) is True

    def test_happy_html_heading_with_signal(self) -> None:
        lines = ["<h2>Business Rules</h2>", "", "BR-001: Access must be checked"]
        assert _has_section_signal(lines, 2) is True

    def test_happy_bold_heading_with_signal(self) -> None:
        lines = ["**Business Rules**", "", "BR-001: Access must be checked"]
        assert _has_section_signal(lines, 2) is True


class TestHasSectionSignalBad:
    """Bad path: no section signal where it should not be found."""

    def test_bad_no_heading_at_all(self) -> None:
        lines = ["Some random text", "", "BR-001: Access must be checked"]
        assert _has_section_signal(lines, 2) is False

    def test_bad_heading_without_signal_keyword(self) -> None:
        lines = ["# Changelog", "", "BR-001: Access must be checked"]
        assert _has_section_signal(lines, 2) is False

    def test_bad_signal_keyword_in_plain_text_not_heading(self) -> None:
        lines = ["The business rules are defined below.", "", "BR-001: Access must be checked"]
        assert _has_section_signal(lines, 2) is False

    def test_bad_heading_too_far_above(self) -> None:
        """Signal heading more than 6 lines above the rule is out of window."""
        lines = [
            "# Business Rules",
            "",
            "Line 2",
            "Line 3",
            "Line 4",
            "Line 5",
            "Line 6",
            "Line 7",
            "BR-001: Access must be checked",
        ]
        assert _has_section_signal(lines, 8) is False


class TestHasSectionSignalCorner:
    """Corner cases for section signal detection."""

    def test_corner_signal_on_same_line_as_rule(self) -> None:
        """If the heading IS on the same line index (shouldn't happen in practice
        but the look-back window includes the current line)."""
        lines = ["# Business Rules BR-001: Access must be checked"]
        assert _has_section_signal(lines, 0) is True

    def test_corner_rst_overline_title_underline(self) -> None:
        """RST overline+title+underline pattern."""
        lines = ["==============", "Business Rules", "==============", "", "BR-001: Access must be checked"]
        assert _has_section_signal(lines, 4) is True

    def test_corner_multiple_headings_closest_wins(self) -> None:
        """Multiple headings in window -- any matching one suffices."""
        lines = [
            "# Changelog",
            "",
            "## Business Rules",
            "",
            "BR-001: Access must be checked",
        ]
        assert _has_section_signal(lines, 4) is True

    def test_corner_german_fachregel_signal(self) -> None:
        lines = ["## Fachliche Regel", "", "BR-001: Zugriff muss authentifiziert sein"]
        assert _has_section_signal(lines, 2) is True

    def test_corner_policy_signal(self) -> None:
        lines = ["# Policy", "", "BR-001: Access must be checked"]
        assert _has_section_signal(lines, 2) is True

    def test_corner_requirements_signal(self) -> None:
        lines = ["== Requirements", "", "BR-001: Access must be checked"]
        assert _has_section_signal(lines, 2) is True

    def test_corner_compliance_signal(self) -> None:
        lines = ["<h3>Compliance</h3>", "", "BR-001: Access must be checked"]
        assert _has_section_signal(lines, 2) is True


class TestHasSectionSignalEdge:
    """Edge cases at boundaries."""

    def test_edge_rule_at_line_zero(self) -> None:
        """Rule at the very first line -- no heading above."""
        lines = ["BR-001: Access must be checked"]
        assert _has_section_signal(lines, 0) is False

    def test_edge_heading_at_line_zero_rule_at_one(self) -> None:
        lines = ["# Business Rules", "BR-001: Access must be checked"]
        assert _has_section_signal(lines, 1) is True

    def test_edge_signal_exactly_6_lines_above(self) -> None:
        """Signal heading exactly 6 lines above -- should be IN window."""
        lines = [
            "# Business Rules",
            "",
            "Line 2",
            "Line 3",
            "Line 4",
            "Line 5",
            "BR-001: Access must be checked",
        ]
        assert _has_section_signal(lines, 6) is True

    def test_edge_signal_exactly_7_lines_above_out_of_window(self) -> None:
        """Signal heading exactly 7 lines above -- should be OUT of window."""
        lines = [
            "# Business Rules",
            "",
            "Line 2",
            "Line 3",
            "Line 4",
            "Line 5",
            "Line 6",
            "BR-001: Access must be checked",
        ]
        assert _has_section_signal(lines, 7) is False


# ---------------------------------------------------------------------------
# End-to-end extraction tests across document formats
# ---------------------------------------------------------------------------


class TestE2EExtractionRST:
    """End-to-end extraction from .rst files."""

    def test_happy_rst_file_extraction(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "docs" / "rules.rst",
            "Business Rules\n"
            "==============\n"
            "\n"
            "BR-001: Access must be authenticated before data access\n"
            "BR-002: Audit entries must not be modified after write\n",
        )
        report, ok = extract_validated_business_rules_from_repo(tmp_path)
        assert ok is True
        assert report.valid_rule_count == 2

    def test_bad_rst_no_heading_signal(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "docs" / "notes.rst",
            "Some Notes\n"
            "==========\n"
            "\n"
            "BR-001: Access must be authenticated\n",
        )
        report, ok = extract_validated_business_rules_from_repo(tmp_path)
        assert ok is True
        assert report.valid_rule_count == 0

    def test_corner_rst_tilde_underline(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "docs" / "rules.rst",
            "Policy\n"
            "~~~~~~\n"
            "\n"
            "BR-001: Access must be authenticated\n",
        )
        report, ok = extract_validated_business_rules_from_repo(tmp_path)
        assert ok is True
        assert report.valid_rule_count == 1


class TestE2EExtractionAsciiDoc:
    """End-to-end extraction from .adoc files."""

    def test_happy_adoc_file_extraction(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "docs" / "rules.adoc",
            "== Business Rules\n"
            "\n"
            "BR-001: Access must be authenticated before data access\n",
        )
        report, ok = extract_validated_business_rules_from_repo(tmp_path)
        assert ok is True
        assert report.valid_rule_count == 1

    def test_bad_adoc_no_signal_keyword(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "docs" / "notes.adoc",
            "== Release Notes\n"
            "\n"
            "BR-001: Access must be authenticated\n",
        )
        report, ok = extract_validated_business_rules_from_repo(tmp_path)
        assert ok is True
        assert report.valid_rule_count == 0


class TestE2EExtractionMarkdownPreserved:
    """Ensure original Markdown extraction behaviour is not regressed."""

    def test_happy_markdown_unchanged(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "docs" / "business-rules.md",
            "# Business Rules\n"
            "- BR-001: Access must be authenticated before data access\n"
            "- BR-002: Audit entries must not be modified after write\n",
        )
        report, ok = extract_validated_business_rules_from_repo(tmp_path)
        assert ok is True
        assert report.is_compliant is True
        assert report.valid_rule_count == 2

    def test_bad_markdown_test_dir_still_rejected(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "tests" / "rules.md",
            "# Business Rules\n"
            "- BR-001: Access must be authenticated\n",
        )
        report, ok = extract_validated_business_rules_from_repo(tmp_path)
        assert ok is True
        assert report.valid_rule_count == 0
        assert report.has_source_violation is True

    def test_corner_markdown_no_heading_still_rejected(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "docs" / "random.md",
            "# Changelog\n"
            "- BR-001: Access must be authenticated\n",
        )
        report, ok = extract_validated_business_rules_from_repo(tmp_path)
        assert ok is True
        assert report.valid_rule_count == 0


class TestE2EExtractionHTMLHeadings:
    """End-to-end with HTML headings in markdown files."""

    def test_happy_html_heading_in_md(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "docs" / "rules.md",
            "<h2>Business Rules</h2>\n"
            "\n"
            "BR-001: Access must be authenticated before data access\n",
        )
        report, ok = extract_validated_business_rules_from_repo(tmp_path)
        assert ok is True
        assert report.valid_rule_count == 1

    def test_edge_html_heading_in_txt(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "docs" / "rules.txt",
            "<h1>Policy</h1>\n"
            "\n"
            "BR-001: Access must be authenticated\n",
        )
        report, ok = extract_validated_business_rules_from_repo(tmp_path)
        assert ok is True
        assert report.valid_rule_count == 1


class TestE2EExtractionBoldHeadings:
    """End-to-end with bold pseudo-headings."""

    def test_happy_bold_heading_in_md(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "docs" / "rules.md",
            "**Business Rules**\n"
            "\n"
            "BR-001: Access must be authenticated before data access\n",
        )
        report, ok = extract_validated_business_rules_from_repo(tmp_path)
        assert ok is True
        assert report.valid_rule_count == 1

    def test_bad_bold_without_signal_rejected(self, tmp_path: Path) -> None:
        _write(
            tmp_path / "docs" / "rules.md",
            "**Release Notes**\n"
            "\n"
            "BR-001: Access must be authenticated\n",
        )
        report, ok = extract_validated_business_rules_from_repo(tmp_path)
        assert ok is True
        assert report.valid_rule_count == 0
