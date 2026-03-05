"""Cross-rail classification guard tests.

Validates that every workflow-relevant MD rail file:
- Contains a <!-- rail-classification: ... --> HTML comment
- Declares valid classification tokens from the allowed set
- Has no contradictory classification (e.g., READ-ONLY + MUTATING)
- Maintains structural consistency across all rails

Test coverage: Happy, Bad, Edge, Corner cases.

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.util import REPO_ROOT

# ---------------------------------------------------------------------------
# Classification schema
# ---------------------------------------------------------------------------

VALID_CLASSIFICATIONS = frozenset({
    "READ-ONLY",
    "MUTATING",
    "GATE-EVALUATION",
    "OUTPUT-ONLY",
    "NO-STATE-CHANGE",
})

# Contradictory pairs: if both appear in a single classification, it is invalid
CONTRADICTORY_PAIRS = [
    ("READ-ONLY", "MUTATING"),
]

# Expected classifications per rail file (source of truth for guards)
RAIL_FILES: dict[str, dict[str, object]] = {
    "continue.md": {
        "required_tokens": {"READ-ONLY", "NO-STATE-CHANGE"},
        "forbidden_tokens": {"MUTATING"},
    },
    "audit-readout.md": {
        "required_tokens": {"READ-ONLY", "OUTPUT-ONLY", "NO-STATE-CHANGE"},
        "forbidden_tokens": {"MUTATING"},
    },
    "review.md": {
        "required_tokens": {"READ-ONLY", "GATE-EVALUATION", "NO-STATE-CHANGE"},
        "forbidden_tokens": {"MUTATING"},
    },
    "ticket.md": {
        "required_tokens": {"MUTATING", "GATE-EVALUATION"},
        "forbidden_tokens": {"READ-ONLY", "NO-STATE-CHANGE"},
    },
}

CLASSIFICATION_RE = re.compile(r"<!--\s*rail-classification:\s*([^>]+)-->")


def _extract_classification(content: str) -> list[str] | None:
    """Extract classification tokens from rail-classification comment."""
    match = CLASSIFICATION_RE.search(content)
    if match is None:
        return None
    raw = match.group(1).strip()
    return [token.strip() for token in raw.split(",") if token.strip()]


# ---------------------------------------------------------------------------
# Happy path: all rails have valid classification
# ---------------------------------------------------------------------------


class TestRailClassificationHappy:
    """Happy path: every rail file has a valid, non-contradictory classification."""

    @pytest.mark.parametrize("rail_name", list(RAIL_FILES.keys()))
    def test_classification_comment_exists(self, rail_name: str) -> None:
        """Each rail file must contain a rail-classification HTML comment."""
        path = REPO_ROOT / rail_name
        assert path.exists(), f"{rail_name} must exist in repo root"
        content = path.read_text(encoding="utf-8")
        tokens = _extract_classification(content)
        assert tokens is not None, (
            f"{rail_name} must contain a <!-- rail-classification: ... --> comment"
        )

    @pytest.mark.parametrize("rail_name", list(RAIL_FILES.keys()))
    def test_classification_tokens_are_valid(self, rail_name: str) -> None:
        """All classification tokens must be from the allowed set."""
        path = REPO_ROOT / rail_name
        content = path.read_text(encoding="utf-8")
        tokens = _extract_classification(content)
        assert tokens is not None
        for token in tokens:
            assert token in VALID_CLASSIFICATIONS, (
                f"{rail_name} contains invalid classification token '{token}'. "
                f"Allowed: {sorted(VALID_CLASSIFICATIONS)}"
            )

    @pytest.mark.parametrize("rail_name", list(RAIL_FILES.keys()))
    def test_required_tokens_present(self, rail_name: str) -> None:
        """Each rail must contain its expected required classification tokens."""
        spec = RAIL_FILES[rail_name]
        path = REPO_ROOT / rail_name
        content = path.read_text(encoding="utf-8")
        tokens = set(_extract_classification(content) or [])
        required = spec["required_tokens"]
        assert isinstance(required, set)
        missing = required - tokens
        assert not missing, (
            f"{rail_name} is missing required classification tokens: {sorted(missing)}"
        )

    @pytest.mark.parametrize("rail_name", list(RAIL_FILES.keys()))
    def test_forbidden_tokens_absent(self, rail_name: str) -> None:
        """Each rail must NOT contain forbidden classification tokens."""
        spec = RAIL_FILES[rail_name]
        path = REPO_ROOT / rail_name
        content = path.read_text(encoding="utf-8")
        tokens = set(_extract_classification(content) or [])
        forbidden = spec["forbidden_tokens"]
        assert isinstance(forbidden, set)
        present = forbidden & tokens
        assert not present, (
            f"{rail_name} contains forbidden classification tokens: {sorted(present)}"
        )


# ---------------------------------------------------------------------------
# Bad path: contradiction detection
# ---------------------------------------------------------------------------


class TestRailClassificationBad:
    """Bad path: detect contradictory or missing classifications."""

    @pytest.mark.parametrize("rail_name", list(RAIL_FILES.keys()))
    def test_no_contradictory_tokens(self, rail_name: str) -> None:
        """No rail may contain contradictory classification token pairs."""
        path = REPO_ROOT / rail_name
        content = path.read_text(encoding="utf-8")
        tokens = set(_extract_classification(content) or [])
        for a, b in CONTRADICTORY_PAIRS:
            assert not (a in tokens and b in tokens), (
                f"{rail_name} has contradictory classification: "
                f"both '{a}' and '{b}' present"
            )

    @pytest.mark.parametrize("rail_name", list(RAIL_FILES.keys()))
    def test_classification_not_empty(self, rail_name: str) -> None:
        """Rail classification must not be empty."""
        path = REPO_ROOT / rail_name
        content = path.read_text(encoding="utf-8")
        tokens = _extract_classification(content)
        assert tokens is not None and len(tokens) > 0, (
            f"{rail_name} rail-classification comment must contain at least one token"
        )


# ---------------------------------------------------------------------------
# Edge case: classification appears exactly once
# ---------------------------------------------------------------------------


class TestRailClassificationEdge:
    """Edge cases: classification comment must appear exactly once."""

    @pytest.mark.parametrize("rail_name", list(RAIL_FILES.keys()))
    def test_classification_appears_exactly_once(self, rail_name: str) -> None:
        """The rail-classification comment must appear exactly once per file."""
        path = REPO_ROOT / rail_name
        content = path.read_text(encoding="utf-8")
        matches = CLASSIFICATION_RE.findall(content)
        assert len(matches) == 1, (
            f"{rail_name} must contain exactly one rail-classification comment, "
            f"found {len(matches)}"
        )

    @pytest.mark.parametrize("rail_name", list(RAIL_FILES.keys()))
    def test_classification_appears_in_first_10_lines(self, rail_name: str) -> None:
        """Rail classification must appear near the top of the file (first 10 lines)."""
        path = REPO_ROOT / rail_name
        content = path.read_text(encoding="utf-8")
        lines = content.split("\n")[:10]
        header = "\n".join(lines)
        assert CLASSIFICATION_RE.search(header), (
            f"{rail_name} rail-classification must appear within the first 10 lines "
            "for reliable LLM parsing"
        )

    def test_read_only_rails_share_no_state_change(self) -> None:
        """All READ-ONLY rails must also declare NO-STATE-CHANGE."""
        for rail_name, spec in RAIL_FILES.items():
            required = spec["required_tokens"]
            assert isinstance(required, set)
            if "READ-ONLY" in required:
                assert "NO-STATE-CHANGE" in required, (
                    f"{rail_name} is READ-ONLY but does not declare NO-STATE-CHANGE. "
                    "READ-ONLY rails must also declare NO-STATE-CHANGE."
                )


# ---------------------------------------------------------------------------
# Corner case: classification robustness
# ---------------------------------------------------------------------------


class TestRailClassificationCorner:
    """Corner cases: whitespace tolerance, ordering independence."""

    def test_extract_classification_with_extra_whitespace(self) -> None:
        """Classification extraction must tolerate extra whitespace."""
        content = "<!-- rail-classification:   READ-ONLY ,  NO-STATE-CHANGE  -->"
        tokens = _extract_classification(content)
        assert tokens is not None
        assert set(tokens) == {"READ-ONLY", "NO-STATE-CHANGE"}

    def test_extract_classification_single_token(self) -> None:
        """Classification extraction must handle a single token."""
        content = "<!-- rail-classification: MUTATING -->"
        tokens = _extract_classification(content)
        assert tokens == ["MUTATING"]

    def test_extract_classification_no_comment(self) -> None:
        """Files without classification return None."""
        tokens = _extract_classification("# Just a heading\nSome content.")
        assert tokens is None

    def test_extract_classification_malformed_comment(self) -> None:
        """Malformed comment (missing closing) returns None."""
        content = "<!-- rail-classification: READ-ONLY"
        tokens = _extract_classification(content)
        assert tokens is None

    def test_extract_classification_empty_value(self) -> None:
        """Classification with empty value between delimiters returns empty list."""
        content = "<!-- rail-classification:  -->"
        tokens = _extract_classification(content)
        # Should return empty list (no tokens after strip)
        assert tokens is not None
        assert len(tokens) == 0

    @pytest.mark.parametrize("rail_name", list(RAIL_FILES.keys()))
    def test_classification_tokens_are_uppercase(self, rail_name: str) -> None:
        """All classification tokens must be UPPERCASE (canonical form)."""
        path = REPO_ROOT / rail_name
        content = path.read_text(encoding="utf-8")
        tokens = _extract_classification(content)
        assert tokens is not None
        for token in tokens:
            assert token == token.upper(), (
                f"{rail_name} classification token '{token}' must be UPPERCASE"
            )

    @pytest.mark.parametrize("rail_name", list(RAIL_FILES.keys()))
    def test_no_duplicate_tokens(self, rail_name: str) -> None:
        """No rail may declare the same classification token twice."""
        path = REPO_ROOT / rail_name
        content = path.read_text(encoding="utf-8")
        tokens = _extract_classification(content)
        assert tokens is not None
        assert len(tokens) == len(set(tokens)), (
            f"{rail_name} contains duplicate classification tokens: {tokens}"
        )


# ---------------------------------------------------------------------------
# Cross-file consistency: provenance and bridge block sync
# ---------------------------------------------------------------------------


class TestCrossRailConsistency:
    """Cross-rail consistency checks across all bridge-bearing rails."""

    BRIDGE_RAILS = ("continue.md", "review.md")

    @pytest.fixture(autouse=True)
    def _load_rails(self) -> None:
        self.contents: dict[str, str] = {}
        for name in self.BRIDGE_RAILS:
            path = REPO_ROOT / name
            assert path.exists(), f"{name} must exist"
            self.contents[name] = path.read_text(encoding="utf-8")

    def test_all_bridge_rails_have_provenance(self) -> None:
        """All bridge-bearing rails must contain installer provenance."""
        for name, content in self.contents.items():
            assert "governance installer" in content.lower(), (
                f"{name} must contain 'governance installer' provenance"
            )

    def test_all_bridge_rails_have_safe_to_execute(self) -> None:
        """All bridge-bearing rails must state 'safe to execute'."""
        for name, content in self.contents.items():
            assert "safe to execute" in content.lower(), (
                f"{name} must state the command is 'safe to execute'"
            )

    def test_all_bridge_rails_have_no_infer_mutate(self) -> None:
        """All bridge-bearing rails must contain the no-infer-or-mutate guard."""
        for name, content in self.contents.items():
            assert "do not infer or mutate" in content.lower(), (
                f"{name} must contain 'Do not infer or mutate any session state'"
            )

    def test_bridge_rails_have_no_sole_exception(self) -> None:
        """No bridge-bearing rail may use 'sole exception' framing."""
        for name, content in self.contents.items():
            assert "sole exception" not in content.lower(), (
                f"{name} must NOT use 'sole exception' — triggers security refusals"
            )

    def test_ticket_has_no_bridge_block(self) -> None:
        """ticket.md must NOT contain a kernel bridge block (it is MUTATING)."""
        ticket_path = REPO_ROOT / "ticket.md"
        content = ticket_path.read_text(encoding="utf-8")
        assert "GOVERNANCE KERNEL BRIDGE" not in content, (
            "ticket.md must NOT contain a kernel bridge block — "
            "it is a MUTATING rail that does not need session reading"
        )


# ---------------------------------------------------------------------------
# Install.py integration: OPENCODE_INSTRUCTIONS includes README-OPENCODE.md
# ---------------------------------------------------------------------------


class TestInstallInstructionsIntegration:
    """Verify install.py OPENCODE_INSTRUCTIONS array is complete."""

    def test_readme_opencode_in_instructions(self) -> None:
        """OPENCODE_INSTRUCTIONS must include README-OPENCODE.md for governance context."""
        from install import OPENCODE_INSTRUCTIONS

        assert "commands/README-OPENCODE.md" in OPENCODE_INSTRUCTIONS, (
            "OPENCODE_INSTRUCTIONS must include 'commands/README-OPENCODE.md' "
            "so the model has governance system context when executing commands"
        )

    def test_master_md_in_instructions(self) -> None:
        """OPENCODE_INSTRUCTIONS must include master.md."""
        from install import OPENCODE_INSTRUCTIONS

        assert "commands/master.md" in OPENCODE_INSTRUCTIONS

    def test_instructions_no_duplicates(self) -> None:
        """OPENCODE_INSTRUCTIONS must not contain duplicate entries."""
        from install import OPENCODE_INSTRUCTIONS

        assert len(OPENCODE_INSTRUCTIONS) == len(set(OPENCODE_INSTRUCTIONS)), (
            "OPENCODE_INSTRUCTIONS contains duplicate entries"
        )

    def test_instructions_all_start_with_commands(self) -> None:
        """All instruction paths must start with 'commands/'."""
        from install import OPENCODE_INSTRUCTIONS

        for entry in OPENCODE_INSTRUCTIONS:
            assert entry.startswith("commands/"), (
                f"Instruction path '{entry}' must start with 'commands/'"
            )


# ---------------------------------------------------------------------------
# master.md content guards
# ---------------------------------------------------------------------------


class TestMasterMdContentGuards:
    """Verify master.md content fixes are in place."""

    @pytest.fixture(autouse=True)
    def _load_master(self) -> None:
        self.path = REPO_ROOT / "master.md"
        assert self.path.exists()
        self.content = self.path.read_text(encoding="utf-8")

    def test_no_double_negation_implicit_gate(self) -> None:
        """master.md must not contain 'does not forbid' double-negation."""
        assert "does not forbid" not in self.content, (
            "master.md must not use 'does not forbid' double-negation — "
            "replace with explicit positive statement about what IS permitted"
        )

    def test_p53_gate_result_has_explicit_target(self) -> None:
        """P5.3 test-quality-pass must specify explicit phase target."""
        assert "proceed to Phase 6" in self.content, (
            "master.md test-quality-pass gate result must specify "
            "'proceed to Phase 6' (not ambiguous 'proceed')"
        )

    def test_p53_critical_gate_documented(self) -> None:
        """P5.3 must be documented as CRITICAL gate."""
        assert "CRITICAL" in self.content, (
            "master.md must document P5.3 as a CRITICAL quality gate"
        )

    def test_phase5_code_output_explicitly_scoped(self) -> None:
        """master.md must explicitly prohibit code output during Phase 5."""
        content_lower = self.content.lower()
        assert "not permitted during phase 5" in content_lower, (
            "master.md must explicitly state that code-producing output is "
            "NOT permitted during Phase 5"
        )
        assert "review gate" in content_lower, (
            "master.md must frame Phase 5 as exclusively a review gate"
        )
        assert "phase 6" in content_lower, (
            "master.md must state implementation begins after Phase 5 gates pass "
            "and the session transitions to Phase 6"
        )


# ---------------------------------------------------------------------------
# QUICKSTART.md content guards
# ---------------------------------------------------------------------------


class TestQuickstartContentGuards:
    """Verify QUICKSTART.md example drift fix is in place."""

    @pytest.fixture(autouse=True)
    def _load_quickstart(self) -> None:
        self.path = REPO_ROOT / "QUICKSTART.md"
        assert self.path.exists()
        self.content = self.path.read_text(encoding="utf-8")

    def test_start_new_work_mentions_plan_mode(self) -> None:
        """'Start new work' example must mention Plan Mode."""
        # Find the 'Start new work' section
        start_idx = self.content.find("Start new work")
        assert start_idx >= 0, "QUICKSTART.md must contain 'Start new work' section"
        # Find the next section or end of file
        next_section_idx = self.content.find("**Debug", start_idx)
        if next_section_idx < 0:
            next_section_idx = len(self.content)
        section = self.content[start_idx:next_section_idx]
        assert "plan mode" in section.lower(), (
            "QUICKSTART.md 'Start new work' example must mention Plan Mode step. "
            "Line 62 mandates Plan Mode for new tickets but the example was missing it."
        )

    def test_workflow_order_in_example(self) -> None:
        """'Start new work' example must show correct workflow order."""
        start_idx = self.content.find("Start new work")
        assert start_idx >= 0
        next_section_idx = self.content.find("**Debug", start_idx)
        if next_section_idx < 0:
            next_section_idx = len(self.content)
        section = self.content[start_idx:next_section_idx]
        # /continue must appear before /ticket
        continue_pos = section.find("/continue")
        ticket_pos = section.find("/ticket")
        review_pos = section.find("/review")
        assert continue_pos < ticket_pos < review_pos, (
            "QUICKSTART.md example must show /continue before /ticket before /review"
        )
