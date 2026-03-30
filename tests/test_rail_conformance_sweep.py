"""Cross-Agent Markdown Rail conformance sweep.

Enforces all 9 conformance rules (CR-01 through CR-09) defined in
docs/contracts/cross-agent-rail-spec.v1.md across every model-facing
markdown file in the repository.

Structure:
    1. Inventory tests — every inventoried file exists + has declared classification.
    2. Per-CR tests — each rule checked against all files in scope.
    3. Regression guard — new unregistered model-rail/hybrid files fail the suite.

Test coverage per rule:
    Happy:  clean file passes.
    Bad:    injected violation caught.
    Corner: edge-case exemptions (tables for CR-08, example blocks for CR-06).
    Edge:   boundary conditions (exactly 3 MUST lines OK, 4 not OK).

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import NamedTuple

import pytest

from tests.util import get_docs_path

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_ROOT = get_docs_path()

# ═══════════════════════════════════════════════════════════════════════════
# 1.  FILE INVENTORY — mirrors cross-agent-rail-spec.v1.md Section 3
# ═══════════════════════════════════════════════════════════════════════════


class _Entry(NamedTuple):
    path: str
    classification: str  # model-rail | hybrid | runbook


# Section 3.1 — Root-level model-rails
_ROOT_RAILS: list[_Entry] = [
    _Entry("continue.md", "model-rail"),
    _Entry("review.md", "model-rail"),
    _Entry("audit-readout.md", "model-rail"),
    _Entry("ticket.md", "model-rail"),
    _Entry("plan.md", "model-rail"),
    _Entry("review-decision.md", "model-rail"),
    _Entry("implementation-decision.md", "model-rail"),
    _Entry("implement.md", "model-rail"),
    _Entry("master.md", "model-rail"),
    _Entry("rules.md", "model-rail"),
    _Entry("BOOTSTRAP.md", "model-rail"),
]

# Section 3.2 — docs/ model-rails
_DOCS_RAILS: list[_Entry] = [
    _Entry("docs/SECURITY_MODEL.md", "model-rail"),
    _Entry("docs/THREAT_MODEL.md", "model-rail"),
    _Entry("docs/MD_PYTHON_POLICY.md", "model-rail"),
    _Entry("docs/new_profile.md", "model-rail"),
    _Entry("docs/new_addon.md", "model-rail"),
]

# Section 3.3 — docs/ hybrid files
_DOCS_HYBRID: list[_Entry] = [
    _Entry("docs/release-security-model.md", "hybrid"),
    _Entry("docs/MODEL_IDENTITY_RESOLUTION.md", "hybrid"),
]

# Section 3.4 — docs/ runbook files
_DOCS_RUNBOOKS: list[_Entry] = [
    _Entry("docs/python-quality-benchmark-pack.md", "runbook"),
    _Entry("docs/customer-install-bundle-v1.md", "runbook"),
    _Entry("docs/releasing.md", "runbook"),
]

# Combined scopes
_MODEL_RAIL_FILES = _ROOT_RAILS + _DOCS_RAILS
_HYBRID_FILES = _DOCS_HYBRID
_MODEL_RAIL_AND_HYBRID = _MODEL_RAIL_FILES + _HYBRID_FILES
_ALL_ENFORCED = _MODEL_RAIL_AND_HYBRID + _DOCS_RUNBOOKS

# Command rails with fallback structure (CR-07 scope).
# Rail-style-spec v1: all execution-facing command rails must have fallback.
_COMMAND_RAILS = [
    e for e in _ROOT_RAILS
    if e.path in {
        "continue.md", "review.md", "audit-readout.md",
        "ticket.md", "plan.md", "review-decision.md", "implementation-decision.md", "implement.md",
    }
]

# Execution rails (state-changing or gate-evaluating) — R1/R2 compression scope.
# audit-readout.md is output-only and has different density expectations.
_EXECUTION_RAILS = [
    e for e in _ROOT_RAILS
    if e.path in {
        "continue.md", "review.md",
        "ticket.md", "plan.md", "review-decision.md", "implementation-decision.md", "implement.md",
    }
]

# ───────────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────────

_RAIL_TAG_RE = re.compile(r"<!--\s*rail-classification:\s*[^>]+-->")
_BACKTICK_REF_RE = re.compile(r"`[^`]+`")
_CODE_FENCE_RE = re.compile(r"^```(\w*)")
_HOME_PATH_RE = re.compile(
    r"(?:/home/\w+|C:[\\\/]Users[\\\/]\w+|C:\\Users\\\w+)",
    re.IGNORECASE,
)
_DIRECT_PYTHON_RE = re.compile(
    r"\b(?:python |python3 |py -3 |python -m )",
    re.IGNORECASE,
)


def _read(entry: _Entry) -> str:
    """Read file content, raising a clear error if missing."""
    p = _resolve_entry_path(entry.path)
    assert p.exists(), f"Inventoried file missing: {entry.path}"
    return p.read_text(encoding="utf-8")


def _resolve_entry_path(rel_path: str) -> Path:
    if rel_path.startswith("docs/"):
        return DOCS_ROOT / rel_path[len("docs/"):]
    if rel_path in {"master.md", "rules.md"}:
        return REPO_ROOT / "governance_content" / "reference" / rel_path
    if "/" not in rel_path and rel_path.endswith(".md"):
        command_path = REPO_ROOT / "opencode" / "commands" / rel_path
        if command_path.exists():
            return command_path
    return REPO_ROOT / rel_path


def _lines(text: str) -> list[str]:
    return text.splitlines()


def _is_table_line(line: str) -> bool:
    return line.lstrip().startswith("|")


def _extract_fenced_blocks(text: str) -> list[tuple[str, str]]:
    """Return list of (label, block_content) for fenced code blocks."""
    blocks: list[tuple[str, str]] = []
    lines = text.splitlines()
    inside = False
    label = ""
    buf: list[str] = []
    for raw in lines:
        stripped = raw.strip()
        if not inside:
            m = _CODE_FENCE_RE.match(stripped)
            if m and stripped.startswith("```"):
                inside = True
                label = m.group(1).lower()
                buf = []
        else:
            if stripped.startswith("```"):
                blocks.append((label, "\n".join(buf)))
                inside = False
            else:
                buf.append(raw)
    return blocks


def _strip_fenced_blocks(text: str) -> str:
    """Return text with fenced code blocks removed."""
    return re.sub(r"```[\s\S]*?```", "", text)


# ═══════════════════════════════════════════════════════════════════════════
# 2.  INVENTORY TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestInventoryExists:
    """Every file in the spec inventory must exist on disk."""

    @pytest.mark.parametrize(
        "entry",
        _ALL_ENFORCED,
        ids=[e.path for e in _ALL_ENFORCED],
    )
    def test_file_exists(self, entry: _Entry) -> None:
        p = _resolve_entry_path(entry.path)
        assert p.is_file(), f"Inventoried file does not exist: {entry.path}"


class TestInventoryClassificationTag:
    """model-rail and hybrid files must have a rail-classification tag (CR-09)."""

    @pytest.mark.parametrize(
        "entry",
        _MODEL_RAIL_AND_HYBRID,
        ids=[e.path for e in _MODEL_RAIL_AND_HYBRID],
    )
    def test_tag_in_first_10_lines(self, entry: _Entry) -> None:
        content = _read(entry)
        first_10 = "\n".join(_lines(content)[:10])
        assert _RAIL_TAG_RE.search(first_10), (
            f"{entry.path}: missing <!-- rail-classification: ... --> in first 10 lines (CR-09)"
        )


class TestRegressionGuard:
    """New .md files in model-facing locations must be registered in inventory."""

    _REGISTERED_PATHS = frozenset(e.path for e in _ALL_ENFORCED)

    # Directories that contain model-facing files
    _MONITORED_ROOTS = [
        # root-level .md files that could be model-rails
        (".", {"continue.md", "review.md", "audit-readout.md", "ticket.md",
               "plan.md", "review-decision.md", "implement.md", "master.md", "rules.md", "BOOTSTRAP.md"}),
    ]

    def test_no_unregistered_model_rail_in_root(self) -> None:
        """Root-level .md files matching known rail patterns must be registered."""
        known_root_rails = {e.path for e in _ROOT_RAILS}
        # Check that no *new* .md file looks like a command rail but is unregistered
        for md in sorted(REPO_ROOT.glob("*.md")):
            name = md.name
            # Heuristic: if a root .md has a rail-classification tag, it should
            # be in the inventory
            content = md.read_text(encoding="utf-8")
            first_10 = "\n".join(content.splitlines()[:10])
            if _RAIL_TAG_RE.search(first_10) and name not in known_root_rails:
                pytest.fail(
                    f"Root file {name} has a rail-classification tag but is not "
                    f"registered in the cross-agent-rail-spec inventory. "
                    f"Add it to Section 3.1 and to this test's _ROOT_RAILS."
                )

    def test_no_unregistered_model_rail_in_docs(self) -> None:
        """docs/ .md files with rail-classification tags must be registered."""
        known_docs = {
            e.path for e in _DOCS_RAILS + _DOCS_HYBRID + _DOCS_RUNBOOKS
        }
        docs_dir = DOCS_ROOT
        if not docs_dir.is_dir():
            return
        for md in sorted(docs_dir.glob("*.md")):
            relpath = f"docs/{md.name}"
            if md.name in {Path(e.path).name for e in _ROOT_RAILS}:
                continue
            content = md.read_text(encoding="utf-8")
            first_10 = "\n".join(content.splitlines()[:10])
            if _RAIL_TAG_RE.search(first_10) and relpath not in known_docs:
                pytest.fail(
                    f"docs/ file {relpath} has a rail-classification tag but is not "
                    f"registered in the cross-agent-rail-spec inventory. "
                    f"Add it to Section 3.2/3.3/3.4 and to this test."
                )


# ═══════════════════════════════════════════════════════════════════════════
# 3.  PER-RULE CONFORMANCE TESTS
# ═══════════════════════════════════════════════════════════════════════════

# ---- CR-01: No trust-triggering language ------------------------------------

_CR01_BANNED = [
    re.compile(r"safe\s+to\s+execute", re.IGNORECASE),
    re.compile(r"governance\s+installer", re.IGNORECASE),
]


class TestCR01NoTrustLanguage:
    """CR-01: banned trust-triggering phrases must not appear."""

    @pytest.mark.parametrize(
        "entry",
        _ALL_ENFORCED,
        ids=[e.path for e in _ALL_ENFORCED],
    )
    def test_no_banned_phrases(self, entry: _Entry) -> None:
        content = _read(entry)
        violations: list[str] = []
        for i, line in enumerate(_lines(content), 1):
            for pat in _CR01_BANNED:
                if pat.search(line):
                    violations.append(f"  {entry.path}:{i}: {pat.pattern}")
        assert not violations, (
            f"CR-01 violation — trust-triggering language found:\n"
            + "\n".join(violations)
        )


# ---- CR-02: "authoritative" requires backtick SSOT ref --------------------


class TestCR02AuthoritativeUsage:
    """CR-02: every line with 'authoritative' must have a backtick ref."""

    @pytest.mark.parametrize(
        "entry",
        _MODEL_RAIL_AND_HYBRID,
        ids=[e.path for e in _MODEL_RAIL_AND_HYBRID],
    )
    def test_authoritative_has_backtick_ref(self, entry: _Entry) -> None:
        content = _read(entry)
        violations: list[str] = []
        for i, line in enumerate(_lines(content), 1):
            if "authoritative" in line.lower():
                if not _BACKTICK_REF_RE.search(line):
                    violations.append(f"  {entry.path}:{i}: {line.strip()}")
        assert not violations, (
            f"CR-02 violation — 'authoritative' without backtick SSOT ref:\n"
            + "\n".join(violations)
        )


# ---- CR-03: "kernel-owned" requires backtick SSOT ref ---------------------


class TestCR03KernelOwnedUsage:
    """CR-03: every line with 'kernel-owned' must have a backtick ref."""

    @pytest.mark.parametrize(
        "entry",
        _MODEL_RAIL_AND_HYBRID,
        ids=[e.path for e in _MODEL_RAIL_AND_HYBRID],
    )
    def test_kernel_owned_has_backtick_ref(self, entry: _Entry) -> None:
        content = _read(entry)
        violations: list[str] = []
        for i, line in enumerate(_lines(content), 1):
            if "kernel-owned" in line.lower():
                # Table classification labels are exempt per spec
                if _is_table_line(line):
                    continue
                if not _BACKTICK_REF_RE.search(line):
                    violations.append(f"  {entry.path}:{i}: {line.strip()}")
        assert not violations, (
            f"CR-03 violation — 'kernel-owned' without backtick SSOT ref:\n"
            + "\n".join(violations)
        )


# ---- CR-04: No absolute home paths as primary commands ---------------------


class TestCR04NoAbsoluteHomePaths:
    """CR-04: no /home/user or C:\\Users\\user paths outside code examples."""

    @pytest.mark.parametrize(
        "entry",
        _ALL_ENFORCED,
        ids=[e.path for e in _ALL_ENFORCED],
    )
    def test_no_home_paths(self, entry: _Entry) -> None:
        # Strip fenced code blocks marked as examples
        content = _read(entry)
        stripped = _strip_fenced_blocks(content)
        violations: list[str] = []
        for i, line in enumerate(_lines(stripped), 1):
            if _HOME_PATH_RE.search(line):
                violations.append(f"  {entry.path}:{i}: {line.strip()}")
        assert not violations, (
            f"CR-04 violation — absolute home paths found:\n"
            + "\n".join(violations)
        )


# ---- CR-05: Platform-correct code blocks ----------------------------------

_WINDOWS_IN_BASH = [
    re.compile(r'\bset\s+"[^"]*"', re.IGNORECASE),
    re.compile(r"%\w+%"),
]

_UNIX_IN_CMD = [
    re.compile(r"\$PATH\b"),
    re.compile(r"\bexport\s+\w+="),
]


class TestCR05PlatformCorrectBlocks:
    """CR-05: bash blocks must not contain CMD syntax and vice versa."""

    @pytest.mark.parametrize(
        "entry",
        _ALL_ENFORCED,
        ids=[e.path for e in _ALL_ENFORCED],
    )
    def test_no_cross_platform_syntax(self, entry: _Entry) -> None:
        content = _read(entry)
        blocks = _extract_fenced_blocks(content)
        violations: list[str] = []
        for label, body in blocks:
            if label == "bash":
                for pat in _WINDOWS_IN_BASH:
                    for m in pat.finditer(body):
                        violations.append(
                            f"  {entry.path}: bash block contains Windows syntax: {m.group()}"
                        )
            elif label == "cmd":
                for pat in _UNIX_IN_CMD:
                    for m in pat.finditer(body):
                        violations.append(
                            f"  {entry.path}: cmd block contains Unix syntax: {m.group()}"
                        )
        assert not violations, (
            f"CR-05 violation — platform syntax mismatch:\n"
            + "\n".join(violations)
        )


# ---- CR-06: Stable launcher name, no direct Python calls ------------------


class TestCR06StableLauncherName:
    """CR-06: model-rail/hybrid code blocks must not invoke Python directly."""

    # Files exempt from CR-06 checks in their code blocks
    _EXEMPT_FILES = {"docs/MD_PYTHON_POLICY.md"}

    @pytest.mark.parametrize(
        "entry",
        _MODEL_RAIL_AND_HYBRID,
        ids=[e.path for e in _MODEL_RAIL_AND_HYBRID],
    )
    def test_no_direct_python_calls(self, entry: _Entry) -> None:
        if entry.path in self._EXEMPT_FILES:
            pytest.skip("MD_PYTHON_POLICY.md is exempt (contains examples)")
        content = _read(entry)
        blocks = _extract_fenced_blocks(content)
        violations: list[str] = []
        for label, body in blocks:
            if label in ("bash", "cmd", "powershell", "sh", "shell", ""):
                for line in body.splitlines():
                    stripped = line.strip()
                    # Skip example-only lines
                    if stripped.startswith("# EXAMPLE ONLY"):
                        continue
                    # Skip directory tree lines (├, └, │ prefixes)
                    if stripped and stripped[0] in "\u251c\u2514\u2502\u2500":
                        continue
                    if _DIRECT_PYTHON_RE.search(stripped):
                        violations.append(
                            f"  {entry.path}: direct Python call in {label or 'unlabeled'} block: {stripped}"
                        )
        assert not violations, (
            f"CR-06 violation — direct Python calls in code blocks:\n"
            + "\n".join(violations)
        )


# ---- CR-07: Tiered fallback structure (command rails only) -----------------

_TIER_A_RE = re.compile(r"Commands by platform|Preferred|```bash", re.IGNORECASE)
_TIER_B_RE = re.compile(r"execution is unavailable|command cannot be executed|paste", re.IGNORECASE)
_TIER_C_RE = re.compile(r"no snapshot is available|proceed\s+using.*context", re.IGNORECASE)


class TestCR07TieredFallback:
    """CR-07: command rails must have preferred command, execution-unavailable fallback, and degraded fallback."""

    @pytest.mark.parametrize(
        "entry",
        _COMMAND_RAILS,
        ids=[e.path for e in _COMMAND_RAILS],
    )
    def test_three_tier_fallback(self, entry: _Entry) -> None:
        content = _read(entry)
        has_a = bool(_TIER_A_RE.search(content))
        has_b = bool(_TIER_B_RE.search(content))
        has_c = bool(_TIER_C_RE.search(content))
        missing: list[str] = []
        if not has_a:
            missing.append("Command block (bash/powershell)")
        if not has_b:
            missing.append("Execution-unavailable fallback (paste)")
        if not has_c:
            missing.append("Degraded fallback (proceed using context)")
        assert not missing, (
            f"CR-07 violation in {entry.path} — missing tiers: {', '.join(missing)}"
        )


# ---- Execution-facing: Launcher name assertion ----------------------------
#   Rail-style-spec v1 requires every execution-facing command rail to invoke
#   the stable launcher name ``opencode-governance-bootstrap`` in at least one
#   code block.  CR-06 already bans direct ``python …`` calls; this assertion
#   confirms the *positive* requirement: the launcher name is present.

_LAUNCHER_NAME = "opencode-governance-bootstrap"


class TestExecutionRailLauncherPresent:
    """Every execution-facing command rail must reference the stable launcher."""

    @pytest.mark.parametrize(
        "entry",
        _COMMAND_RAILS,
        ids=[e.path for e in _COMMAND_RAILS],
    )
    def test_launcher_name_in_code_blocks(self, entry: _Entry) -> None:
        content = _read(entry)
        blocks = _extract_fenced_blocks(content)
        found = any(_LAUNCHER_NAME in body for _label, body in blocks)
        assert found, (
            f"{entry.path}: no code block contains the stable launcher name "
            f"'{_LAUNCHER_NAME}'. Execution-facing rails must invoke the launcher."
        )


class TestExecutionRailLauncherSynthetic:
    """Bad-path: code block without launcher name must be caught."""

    def test_missing_launcher_caught(self) -> None:
        body = "some-other-binary --flag value"
        assert _LAUNCHER_NAME not in body

    def test_present_launcher_passes(self) -> None:
        body = "opencode-governance-bootstrap --session-reader"
        assert _LAUNCHER_NAME in body


# ---- Execution-facing: Fallback minimum content assertion -----------------
#   Rail-style-spec v1 requires the "If execution is unavailable" section of
#   every command rail to contain either "paste the command output" OR the
#   minimum field set: phase, next, active_gate, next_gate_condition.

_FALLBACK_SECTION_RE = re.compile(
    r"## If execution is unavailable\s*\n(.*?)(?=\n## |\Z)",
    re.DOTALL,
)
_FALLBACK_PASTE_RE = re.compile(r"paste\s+the\s+(?:command\s+)?output", re.IGNORECASE)
_FALLBACK_MIN_FIELDS = ["phase", "next", "active_gate", "next_gate_condition"]


class TestExecutionRailFallbackContent:
    """Every execution-facing command rail must have actionable fallback content."""

    @pytest.mark.parametrize(
        "entry",
        _COMMAND_RAILS,
        ids=[e.path for e in _COMMAND_RAILS],
    )
    def test_fallback_has_paste_or_min_fields(self, entry: _Entry) -> None:
        content = _read(entry)
        m = _FALLBACK_SECTION_RE.search(content)
        assert m, (
            f"{entry.path}: missing '## If execution is unavailable' section"
        )
        fallback_text = m.group(1)
        has_paste = bool(_FALLBACK_PASTE_RE.search(fallback_text))
        has_min_fields = all(f"`{field}`" in fallback_text for field in _FALLBACK_MIN_FIELDS)
        assert has_paste or has_min_fields, (
            f"{entry.path}: fallback section must contain either 'paste the command output' "
            f"or the minimum fields {_FALLBACK_MIN_FIELDS} in backtick-quoted form. "
            f"Found neither."
        )


class TestExecutionRailFallbackSynthetic:
    """Bad-path / edge-case tests for fallback content assertion."""

    def test_paste_output_passes(self) -> None:
        text = "ask the user to paste the command output"
        assert _FALLBACK_PASTE_RE.search(text)

    def test_paste_the_output_also_passes(self) -> None:
        text = "ask the user to paste the output"
        assert _FALLBACK_PASTE_RE.search(text)

    def test_min_fields_passes(self) -> None:
        text = "snapshot containing at least `phase`, `next`, `active_gate`, and `next_gate_condition`"
        assert all(f"`{f}`" in text for f in _FALLBACK_MIN_FIELDS)

    def test_empty_fallback_caught(self) -> None:
        text = "If the command cannot be executed, do something vague."
        assert not _FALLBACK_PASTE_RE.search(text)
        assert not all(f"`{f}`" in text for f in _FALLBACK_MIN_FIELDS)

    def test_partial_fields_caught(self) -> None:
        text = "snapshot containing `phase` and `next` only"
        assert not all(f"`{f}`" in text for f in _FALLBACK_MIN_FIELDS)


# ---- CR-08: Over-prompting limit ------------------------------------------


class TestCR08OverPromptingLimit:
    """CR-08: max 3 consecutive MUST/NEVER lines (tables exempt)."""

    @pytest.mark.parametrize(
        "entry",
        _MODEL_RAIL_AND_HYBRID,
        ids=[e.path for e in _MODEL_RAIL_AND_HYBRID],
    )
    def test_no_dense_must_never_runs(self, entry: _Entry) -> None:
        content = _read(entry)
        lines = _lines(content)
        run_start = 0
        run_length = 0
        violations: list[str] = []

        for i, line in enumerate(lines, 1):
            # Tables are exempt
            if _is_table_line(line):
                run_length = 0
                continue
            # Check if line contains MUST or NEVER (case-sensitive per spec)
            if re.search(r"\bMUST\b|\bNEVER\b", line):
                if run_length == 0:
                    run_start = i
                run_length += 1
                if run_length > 3:
                    violations.append(
                        f"  {entry.path}:{run_start}-{i}: "
                        f"run of {run_length} consecutive MUST/NEVER lines"
                    )
            else:
                run_length = 0

        assert not violations, (
            f"CR-08 violation — over-prompting (>3 consecutive MUST/NEVER):\n"
            + "\n".join(violations)
        )


# ---- CR-09: Rail classification tag (detailed check) ----------------------
#   (Also tested in TestInventoryClassificationTag above, but this adds
#    edge-case checks — tag must be an HTML comment, not just any text.)


class TestCR09TagFormat:
    """CR-09: rail-classification tag must be a valid HTML comment in first 10 lines."""

    @pytest.mark.parametrize(
        "entry",
        _MODEL_RAIL_AND_HYBRID,
        ids=[e.path for e in _MODEL_RAIL_AND_HYBRID],
    )
    def test_tag_is_html_comment(self, entry: _Entry) -> None:
        content = _read(entry)
        first_10 = _lines(content)[:10]
        found = False
        for line in first_10:
            if _RAIL_TAG_RE.search(line):
                found = True
                # Verify it's a proper HTML comment (starts with <!-- and ends with -->)
                stripped = line.strip()
                assert stripped.startswith("<!--"), (
                    f"{entry.path}: rail-classification tag must start with '<!--'"
                )
                assert stripped.endswith("-->"), (
                    f"{entry.path}: rail-classification tag must end with '-->'"
                )
                break
        assert found, (
            f"{entry.path}: no rail-classification tag found in first 10 lines (CR-09)"
        )


# ═══════════════════════════════════════════════════════════════════════════
# 4.  SYNTHETIC / BAD-PATH / EDGE-CASE TESTS
# ═══════════════════════════════════════════════════════════════════════════


class TestCR01Synthetic:
    """Bad-path: injected trust-triggering phrases must be caught."""

    def test_safe_to_execute_caught(self) -> None:
        fake_content = "This is safe to execute without review."
        for pat in _CR01_BANNED:
            if pat.search(fake_content):
                return  # correctly detected
        pytest.fail("CR-01 check failed to detect 'safe to execute'")

    def test_governance_installer_caught(self) -> None:
        fake_content = "The governance installer handles setup."
        for pat in _CR01_BANNED:
            if pat.search(fake_content):
                return
        pytest.fail("CR-01 check failed to detect 'governance installer'")

    def test_case_insensitive(self) -> None:
        fake_content = "SAFE TO EXECUTE is always fine."
        for pat in _CR01_BANNED:
            if pat.search(fake_content):
                return
        pytest.fail("CR-01 check should be case-insensitive")


class TestCR02Synthetic:
    """Bad-path: 'authoritative' without backtick ref must be caught."""

    def test_authoritative_without_ref_caught(self) -> None:
        line = "This file is the authoritative source of governance."
        assert "authoritative" in line.lower()
        assert not _BACKTICK_REF_RE.search(line), "test setup: should have no backtick"

    def test_authoritative_with_ref_passes(self) -> None:
        line = "See `phase_api.yaml` for authoritative routing."
        assert "authoritative" in line.lower()
        assert _BACKTICK_REF_RE.search(line), "line with backtick ref should pass"


class TestCR03Synthetic:
    """Bad-path: 'kernel-owned' without backtick ref must be caught."""

    def test_kernel_owned_without_ref_caught(self) -> None:
        line = "This behavior is kernel-owned."
        assert "kernel-owned" in line.lower()
        assert not _BACKTICK_REF_RE.search(line), "test setup: should have no backtick"

    def test_kernel_owned_with_ref_passes(self) -> None:
        line = "Routing is kernel-owned. See `governance/kernel/*`."
        assert "kernel-owned" in line.lower()
        assert _BACKTICK_REF_RE.search(line), "line with backtick ref should pass"

    def test_kernel_owned_in_table_exempt(self) -> None:
        line = "| kernel-owned | kernel code owns this | yes |"
        assert _is_table_line(line), "table line should be recognized"


class TestCR08Synthetic:
    """Edge-case: exactly 3 MUST lines OK, 4 is violation."""

    def test_three_consecutive_ok(self) -> None:
        text = "MUST do X\nMUST do Y\nMUST do Z\nSome normal line."
        lines = _lines(text)
        run = 0
        max_run = 0
        for line in lines:
            if re.search(r"\bMUST\b|\bNEVER\b", line):
                run += 1
                max_run = max(max_run, run)
            else:
                run = 0
        assert max_run == 3, "3 consecutive MUST lines should be the max run"

    def test_four_consecutive_violation(self) -> None:
        text = "MUST do A\nMUST do B\nMUST do C\nMUST do D\nNormal."
        lines = _lines(text)
        run = 0
        max_run = 0
        for line in lines:
            if re.search(r"\bMUST\b|\bNEVER\b", line):
                run += 1
                max_run = max(max_run, run)
            else:
                run = 0
        assert max_run == 4, "4 consecutive MUST lines should be caught"
        assert max_run > 3, "This should be a violation"

    def test_table_lines_break_run(self) -> None:
        text = "MUST do A\nMUST do B\n| MUST in table |\nMUST do C\nMUST do D"
        lines = _lines(text)
        run = 0
        max_run = 0
        for line in lines:
            if _is_table_line(line):
                run = 0
                continue
            if re.search(r"\bMUST\b|\bNEVER\b", line):
                run += 1
                max_run = max(max_run, run)
            else:
                run = 0
        assert max_run <= 3, "Table line should reset the MUST/NEVER run counter"


class TestCR09Synthetic:
    """Edge-case: tag on line 10 is OK, line 11 is not."""

    def test_tag_on_line_10_ok(self) -> None:
        lines = ["line"] * 9 + ["<!-- rail-classification: TEST -->"]
        first_10 = "\n".join(lines[:10])
        assert _RAIL_TAG_RE.search(first_10)

    def test_tag_on_line_11_fails(self) -> None:
        lines = ["line"] * 10 + ["<!-- rail-classification: TEST -->"]
        first_10 = "\n".join(lines[:10])
        assert not _RAIL_TAG_RE.search(first_10)


class TestCR05Synthetic:
    """Bad-path: Windows syntax in bash block must be caught."""

    def test_set_in_bash_caught(self) -> None:
        body = 'set "PATH=C:\\foo" && command'
        for pat in _WINDOWS_IN_BASH:
            if pat.search(body):
                return
        pytest.fail("Windows set command should be caught in bash block")

    def test_percent_var_in_bash_caught(self) -> None:
        body = "echo %USERPROFILE%"
        for pat in _WINDOWS_IN_BASH:
            if pat.search(body):
                return
        pytest.fail("%VAR% should be caught in bash block")

    def test_unix_in_cmd_caught(self) -> None:
        body = "export PATH=/usr/local/bin:$PATH"
        for pat in _UNIX_IN_CMD:
            if pat.search(body):
                return
        pytest.fail("Unix export should be caught in cmd block")


class TestCR06Synthetic:
    """Bad-path: direct Python calls must be caught."""

    def test_python_space_caught(self) -> None:
        assert _DIRECT_PYTHON_RE.search("python governance/install.py")

    def test_python3_caught(self) -> None:
        assert _DIRECT_PYTHON_RE.search("python3 -m governance")

    def test_py_dash_3_caught(self) -> None:
        assert _DIRECT_PYTHON_RE.search("py -3 install.py")

    def test_launcher_passes(self) -> None:
        assert not _DIRECT_PYTHON_RE.search("opencode-governance-bootstrap install")


# ═══════════════════════════════════════════════════════════════════════════
# 5.  EXECUTION-RAIL DENSITY GUARDS
# ═══════════════════════════════════════════════════════════════════════════
#   These guards enforce operative minimalism on execution-facing rails.
#   They are additive to CR-01..CR-09 (no duplication).

_HEADING_RE = re.compile(r"^#{1,6}\s")
_BULLET_RE = re.compile(r"^\s*[-*]\s")
_RESPONSE_SHAPE_SECTION_RE = re.compile(
    r"## Response shape\s*\n(.*?)(?=\n## |\n---|\n[A-Z][^\n]*:\s*\n|\Z)",
    re.DOTALL,
)

# Density caps — intentionally generous; tighten after guidance-core refactor
_MAX_HEADINGS_PER_RAIL = 9
_MAX_LINES_PER_RAIL = 75
_MAX_RESPONSE_SHAPE_BULLETS = 4

# Guidance vocabulary banned from execution-facing rails
_GUIDANCE_VOCAB_RE = re.compile(
    r"\bkernel-owned\b|\bschema-owned\b|\bkernel- and schema-owned\b",
    re.IGNORECASE,
)


class TestExecutionRailDensity:
    """Density guards: execution rails must stay at operative minimum."""

    @pytest.mark.parametrize(
        "entry",
        _EXECUTION_RAILS,
        ids=[e.path for e in _EXECUTION_RAILS],
    )
    def test_max_headings(self, entry: _Entry) -> None:
        content = _read(entry)
        heading_count = sum(1 for line in _lines(content) if _HEADING_RE.match(line))
        assert heading_count <= _MAX_HEADINGS_PER_RAIL, (
            f"{entry.path}: {heading_count} headings exceeds cap of "
            f"{_MAX_HEADINGS_PER_RAIL}. Execution rails must stay minimal."
        )

    @pytest.mark.parametrize(
        "entry",
        _EXECUTION_RAILS,
        ids=[e.path for e in _EXECUTION_RAILS],
    )
    def test_max_total_lines(self, entry: _Entry) -> None:
        content = _read(entry)
        line_count = len(_lines(content))
        assert line_count <= _MAX_LINES_PER_RAIL, (
            f"{entry.path}: {line_count} lines exceeds cap of "
            f"{_MAX_LINES_PER_RAIL}. Execution rails must stay compact."
        )

    @pytest.mark.parametrize(
        "entry",
        _EXECUTION_RAILS,
        ids=[e.path for e in _EXECUTION_RAILS],
    )
    def test_max_response_shape_bullets(self, entry: _Entry) -> None:
        content = _read(entry)
        m = _RESPONSE_SHAPE_SECTION_RE.search(content)
        if m is None:
            pytest.skip(f"{entry.path}: no Response shape section found")
        section_text = m.group(1)
        bullet_count = sum(1 for line in section_text.splitlines() if _BULLET_RE.match(line))
        assert bullet_count <= _MAX_RESPONSE_SHAPE_BULLETS, (
            f"{entry.path}: Response shape has {bullet_count} bullets, "
            f"exceeds cap of {_MAX_RESPONSE_SHAPE_BULLETS}."
        )

    @pytest.mark.parametrize(
        "entry",
        _EXECUTION_RAILS,
        ids=[e.path for e in _EXECUTION_RAILS],
    )
    def test_no_guidance_vocabulary(self, entry: _Entry) -> None:
        content = _read(entry)
        # Strip fenced code blocks (command examples may contain anything)
        stripped = _strip_fenced_blocks(content)
        violations: list[str] = []
        for i, line in enumerate(_lines(stripped), 1):
            if _GUIDANCE_VOCAB_RE.search(line):
                violations.append(f"  {entry.path}:{i}: {line.strip()}")
        assert not violations, (
            f"Execution rails must not use guidance vocabulary "
            f"(kernel-owned, schema-owned):\n" + "\n".join(violations)
        )


class TestExecutionRailFreeTextGuard:
    """Every mutating execution rail must have a free-text guard."""

    _MUTATING_RAILS = [
        e for e in _EXECUTION_RAILS
        if e.path in {"continue.md", "ticket.md", "plan.md"}
    ]

    @pytest.mark.parametrize(
        "entry",
        _MUTATING_RAILS,
        ids=[e.path for e in _MUTATING_RAILS],
    )
    def test_free_text_guard_present(self, entry: _Entry) -> None:
        content = _read(entry)
        assert "free-text guard" in content.lower(), (
            f"{entry.path}: mutating execution rail must contain a free-text guard"
        )


class TestExecutionRailDensitySynthetic:
    """Synthetic tests for density guard helpers."""

    def test_heading_regex_matches(self) -> None:
        assert _HEADING_RE.match("## Purpose")
        assert _HEADING_RE.match("### Sub heading")
        assert not _HEADING_RE.match("Not a heading")

    def test_bullet_regex_matches(self) -> None:
        assert _BULLET_RE.match("- item one")
        assert _BULLET_RE.match("  * nested item")
        assert not _BULLET_RE.match("plain text")

    def test_guidance_vocab_caught(self) -> None:
        assert _GUIDANCE_VOCAB_RE.search("This is kernel-owned behavior")
        assert _GUIDANCE_VOCAB_RE.search("Format is schema-owned")
        assert _GUIDANCE_VOCAB_RE.search("X is kernel- and schema-owned")

    def test_guidance_vocab_clean(self) -> None:
        assert not _GUIDANCE_VOCAB_RE.search("Use the YAML output as governance context")
        assert not _GUIDANCE_VOCAB_RE.search("The command is mutating")
