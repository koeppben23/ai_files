"""O3 density and regression guards for compressed support docs.

Prevents regression of the O3 wave optimizations:
- README-OPENCODE.md model-operative scope compression
- QUICKSTART.md install-bootstrap-start focus
- audit-readout.md fallback minimalism
- README.md authority language removal

Test coverage: Happy, Bad, Edge, Corner cases.

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.util import REPO_ROOT


def _read(relpath: str) -> str:
    """Read a file relative to REPO_ROOT, fail fast if missing."""
    p = REPO_ROOT / relpath
    assert p.exists(), f"Expected file not found: {relpath}"
    return p.read_text(encoding="utf-8")


# ===================================================================
# 1. README-OPENCODE.md — model-operative scope guards
# ===================================================================


class TestReadmeOpencodeHappy:
    """README-OPENCODE.md must stay focused on model-operative content."""

    def test_fallback_section_exists(self) -> None:
        """Compressed fallback section must exist."""
        content = _read("README-OPENCODE.md")
        assert "## If execution is unavailable" in content

    def test_lifecycle_section_exists(self) -> None:
        """OpenCode Lifecycle section must exist."""
        content = _read("README-OPENCODE.md")
        assert "## OpenCode Lifecycle" in content


class TestReadmeOpencodeBad:
    """Detect regression of removed operator/speculation sections."""

    def test_no_tier_matrix(self) -> None:
        """README-OPENCODE.md must NOT contain the removed Tier/Matrix."""
        content = _read("README-OPENCODE.md")
        assert "Compatibility matrix" not in content, (
            "README-OPENCODE.md must not contain 'Compatibility matrix' — "
            "removed in O3-F1"
        )

    def test_no_three_tier_contract(self) -> None:
        """README-OPENCODE.md must NOT contain three-tier resume contract."""
        content = _read("README-OPENCODE.md")
        assert "three-tier" not in content.lower(), (
            "README-OPENCODE.md must not contain 'three-tier' — "
            "replaced by single fallback sentence in O3-F1"
        )

    def test_no_response_rendering_section(self) -> None:
        """README-OPENCODE.md must NOT contain the removed rendering section."""
        content = _read("README-OPENCODE.md")
        assert "Response rendering" not in content, (
            "README-OPENCODE.md must not contain 'Response rendering' — "
            "operator debugging section removed in O3-F1"
        )


class TestReadmeOpencodeEdge:
    """Edge: density cap prevents future bloat."""

    def test_density_cap(self) -> None:
        """README-OPENCODE.md must not exceed 90 lines."""
        content = _read("README-OPENCODE.md")
        line_count = len(content.strip().splitlines())
        assert line_count <= 90, (
            f"README-OPENCODE.md has {line_count} lines (cap: 90). "
            "Compress or move content to operator docs."
        )


class TestReadmeOpencodeCorner:
    """Corner: fallback section must be minimal — no speculation."""

    def test_fallback_no_tier_language(self) -> None:
        """Fallback section must not contain tier/compatibility language."""
        content = _read("README-OPENCODE.md")
        start = content.find("## If execution is unavailable")
        assert start >= 0
        # Find next section or end
        next_section = content.find("\n## ", start + 1)
        if next_section < 0:
            next_section = len(content)
        section = content[start:next_section].lower()
        forbidden = ["tier", "compatibility", "fallback a", "fallback b",
                      "fallback c", "sandboxed"]
        for word in forbidden:
            assert word not in section, (
                f"README-OPENCODE.md fallback section must not contain "
                f"'{word}' — must stay minimal"
            )


# ===================================================================
# 2. QUICKSTART.md — install-bootstrap-start focus guards
# ===================================================================


class TestQuickstartHappy:
    """QUICKSTART.md must stay focused on the three-step flow."""

    def test_three_steps_present(self) -> None:
        """QUICKSTART.md must have Install, Bootstrap, and Continue steps."""
        content = _read("QUICKSTART.md")
        assert "## Step 1:" in content
        assert "## Step 2:" in content
        assert "## Step 3:" in content


class TestQuickstartBad:
    """Detect regression of removed sections."""

    def test_no_upgrade_section(self) -> None:
        """QUICKSTART.md must NOT contain upgrade/rollback sections."""
        content = _read("QUICKSTART.md")
        assert "Quick Upgrade" not in content, (
            "QUICKSTART.md must not contain 'Quick Upgrade' — "
            "moved to operator-runbook in O3-F2"
        )

    def test_no_rollback_section(self) -> None:
        """QUICKSTART.md must NOT contain rollback section."""
        content = _read("QUICKSTART.md")
        assert "Quick Rollback" not in content, (
            "QUICKSTART.md must not contain 'Quick Rollback' — "
            "moved to operator-runbook in O3-F2"
        )


class TestQuickstartEdge:
    """Edge: density cap and launcher-first in workflow."""

    def test_density_cap(self) -> None:
        """QUICKSTART.md must not exceed 130 lines."""
        content = _read("QUICKSTART.md")
        line_count = len(content.strip().splitlines())
        assert line_count <= 130, (
            f"QUICKSTART.md has {line_count} lines (cap: 130). "
            "Compress or move content to operator docs."
        )

    def test_start_new_work_has_launcher(self) -> None:
        """'Start new work' section must reference the launcher."""
        content = _read("QUICKSTART.md")
        start = content.find("Start new work")
        assert start >= 0
        next_section = content.find("**Debug", start)
        if next_section < 0:
            next_section = len(content)
        section = content[start:next_section]
        assert "opencode-governance-bootstrap" in section, (
            "QUICKSTART.md 'Start new work' section must reference "
            "the launcher (opencode-governance-bootstrap)"
        )


class TestQuickstartCorner:
    """Corner: no direct python entrypoint calls in workflow section."""

    def test_no_direct_python_in_workflow(self) -> None:
        """'Start new work' section must NOT contain direct python calls."""
        content = _read("QUICKSTART.md")
        start = content.find("Start new work")
        assert start >= 0
        next_section = content.find("**Debug", start)
        if next_section < 0:
            next_section = len(content)
        section = content[start:next_section]
        assert "python3 -m" not in section, (
            "QUICKSTART.md 'Start new work' must not use python3 -m — "
            "use launcher equivalent"
        )
        assert "python scripts/" not in section, (
            "QUICKSTART.md 'Start new work' must not use python scripts/ — "
            "use launcher equivalent"
        )


# ===================================================================
# 3. audit-readout.md — fallback minimalism guard
# ===================================================================


class TestAuditReadoutFallbackHappy:
    """audit-readout.md fallback must be minimal."""

    def test_fallback_exists(self) -> None:
        """Fallback section must exist."""
        content = _read("audit-readout.md")
        assert "## If execution is unavailable" in content


class TestAuditReadoutFallbackCorner:
    """Corner: fallback must not enumerate speculative reasons."""

    def test_no_reason_enumeration(self) -> None:
        """Fallback must NOT speculate about why execution is unavailable."""
        content = _read("audit-readout.md")
        assert "sandboxed environment" not in content, (
            "audit-readout.md must not contain 'sandboxed environment' — "
            "not operative minimum"
        )
        assert "model policy" not in content.lower(), (
            "audit-readout.md must not contain 'model policy' — "
            "not operative minimum"
        )


# ===================================================================
# 4. README.md — authority language guard
# ===================================================================


class TestReadmeAuthorityHappy:
    """README.md /review line must not contain authority language."""

    def test_review_line_no_authoritative(self) -> None:
        """README.md /review description must not use 'authoritative'."""
        content = _read("README.md")
        for line in content.split("\n"):
            if "/review" in line and "read-only rail entrypoint" in line:
                assert "authoritative" not in line.lower(), (
                    f"README.md /review line must not contain 'authoritative' — "
                    f"authority language removed in O3-F3: {line.strip()}"
                )
