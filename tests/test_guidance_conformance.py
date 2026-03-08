"""Guidance-core structural and operative-preservation conformance checks.

Verifies that the G1–G4 refactor of master.md and rules.md preserved all
operative rules and structural invariants.

Test coverage:
    Happy:  each required concept/string is present in the expected file.
    Corner: XML tags are balanced; heading caps respected.
    Edge:   boundary heading counts exactly at cap.
    Bad:    synthetic unbalanced tag / over-cap heading count detected.

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

_MASTER = REPO_ROOT / "master.md"
_RULES = REPO_ROOT / "rules.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════════
# 1.  STRUCTURAL CHECKS — XML tags, heading caps, ordering
# ═══════════════════════════════════════════════════════════════════════════

_XML_TAGS = [
    "authority",
    "phase-routing",
    "operative-constraints",
    "evidence-rules",
    "presentation-advisory",
]

_OPEN_TAG_RE = re.compile(r"<(" + "|".join(_XML_TAGS) + r")>")
_CLOSE_TAG_RE = re.compile(r"</(" + "|".join(_XML_TAGS) + r")>")

_HEADING_RE = re.compile(r"^#{1,6}\s", re.MULTILINE)


class TestGuidanceXMLStructure:
    """XML tags must be balanced and drawn from the approved set."""

    @pytest.mark.parametrize("path", [_MASTER, _RULES], ids=["master.md", "rules.md"])
    def test_xml_tags_balanced(self, path: Path) -> None:
        text = _read(path)
        opens = _OPEN_TAG_RE.findall(text)
        closes = _CLOSE_TAG_RE.findall(text)
        assert sorted(opens) == sorted(closes), (
            f"{path.name}: unbalanced XML tags — "
            f"opens={sorted(opens)}, closes={sorted(closes)}"
        )

    @pytest.mark.parametrize("path", [_MASTER, _RULES], ids=["master.md", "rules.md"])
    def test_no_orphan_xml_tags(self, path: Path) -> None:
        """Every open tag must have a matching close before the next open of same name."""
        text = _read(path)
        for tag in _XML_TAGS:
            open_count = len(re.findall(rf"<{tag}>", text))
            close_count = len(re.findall(rf"</{tag}>", text))
            assert open_count == close_count, (
                f"{path.name}: tag <{tag}> has {open_count} opens "
                f"but {close_count} closes"
            )

    def test_master_has_required_xml_zones(self) -> None:
        text = _read(_MASTER)
        required = ["authority", "phase-routing", "operative-constraints"]
        for tag in required:
            assert f"<{tag}>" in text, f"master.md missing <{tag}> zone"
            assert f"</{tag}>" in text, f"master.md missing </{tag}> close"

    def test_rules_has_required_xml_zones(self) -> None:
        text = _read(_RULES)
        required = ["authority", "operative-constraints", "evidence-rules"]
        for tag in required:
            assert f"<{tag}>" in text, f"rules.md missing <{tag}> zone"
            assert f"</{tag}>" in text, f"rules.md missing </{tag}> close"


class TestGuidanceHeadingCaps:
    """Heading counts must stay within agreed caps."""

    _MASTER_CAP = 30
    _RULES_CAP = 35

    def test_master_heading_cap(self) -> None:
        text = _read(_MASTER)
        count = len(_HEADING_RE.findall(text))
        assert count <= self._MASTER_CAP, (
            f"master.md has {count} headings, exceeds cap of {self._MASTER_CAP}"
        )

    def test_rules_heading_cap(self) -> None:
        text = _read(_RULES)
        count = len(_HEADING_RE.findall(text))
        assert count <= self._RULES_CAP, (
            f"rules.md has {count} headings, exceeds cap of {self._RULES_CAP}"
        )


class TestGuidanceAuthorityDensity:
    """Keep authority language sparse and operational."""

    def test_master_kernel_owned_density_cap(self) -> None:
        text = _read(_MASTER).lower()
        assert text.count("kernel-owned") <= 12, (
            "master.md repeats 'kernel-owned' too often; keep authority language sparse"
        )

    def test_rules_kernel_owned_density_cap(self) -> None:
        text = _read(_RULES).lower()
        assert text.count("kernel-owned") <= 12, (
            "rules.md repeats 'kernel-owned' too often; keep authority language sparse"
        )

    def test_master_critical_emphasis_cap(self) -> None:
        text = _read(_MASTER)
        assert text.count("CRITICAL") <= 2, (
            "master.md overuses CRITICAL emphasis; keep emphatic language minimal"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 2.  OPERATIVE PRESERVATION — key rules must survive refactor
# ═══════════════════════════════════════════════════════════════════════════


class TestOperativePreservationMaster:
    """master.md must retain all operative rules after G1–G4 refactor."""

    @pytest.fixture(autouse=True)
    def _load(self) -> None:
        self.text = _read(_MASTER)
        self.lower = self.text.lower()

    def test_phase5_no_implementation(self) -> None:
        """Phase 5 implementation prohibition must survive."""
        assert "not permitted during phase 5" in self.lower

    def test_rule_a_implementation_intent(self) -> None:
        assert "Rule A" in self.text
        assert "implementation" in self.lower
        assert "forbidden" in self.lower or "prohibited" in self.lower

    def test_rule_b_self_review(self) -> None:
        assert "Rule B" in self.text
        assert "self-review" in self.text

    def test_phase53_critical_gate(self) -> None:
        assert "CRITICAL" in self.text
        assert "implementation readiness" in self.text

    def test_confidence_clarification(self) -> None:
        assert "confidence" in self.lower
        assert "clarification" in self.lower

    def test_bootstrap_blocked(self) -> None:
        assert "BLOCKED" in self.text
        assert "bootstrap" in self.lower

    def test_output_policy_reference(self) -> None:
        assert "output_policy" in self.text

    def test_implementation_intent_reference(self) -> None:
        assert "implementation-intent" in self.text


class TestOperativePreservationRules:
    """rules.md must retain all operative rules after G1–G4 refactor."""

    @pytest.fixture(autouse=True)
    def _load(self) -> None:
        self.text = _read(_RULES)
        self.lower = self.text.lower()

    def test_component_scope(self) -> None:
        assert "component scope" in self.lower

    def test_working_set(self) -> None:
        assert "working set" in self.lower

    def test_touched_surface(self) -> None:
        assert "touched surface" in self.lower or "touchedsurface" in self.lower

    def test_strict_evidence_mode(self) -> None:
        assert "strict evidence mode" in self.lower

    def test_not_provable(self) -> None:
        assert "not provable" in self.lower

    def test_evidence_ladder(self) -> None:
        assert "evidence ladder" in self.lower

    def test_presentation_advisory_operative_rules(self) -> None:
        """The 4 operative presentation rules must survive."""
        assert "exactly one actionable next step" in self.lower
        assert "one primary blocker" in self.lower
        assert "blocked, not warn" in self.lower
        assert "presentation mode" in self.lower

    def test_business_logic_contract(self) -> None:
        assert "business logic" in self.lower or "business rules" in self.lower
        assert "domain type" in self.lower or "domain model" in self.lower

    def test_fast_path_awareness(self) -> None:
        assert "fast path" in self.lower

    def test_blocker_handling(self) -> None:
        """Blocked outcome for missing component scope must survive."""
        assert "blocked" in self.lower
        assert "component scope" in self.lower


class TestRoleMandateConformance:
    """Ensure concise role definition and dual mandates stay enforced."""

    def test_happy_master_global_role_present(self) -> None:
        text = _read(_MASTER).lower()
        assert "global role" in text
        assert "senior technical governance operator" in text
        assert "evidence-first" in text
        assert "drift-sensitive" in text

    def test_happy_rules_dual_mandates_present(self) -> None:
        text = _read(_RULES).lower()
        assert "authoring mandate" in text
        assert "review mandate" in text
        assert "smallest correct solution" in text
        assert "attempt to falsify before approving" in text

    def test_corner_review_mandate_quality_focus(self) -> None:
        text = _read(_RULES).lower()
        required = [
            "contract drift",
            "cross-os",
            "silent fallback",
            "test gaps",
            "fail-closed",
        ]
        for token in required:
            assert token in text, f"rules.md review mandate missing token: {token}"

    def test_bad_persona_inflation_forbidden(self) -> None:
        combined = (_read(_MASTER) + "\n" + _read(_RULES)).lower()
        forbidden = ["20+ years", "world-class", "elite developer"]
        for token in forbidden:
            assert token not in combined, f"Persona inflation token must be absent: {token}"


# ═══════════════════════════════════════════════════════════════════════════
# 3.  BAD-PATH / SYNTHETIC TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestGuidanceStructureSynthetic:
    """Bad-path: synthetic violations must be detected by the helpers."""

    def test_unbalanced_tags_detected(self) -> None:
        text = "<authority>\nsome content\n"
        opens = _OPEN_TAG_RE.findall(text)
        closes = _CLOSE_TAG_RE.findall(text)
        assert sorted(opens) != sorted(closes), "Unbalanced tags should differ"

    def test_balanced_tags_pass(self) -> None:
        text = "<authority>\nsome content\n</authority>\n"
        opens = _OPEN_TAG_RE.findall(text)
        closes = _CLOSE_TAG_RE.findall(text)
        assert sorted(opens) == sorted(closes)

    def test_heading_cap_exceeded_detected(self) -> None:
        text = "\n".join(f"## Heading {i}" for i in range(40))
        count = len(_HEADING_RE.findall(text))
        assert count == 40
        assert count > 35, "40 headings should exceed any reasonable cap"

    def test_heading_cap_at_boundary(self) -> None:
        text = "\n".join(f"## Heading {i}" for i in range(30))
        count = len(_HEADING_RE.findall(text))
        assert count == 30, "Exactly 30 headings at master cap boundary"
