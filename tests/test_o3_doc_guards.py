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
    """QUICKSTART.md must stay focused on the four-step flow."""

    def test_four_steps_present(self) -> None:
        """QUICKSTART.md must have Install, Verify, Bootstrap, and Continue steps."""
        content = _read("QUICKSTART.md")
        assert "## Step 1:" in content
        assert "## Step 2:" in content
        assert "## Step 3:" in content
        assert "## Step 4:" in content


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
    """Edge: density cap and launcher-first quickstart examples."""

    def test_density_cap(self) -> None:
        """QUICKSTART.md must not exceed 130 lines."""
        content = _read("QUICKSTART.md")
        line_count = len(content.strip().splitlines())
        assert line_count <= 130, (
            f"QUICKSTART.md has {line_count} lines (cap: 130). "
            "Compress or move content to operator docs."
        )

    def test_bootstrap_step_has_launcher(self) -> None:
        """Step 3 bootstrap section must reference the launcher."""
        content = _read("QUICKSTART.md")
        start = content.find("## Step 3:")
        assert start >= 0
        next_section = content.find("## Step 4:", start)
        if next_section < 0:
            next_section = len(content)
        section = content[start:next_section]
        assert "opencode-governance-bootstrap" in section, (
            "QUICKSTART.md bootstrap section must reference "
            "the launcher (opencode-governance-bootstrap)"
        )


class TestQuickstartCorner:
    """Corner: no runbook overhang in quickstart."""

    def test_no_runbook_overhang_sections(self) -> None:
        """QUICKSTART.md must not contain workflow/debug/runbook overhang."""
        content = _read("QUICKSTART.md")
        assert "### Common Workflows" not in content
        assert "Debug blocked run" not in content
        assert "Operator runbook" not in content


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


# ===================================================================
# 5. Cross-doc O3 surface guards
# ===================================================================


class TestO3SurfaceBad:
    """Prevent regression to deprecated command and entrypoint surfaces."""

    _DOCS = ["README-OPENCODE.md", "QUICKSTART.md", "README.md", "docs/operator-runbook.md"]

    @pytest.mark.parametrize("relpath", _DOCS)
    def test_no_direct_governance_entrypoint_calls(self, relpath: str) -> None:
        content = _read(relpath)
        assert "governance.entrypoints." not in content, (
            f"{relpath} must not include direct governance.entrypoints.* calls"
        )

    @pytest.mark.parametrize("relpath", _DOCS)
    def test_no_resume_command(self, relpath: str) -> None:
        content = _read(relpath)
        assert "/resume" not in content, (
            f"{relpath} must not include deprecated /resume command"
        )

    @pytest.mark.parametrize("relpath", _DOCS)
    def test_no_audit_short_command(self, relpath: str) -> None:
        content = _read(relpath)
        assert re.search(r"/audit(?![-a-zA-Z0-9_])", content) is None, (
            f"{relpath} must not include deprecated /audit command"
        )


class TestO3SurfaceEdge:
    """Enforce launcher-first examples and avoid user-absolute primaries."""

    def test_no_absolute_primary_launcher_paths(self) -> None:
        combined = "\n".join(_read(p) for p in ["README-OPENCODE.md", "QUICKSTART.md"])
        assert "~/.config/opencode/bin/" not in combined
        assert "%USERPROFILE%\\.config\\opencode\\bin\\" not in combined

    def test_launcher_command_present(self) -> None:
        combined = "\n".join(_read(p) for p in ["README-OPENCODE.md", "QUICKSTART.md", "README.md"])
        assert "opencode-governance-bootstrap" in combined


class TestO3SurfaceHappy:
    """Current command surfaces remain discoverable."""

    def test_current_commands_present(self) -> None:
        content = "\n".join(_read(p) for p in ["README-OPENCODE.md", "QUICKSTART.md"])
        required = ["/continue", "/ticket", "/plan", "/review", "/audit-readout"]
        for cmd in required:
            assert cmd in content, f"Missing expected command in O3 docs: {cmd}"


class TestO3ActiveCatalogGuards:
    """Ensure active governance catalogs do not regress to legacy command wording."""

    _ACTIVE_CATALOGS = [
        "governance/assets/reasons/blocked_reason_catalog.yaml",
        "governance/assets/config/blocked_reason_catalog.yaml",
        "governance/assets/catalogs/reason_codes.registry.json",
        "SESSION_STATE_SCHEMA.md",
        "phase_api.yaml",
    ]

    @pytest.mark.parametrize("relpath", _ACTIVE_CATALOGS)
    def test_no_resume_pointer_or_reload_alias(self, relpath: str) -> None:
        content = _read(relpath)
        assert "resume_pointer" not in content
        assert "/reload-addons" not in content
