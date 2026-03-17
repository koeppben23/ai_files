"""Documentation invariant guard tests.

Validates cross-file invariants established during the MD-rails-robustness
overhaul.  Every test here guards against regression of a specific P0 or P1
audit finding.

Test coverage: Happy, Bad, Edge, Corner cases.

Copyright 2026 Benjamin Fuchs. All rights reserved. See LICENSE.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.util import REPO_ROOT, get_docs_path, read_text

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DOCS = get_docs_path()


def _read(relpath: str) -> str:
    """Read a file relative to REPO_ROOT, fail fast if missing."""
    p = REPO_ROOT / relpath
    try:
        return read_text(p)
    except FileNotFoundError:
        assert False, f"Expected file not found: {relpath}"


def _exists_repo_path(relpath: str) -> bool:
    try:
        _ = read_text(REPO_ROOT / relpath)
        return True
    except FileNotFoundError:
        return False


# ===================================================================
# 1. /review canonical framing invariant
#    - Allowed: "read-only rail entrypoint"
#    - Forbidden: "review-only rail" (when describing /review),
#      "Phase 4 review-only path", "at Phase 4" directly in /review
#      command labels
# ===================================================================


# Files that describe the /review command and must use canonical framing
_REVIEW_FRAMING_FILES = [
    "QUICKSTART.md",
    "README.md",
    "README-OPENCODE.md",
    "docs/phases.md",
    "review.md",
]


class TestReviewFramingHappy:
    """/review must be framed as 'read-only rail entrypoint' everywhere."""

    @pytest.mark.parametrize("relpath", _REVIEW_FRAMING_FILES)
    def test_canonical_framing_present_where_review_mentioned(
        self, relpath: str
    ) -> None:
        """Files that describe /review must use the canonical framing."""
        content = _read(relpath)
        # Only enforce if the file actually mentions /review
        if "/review" not in content:
            pytest.skip(f"{relpath} does not mention /review")
        assert "read-only rail entrypoint" in content, (
            f"{relpath} mentions /review but does not use the canonical "
            "'read-only rail entrypoint' framing"
        )


class TestReviewFramingBad:
    """Detect forbidden /review framing patterns across all docs."""

    # Files where the old framing could regress
    _ALL_MD_FILES = sorted(
        str(p.relative_to(REPO_ROOT).as_posix())
        for p in REPO_ROOT.rglob("*.md")
        if not any(
            part.startswith((".", "_archive", "node_modules", ".git"))
            for part in p.relative_to(REPO_ROOT).parts
        )
    )

    @pytest.mark.parametrize("relpath", _ALL_MD_FILES)
    def test_no_review_only_rail_framing(self, relpath: str) -> None:
        """No MD file may frame /review as 'review-only rail' in a command context.

        Note: The phrase 'review-only rail' is forbidden when describing /review.
        Phase 4 row in phases.md should say 'read-only rail entrypoint'.
        """
        content = _read(relpath)
        # Match "review-only rail" only when it appears near /review context
        # The exact banned pattern: "review-only rail" as a standalone descriptor
        if "/review" not in content:
            return  # Not relevant for this file
        assert "review-only rail" not in content, (
            f"{relpath} uses banned framing 'review-only rail' — "
            "must use 'read-only rail entrypoint'"
        )

    @pytest.mark.parametrize("relpath", _ALL_MD_FILES)
    def test_no_phase4_review_only_path(self, relpath: str) -> None:
        """No MD file may use 'Phase 4 review-only path' framing."""
        content = _read(relpath)
        assert "phase 4 review-only" not in content.lower(), (
            f"{relpath} uses banned framing 'Phase 4 review-only' — "
            "the authoritative review gate is Phase 5"
        )


class TestReviewFramingEdge:
    """Edge: command table labels must not tie /review to a specific phase."""

    def test_quickstart_review_row_no_phase_reference(self) -> None:
        """QUICKSTART.md /review table row must not reference 'Phase 4'."""
        content = _read("QUICKSTART.md")
        # Find the command table row for /review
        for line in content.split("\n"):
            if "| `/review`" in line:
                assert "Phase 4" not in line, (
                    "QUICKSTART.md /review table row must not reference Phase 4 — "
                    f"found: {line.strip()}"
                )
                # It must contain the canonical framing
                assert "read-only rail entrypoint" in line.lower() or "read-only rail entrypoint" in line, (
                    "QUICKSTART.md /review table row must contain "
                    "'Read-only rail entrypoint'"
                )

    def test_quickstart_prose_review_no_phase4(self) -> None:
        """QUICKSTART.md prose about /review must not use 'in Phase 4'."""
        content = _read("QUICKSTART.md")
        for line in content.split("\n"):
            if "/review" in line and "Phase 4" in line:
                # Allow lines about /continue landing at Phase 4 (that's different)
                if "/continue" in line:
                    continue
                pytest.fail(
                    f"QUICKSTART.md ties /review to Phase 4: {line.strip()}"
                )


class TestReviewFramingCorner:
    """Corner: phases.md Phase 4 row may mention /review but must use canonical term."""

    def test_phases_md_phase4_row_canonical(self) -> None:
        """phases.md Phase 4 row mentioning /review must use 'read-only rail entrypoint'."""
        content = _read("docs/phases.md")
        for line in content.split("\n"):
            if "Phase 4" in line and "/review" in line:
                assert "read-only rail entrypoint" in line, (
                    f"docs/phases.md Phase 4 row mentions /review but uses wrong framing: "
                    f"{line.strip()}"
                )

    def test_review_md_itself_uses_canonical_framing(self) -> None:
        """review.md must self-describe as 'read-only rail entrypoint'."""
        content = _read("review.md")
        assert "read-only rail entrypoint" in content, (
            "review.md must contain 'read-only rail entrypoint' self-description"
        )


# ===================================================================
# 2. Phase 5 semantics invariant
#    - Phase 5 = review gate ONLY
#    - No code output/emission during Phase 5
#    - Implementation begins at Phase 6
# ===================================================================


class TestPhase5SemanticsHappy:
    """Phase 5 must be framed as review gate with no code output."""

    def test_quality_index_no_phase5_code_emission(self) -> None:
        """QUALITY_INDEX.md must not reference 'Phase 5 code emission'."""
        content = _read("QUALITY_INDEX.md")
        assert "phase 5 code emission" not in content.lower(), (
            "QUALITY_INDEX.md must not reference 'Phase 5 code emission' — "
            "Phase 5 is a review gate, not a code-producing phase"
        )

    def test_quality_index_uses_implementation_readiness(self) -> None:
        """QUALITY_INDEX.md must use 'implementation readiness' framing."""
        content = _read("QUALITY_INDEX.md")
        assert "implementation readiness" in content.lower(), (
            "QUALITY_INDEX.md must use 'implementation readiness' framing "
            "instead of 'Phase 5 code emission'"
        )

    def test_master_md_phase5_no_code_output(self) -> None:
        """master.md must explicitly prohibit code output during Phase 5."""
        content = _read("master.md").lower()
        assert "not permitted during phase 5" in content, (
            "master.md must state code-producing output is "
            "'not permitted during Phase 5'"
        )


class TestPhase5SemanticsBad:
    """Detect any doc that implies code production during Phase 5."""

    _GOVERNANCE_MD = sorted(
        str(p.relative_to(REPO_ROOT).as_posix())
        for p in list(REPO_ROOT.glob("*.md")) + list(DOCS.rglob("*.md"))
        if not any(
            part.startswith((".", "_archive", "node_modules", ".git"))
            for part in p.relative_to(REPO_ROOT).parts
        )
    )

    @pytest.mark.parametrize("relpath", _GOVERNANCE_MD)
    def test_no_phase5_code_emission_anywhere(self, relpath: str) -> None:
        """No governance doc may use 'Phase 5 code emission'."""
        content = _read(relpath)
        assert "phase 5 code emission" not in content.lower(), (
            f"{relpath} uses banned phrase 'Phase 5 code emission' — "
            "Phase 5 is a review gate; code emission does not occur there"
        )


class TestPhase5SemanticsEdge:
    """Edge: quality index must still have a usage section with meaningful guidance."""

    def test_quality_index_usage_section_exists(self) -> None:
        """QUALITY_INDEX.md must have a Usage section after the fix."""
        content = _read("QUALITY_INDEX.md")
        assert "## Usage" in content
        # The usage section must contain at least 2 bullet points
        usage_start = content.index("## Usage")
        usage_section = content[usage_start:]
        bullets = [l for l in usage_section.split("\n") if l.strip().startswith("- ")]
        assert len(bullets) >= 2, (
            "QUALITY_INDEX.md Usage section must have at least 2 bullet points"
        )


class TestPhase5SemanticsCorner:
    """Corner: 'Phase 5' CAN appear in docs — just not as 'Phase 5 code emission'."""

    def test_phase5_mention_allowed_in_master(self) -> None:
        """master.md may mention Phase 5 (it's the review gate)."""
        content = _read("master.md")
        assert "phase 5" in content.lower(), (
            "master.md must reference Phase 5 as the review gate"
        )

    def test_phase5_mention_allowed_in_phases(self) -> None:
        """docs/phases.md must document Phase 5 as Lead Architect Review."""
        content = _read("docs/phases.md")
        assert "Phase 5 - Lead Architect Review" in content


# ===================================================================
# 3. Catalog path invariant
#    - Benchmark packs and policy JSON live under
#      governance/assets/catalogs/, NOT governance/
#    - governance/security-evidence/ is a runtime output dir (allowed)
# ===================================================================

# Files that reference benchmark packs or policy JSON
_CATALOG_REF_FILES = [
    "docs/security-gates.md",
    "docs/quality-benchmark-pack-matrix.md",
    "docs/python-quality-benchmark-pack.md",
    "docs/benchmarks.md",
]

# Pattern: governance/<FILENAME>.json but NOT governance/assets/...
# Also excludes governance/security-evidence/ (runtime output dir)
# and governance/benchmark-results/ (runtime output dir)
_STALE_CATALOG_RE = re.compile(
    r"`governance/(?!assets/)(?!security-evidence/)(?!benchmark-results/)"
    r"[A-Z][A-Z0-9_]*\.(json)`"
)

# Stricter: any backtick-quoted path to a JSON file under governance/ that
# doesn't go through assets/catalogs/ and isn't a known runtime dir
_STALE_GOVERNANCE_JSON_RE = re.compile(
    r"`governance/(?!assets/)(?!security-evidence/)(?!benchmark-results/)"
    r"[\w./]*\.json`"
)


class TestCatalogPathsHappy:
    """All catalog JSON refs must point to governance/assets/catalogs/."""

    @pytest.mark.parametrize("relpath", _CATALOG_REF_FILES)
    def test_no_stale_governance_json_paths(self, relpath: str) -> None:
        """Docs must not reference governance/<FILE>.json directly."""
        content = _read(relpath)
        matches = _STALE_GOVERNANCE_JSON_RE.findall(content)
        assert not matches, (
            f"{relpath} has stale governance/*.json path(s): {matches} — "
            "these should be governance/assets/catalogs/*.json"
        )

    def test_security_gates_uses_catalogs_path(self) -> None:
        """security-gates.md must reference the catalogs path for policy."""
        content = _read("docs/security-gates.md")
        assert "governance/assets/catalogs/SECURITY_GATE_POLICY.json" in content

    def test_benchmark_matrix_uses_catalogs_paths(self) -> None:
        """quality-benchmark-pack-matrix.md must use catalogs paths."""
        content = _read("docs/quality-benchmark-pack-matrix.md")
        assert "governance/assets/catalogs/BACKEND_JAVA_QUALITY_BENCHMARK_PACK.json" in content
        assert "governance/assets/catalogs/PYTHON_QUALITY_BENCHMARK_PACK.json" in content
        assert "governance/assets/catalogs/FALLBACK_MINIMUM_QUALITY_BENCHMARK_PACK.json" in content


class TestCatalogPathsBad:
    """Detect any direct governance/*.json reference that should be in catalogs."""

    @pytest.mark.parametrize("relpath", _CATALOG_REF_FILES)
    def test_no_bare_governance_pack_refs(self, relpath: str) -> None:
        """No doc may reference governance/XYZ_QUALITY_BENCHMARK_PACK.json directly."""
        content = _read(relpath)
        # Specific pattern for benchmark packs without assets/catalogs/
        bare_pack = re.findall(
            r"`governance/[A-Z_]+_QUALITY_BENCHMARK_PACK\.json`", content
        )
        assert not bare_pack, (
            f"{relpath} has bare governance/ benchmark pack ref(s): {bare_pack}"
        )


class TestCatalogPathsEdge:
    """Edge: governance/security-evidence/ paths are runtime dirs — leave them alone."""

    def test_security_evidence_dir_refs_preserved(self) -> None:
        """security-gates.md may still reference governance/security-evidence/."""
        content = _read("docs/security-gates.md")
        assert "governance/security-evidence/" in content, (
            "security-gates.md must still reference governance/security-evidence/ "
            "(runtime output directory)"
        )

    def test_benchmarks_landing_page_uses_catalogs_glob(self) -> None:
        """benchmarks.md landing page must use catalogs glob path."""
        content = _read("docs/benchmarks.md")
        assert "governance/assets/catalogs/*_QUALITY_BENCHMARK_PACK.json" in content


class TestCatalogPathsCorner:
    """Corner: the actual catalog files must exist on disk for every docs reference."""

    _PACK_NAMES = [
        "BACKEND_JAVA_QUALITY_BENCHMARK_PACK",
        "PYTHON_QUALITY_BENCHMARK_PACK",
        "FRONTEND_ANGULAR_NX_QUALITY_BENCHMARK_PACK",
        "OPENAPI_CONTRACTS_QUALITY_BENCHMARK_PACK",
        "CUCUMBER_BDD_QUALITY_BENCHMARK_PACK",
        "POSTGRES_LIQUIBASE_QUALITY_BENCHMARK_PACK",
        "FRONTEND_CYPRESS_TESTING_QUALITY_BENCHMARK_PACK",
        "FRONTEND_OPENAPI_TS_CLIENT_QUALITY_BENCHMARK_PACK",
        "DOCS_GOVERNANCE_QUALITY_BENCHMARK_PACK",
        "FALLBACK_MINIMUM_QUALITY_BENCHMARK_PACK",
    ]

    @pytest.mark.parametrize("pack_name", _PACK_NAMES)
    def test_referenced_pack_file_exists(self, pack_name: str) -> None:
        """Every benchmark pack referenced in the matrix must exist on disk."""
        path = REPO_ROOT / "governance" / "assets" / "catalogs" / f"{pack_name}.json"
        assert path.exists(), (
            f"Benchmark pack referenced in docs does not exist: {path.relative_to(REPO_ROOT)}"
        )

    def test_security_gate_policy_exists(self) -> None:
        """SECURITY_GATE_POLICY.json must exist at the catalogs path."""
        path = REPO_ROOT / "governance" / "assets" / "catalogs" / "SECURITY_GATE_POLICY.json"
        assert path.exists(), (
            f"SECURITY_GATE_POLICY.json not found at {path.relative_to(REPO_ROOT)}"
        )


# ===================================================================
# 4. Technology scope invariant
#    - SCOPE-AND-CONTEXT.md must not claim non-Java stacks are out of scope
#    - Must acknowledge existing multi-stack governance profiles
# ===================================================================


class TestTechScopeHappy:
    """SCOPE-AND-CONTEXT.md must reflect multi-stack reality."""

    def test_no_non_java_stacks_exclusion(self) -> None:
        """SCOPE-AND-CONTEXT.md must not blanket-exclude non-Java stacks."""
        content = _read("SCOPE-AND-CONTEXT.md")
        assert "Non-Java stacks" not in content, (
            "SCOPE-AND-CONTEXT.md must not claim 'Non-Java stacks' are out of scope — "
            "governance profiles exist for Python, Angular/Nx, Cypress, OpenAPI contracts"
        )

    def test_acknowledges_governance_profiles(self) -> None:
        """SCOPE-AND-CONTEXT.md must mention governance profiles for supported stacks."""
        content = _read("SCOPE-AND-CONTEXT.md")
        assert "governance profile" in content.lower(), (
            "SCOPE-AND-CONTEXT.md must reference governance profiles"
        )


class TestTechScopeBad:
    """Detect stale tech scope claims."""

    def test_no_java_only_framing(self) -> None:
        """SCOPE-AND-CONTEXT.md must not imply Java-only support."""
        content = _read("SCOPE-AND-CONTEXT.md").lower()
        # Check that the file doesn't blanket say "only java" or "java only"
        assert "java only" not in content and "only java" not in content, (
            "SCOPE-AND-CONTEXT.md must not imply Java-only governance support"
        )


class TestTechScopeEdge:
    """Edge: the exclusion must still scope what IS out of scope."""

    def test_stacks_without_profile_still_excluded(self) -> None:
        """Stacks without a governance profile should still be out of scope."""
        content = _read("SCOPE-AND-CONTEXT.md")
        assert "without a governance profile" in content.lower(), (
            "SCOPE-AND-CONTEXT.md must clarify that stacks without a "
            "governance profile are out of scope"
        )


class TestTechScopeCorner:
    """Corner: known supported stacks must be named in the scope clarification."""

    _EXPECTED_STACKS = ["Java", "Python", "Angular"]

    @pytest.mark.parametrize("stack", _EXPECTED_STACKS)
    def test_supported_stack_named(self, stack: str) -> None:
        """Each supported stack with a governance profile must be named."""
        content = _read("SCOPE-AND-CONTEXT.md")
        assert stack in content, (
            f"SCOPE-AND-CONTEXT.md must name '{stack}' as a supported stack "
            "with a governance profile"
        )


# ===================================================================
# 5. SECURITY_MODEL.md references invariant
#    - Module refs must point to files that actually exist
#    - Dead refs must not be present
# ===================================================================


class TestSecurityModelRefsHappy:
    """SECURITY_MODEL.md module references must point to existing files."""

    def test_artifact_integrity_ref_exists(self) -> None:
        """artifact_integrity.py reference must exist."""
        content = _read("docs/SECURITY_MODEL.md")
        assert "governance/infrastructure/artifact_integrity.py" in content
        path = REPO_ROOT / "governance" / "infrastructure" / "artifact_integrity.py"
        assert path.exists()


class TestSecurityModelRefsBad:
    """Detect dead module references in SECURITY_MODEL.md."""

    _DEAD_MODULES = [
        "governance/domain/trust_levels.py",
        "governance/infrastructure/input_validation.py",
    ]

    @pytest.mark.parametrize("dead_ref", _DEAD_MODULES)
    def test_dead_module_ref_removed(self, dead_ref: str) -> None:
        """Previously dead module references must be removed."""
        content = _read("docs/SECURITY_MODEL.md")
        assert dead_ref not in content, (
            f"docs/SECURITY_MODEL.md still references dead module: {dead_ref}"
        )

    @pytest.mark.parametrize("dead_ref", _DEAD_MODULES)
    def test_dead_module_does_not_exist(self, dead_ref: str) -> None:
        """Confirm the modules are actually dead (don't exist on disk)."""
        path = REPO_ROOT / dead_ref
        assert not path.exists(), (
            f"Module was expected to be dead but exists: {dead_ref} — "
            "if it was re-created, add it back to SECURITY_MODEL.md"
        )


class TestSecurityModelRefsEdge:
    """Edge: the References section must still exist and be non-empty."""

    def test_references_section_exists(self) -> None:
        """SECURITY_MODEL.md must have a References section."""
        content = _read("docs/SECURITY_MODEL.md")
        assert "## References" in content

    def test_references_have_at_least_two_entries(self) -> None:
        """References section must have at least 2 entries after dead ref removal."""
        content = _read("docs/SECURITY_MODEL.md")
        ref_start = content.index("## References")
        # Find next section or end
        next_section = content.find("\n## ", ref_start + 1)
        if next_section < 0:
            next_section = len(content)
        section = content[ref_start:next_section]
        entries = [l for l in section.split("\n") if l.strip().startswith("- ")]
        assert len(entries) >= 2, (
            f"SECURITY_MODEL.md References must have at least 2 entries, "
            f"found {len(entries)}: {entries}"
        )


class TestSecurityModelRefsCorner:
    """Corner: all remaining refs in SECURITY_MODEL.md References must resolve."""

    def test_all_refs_resolve_to_existing_files(self) -> None:
        """Every file path in the References section must exist on disk."""
        content = _read("docs/SECURITY_MODEL.md")
        ref_start = content.index("## References")
        next_section = content.find("\n## ", ref_start + 1)
        if next_section < 0:
            next_section = len(content)
        section = content[ref_start:next_section]
        # Extract backtick-quoted paths
        paths = re.findall(r"`([^`]+\.(?:py|md|json))`", section)
        for ref_path in paths:
            assert _exists_repo_path(ref_path), (
                f"docs/SECURITY_MODEL.md References contains dead path: {ref_path}"
            )


# ===================================================================
# 6. Cross-file /review framing consistency (combined invariant)
#    Tests that ALL files mentioning /review are consistent
# ===================================================================


class TestCrossFileReviewConsistency:
    """Cross-file invariant: /review framing must be consistent everywhere."""

    # Forbidden patterns in any file that mentions /review
    _FORBIDDEN_PATTERNS = [
        "review-only rail",
        "Phase 4 review-only",
        "review-only command",
    ]

    def _all_md_mentioning_review(self) -> list[tuple[str, str]]:
        """Return (relpath, content) for all MD files mentioning /review."""
        results = []
        for p in REPO_ROOT.rglob("*.md"):
            if any(
                part.startswith((".", "_archive", "node_modules", ".git"))
                for part in p.relative_to(REPO_ROOT).parts
            ):
                continue
            content = p.read_text(encoding="utf-8")
            if "/review" in content:
                results.append(
                    (str(p.relative_to(REPO_ROOT).as_posix()), content)
                )
        return results

    def test_no_forbidden_framing_in_any_review_file(self) -> None:
        """No file mentioning /review may use any forbidden framing pattern."""
        violations = []
        for relpath, content in self._all_md_mentioning_review():
            content_lower = content.lower()
            for pattern in self._FORBIDDEN_PATTERNS:
                if pattern.lower() in content_lower:
                    violations.append(f"{relpath}: contains '{pattern}'")
        assert not violations, (
            "Cross-file /review framing violations:\n" +
            "\n".join(f"  - {v}" for v in violations)
        )


# ===========================================================================
# P2 structural cleanup guard tests
# ===========================================================================


class TestP2AuditMdBindingLabel:
    """Guard: audit.md must not use bare 'binding' labels."""

    AUDIT_PATH = "governance/assets/catalogs/audit.md"

    def _audit_content(self) -> str:
        return _read(self.AUDIT_PATH)

    # -- Happy --
    def test_normative_label_present_reason_key(self) -> None:
        content = self._audit_content()
        assert "Reason key semantics (normative for audit scope):" in content

    def test_normative_label_present_deterministic_bridge(self) -> None:
        content = self._audit_content()
        assert "Deterministic bridge (normative for audit scope):" in content

    def test_normative_label_present_abuse_resistance(self) -> None:
        content = self._audit_content()
        assert "Normative for audit scope; Read-Only Diagnostics" in content

    # -- Bad --
    def test_no_bare_binding_parenthetical(self) -> None:
        """'(binding)' or '(Binding)' must not appear."""
        content = self._audit_content().lower()
        assert "(binding)" not in content, (
            "audit.md still contains bare '(binding)' label"
        )

    def test_no_binding_semicolon_label(self) -> None:
        """'Binding;' must not appear as a section label."""
        content = self._audit_content()
        assert "Binding;" not in content

    # -- Edge --
    def test_binding_word_in_prose_allowed(self) -> None:
        """The word 'binding' may still appear in prose (e.g. 'non-binding')."""
        # This is an edge case: we only forbid the parenthetical label usage.
        content = self._audit_content()
        # The word "binding" in "non-binding" or prose is acceptable
        # We just confirm the file is parseable and our label check works
        assert "normative for audit scope" in content.lower()

    # -- Corner --
    def test_audit_md_still_read_only_command(self) -> None:
        """audit.md must retain Read-Only semantics."""
        content = self._audit_content()
        assert "Read-Only" in content


class TestP2GovernanceSchemasCleanup:
    """Guard: governance_schemas.md Draft label removed; path corrected."""

    SCHEMAS_PATH = "docs/governance/governance_schemas.md"

    def _content(self) -> str:
        return _read(self.SCHEMAS_PATH)

    # -- Happy --
    def test_heading_has_no_draft_label(self) -> None:
        content = self._content()
        first_line = content.split("\n")[0]
        assert first_line.strip() == "# Governance Schemas"

    def test_response_envelope_path_corrected(self) -> None:
        content = self._content()
        assert "governance/assets/catalogs/RESPONSE_ENVELOPE_SCHEMA.json" in content

    # -- Bad --
    def test_no_draft_in_heading(self) -> None:
        content = self._content()
        first_line = content.split("\n")[0]
        assert "(Draft)" not in first_line

    def test_no_stale_root_path(self) -> None:
        """Must not reference the old root-level path."""
        content = self._content()
        # Check that `governance/assets/catalogs/RESPONSE_ENVELOPE_SCHEMA.json` without
        # `assets/catalogs/` prefix does NOT appear.
        lines = content.split("\n")
        for line in lines:
            if "RESPONSE_ENVELOPE_SCHEMA.json" in line:
                assert "assets/catalogs/" in line, (
                    f"Stale path found: {line.strip()}"
                )

    # -- Edge --
    def test_schema_version_labels_preserved(self) -> None:
        content = self._content()
        assert "governance.schemas.v1" in content

    # -- Corner --
    def test_file_not_empty(self) -> None:
        content = self._content()
        assert len(content.strip()) > 50


class TestP2CustomerInstallBundleStructure:
    """Guard: customer-install-bundle-v1.md has H1 and no truncated sections."""

    BUNDLE_PATH = "docs/customer-install-bundle-v1.md"

    def _content(self) -> str:
        return _read(self.BUNDLE_PATH)

    # -- Happy --
    def test_has_h1_heading(self) -> None:
        content = self._content()
        assert content.startswith("# Customer Install Bundle")

    def test_github_release_section_not_empty(self) -> None:
        content = self._content()
        idx = content.find("## GitHub release pipeline")
        assert idx != -1, "Missing '## GitHub release pipeline' section"
        after = content[idx + len("## GitHub release pipeline"):].strip()
        assert len(after) > 5, "GitHub release pipeline section is empty/truncated"

    # -- Bad --
    def test_no_headingless_start(self) -> None:
        content = self._content()
        assert content.strip()[0] == "#", "File must start with a heading"

    # -- Edge --
    def test_install_sh_section_present(self) -> None:
        content = self._content()
        assert "install/install.sh" in content

    def test_install_ps1_section_present(self) -> None:
        content = self._content()
        assert "install/install.ps1" in content

    # -- Corner --
    def test_ci_release_path_section_present(self) -> None:
        content = self._content()
        assert "## CI release path" in content


class TestP2TicketPhase6Precision:
    """Guard: ticket.md specifies Phase 6 transition."""

    TICKET_PATH = "ticket.md"

    def _content(self) -> str:
        return _read(self.TICKET_PATH)

    # -- Happy --
    def test_phase_6_transition_mentioned(self) -> None:
        content = self._content()
        assert "Phase 6" in content, (
            "ticket.md must reference Phase 6 (implementation gate)"
        )

    # -- Bad --
    def test_no_ambiguous_approved_only(self) -> None:
        """Must not say 'gates are approved' without mentioning Phase 6."""
        content = self._content()
        for line in content.split("\n"):
            if "gates are approved" in line:
                assert "Phase 6" in line, (
                    f"Line mentions gate approval without Phase 6 target: {line.strip()}"
                )

    # -- Edge --
    def test_continue_review_rail_statement_preserved(self) -> None:
        content = self._content()
        # R2 compressed this into Interpretation scope; the key semantic is
        # that ticket.md clarifies text alone doesn't change phase.
        assert "do not change phase" in content.lower() or \
               "does not change phase" in content.lower() or \
               "do not change phase by themselves" in content.lower(), (
            "ticket.md must clarify that text alone does not change phase"
        )

    # -- Corner --
    def test_intake_reroute_disclaimer_preserved(self) -> None:
        content = self._content()
        assert "Intake reroute is not implementation approval" in content


class TestP2StaleFileDeletions:
    """Guard: stale files must not reappear after deletion."""

    _DELETED_FILES = [
        "docs/governance/MASTER_SECTION_CLASSIFICATION.md",
        "docs/governance-customer-scripts.md",
        "ARCHITECTURE_MIGRATION_STATUS.md",
        "docs/governance/RAILS_REFACTOR_MAPPING.md",
    ]

    _MOVED_TO_ARCHIVE = [
        (
            "docs/MD_VIOLATION_ANALYSIS.md",
            "governance_content/docs/_archive/MD_VIOLATION_ANALYSIS.md",
        ),
    ]

    # -- Happy --
    @pytest.mark.parametrize("relpath", _DELETED_FILES)
    def test_deleted_file_does_not_exist(self, relpath: str) -> None:
        p = REPO_ROOT / relpath
        assert not p.exists(), f"Stale file should have been deleted: {relpath}"

    @pytest.mark.parametrize("old,new", _MOVED_TO_ARCHIVE)
    def test_archived_file_moved(self, old: str, new: str) -> None:
        assert not (REPO_ROOT / old).exists(), f"Original should not exist: {old}"
        assert (REPO_ROOT / new).exists(), f"Archive copy missing: {new}"

    # -- Bad --
    def test_readme_rules_no_rails_refactor_ref(self) -> None:
        """README-RULES.md must not reference deleted RAILS_REFACTOR_MAPPING.md."""
        content = _read("README-RULES.md")
        assert "RAILS_REFACTOR_MAPPING" not in content

    def test_lint_md_python_uses_archive_path(self) -> None:
        """lint_md_python.py must reference the archived path."""
        content = _read("scripts/lint_md_python.py")
        assert "docs/_archive/MD_VIOLATION_ANALYSIS.md" in content
        assert '"docs/MD_VIOLATION_ANALYSIS.md"' not in content

    def test_fix_md_authority_uses_archive_path(self) -> None:
        """fix_md_authority_language.py must reference the archived path."""
        content = _read("scripts/fix_md_authority_language.py")
        assert "docs/_archive/MD_VIOLATION_ANALYSIS.md" in content
        assert '"docs/MD_VIOLATION_ANALYSIS.md"' not in content

    # -- Edge --
    def test_archive_directory_exists(self) -> None:
        assert (DOCS / "_archive").is_dir()

    # -- Corner --
    def test_no_dangling_refs_to_master_section_classification(self) -> None:
        """No non-archived MD file should reference the deleted file."""
        for p in REPO_ROOT.rglob("*.md"):
            if "_archive" in str(p):
                continue
            content = p.read_text(encoding="utf-8", errors="replace")
            assert "MASTER_SECTION_CLASSIFICATION.md" not in content, (
                f"Dangling reference in {p.relative_to(REPO_ROOT)}"
            )


# ===================================================================
# 8. Archive move guard: active rails live in docs/, not docs/_archive/
#
#    resume.md, resume_prompt.md, new_profile.md, new_addon.md were
#    moved from docs/_archive/ to docs/ because they are actively
#    referenced by install.py, governance_lint.py, tests, and runtime
#    catalogs.  These guards prevent regression.
# ===================================================================

_ACTIVE_RAILS_MOVED_FROM_ARCHIVE = [
    "resume.md",
    "resume_prompt.md",
    "new_profile.md",
    "new_addon.md",
]

# Source files (Python, JSON) that should reference docs/<file> NOT docs/_archive/<file>
# Excludes: CHANGELOG.md (historical refs are fine), archived files themselves, __pycache__
_SOURCE_GLOBS = ["**/*.py", "**/*.json"]

# Files where archive paths for the 4 moved files are NEVER legitimate
# (we scan all .py and .json files)


class TestArchiveMoveHappy:
    """The 4 active rails must exist at docs/ after the move."""

    @pytest.mark.parametrize("filename", _ACTIVE_RAILS_MOVED_FROM_ARCHIVE)
    def test_active_rail_exists_at_docs(self, filename: str) -> None:
        target = DOCS / filename
        assert target.exists(), f"Active rail missing at docs/{filename}"
        assert target.stat().st_size > 0, f"docs/{filename} is empty"

    @pytest.mark.parametrize("filename", _ACTIVE_RAILS_MOVED_FROM_ARCHIVE)
    def test_active_rail_is_readable_markdown(self, filename: str) -> None:
        """Each moved file must be valid UTF-8 with meaningful content."""
        content = (DOCS / filename).read_text(encoding="utf-8")
        # Must have substantive content (at least 50 chars)
        assert len(content.strip()) >= 50, (
            f"docs/{filename} has insufficient content ({len(content.strip())} chars)"
        )


class TestArchiveMoveBad:
    """The 4 active rails must NOT still exist at docs/_archive/."""

    @pytest.mark.parametrize("filename", _ACTIVE_RAILS_MOVED_FROM_ARCHIVE)
    def test_active_rail_not_in_archive(self, filename: str) -> None:
        stale = DOCS / "_archive" / filename
        assert not stale.exists(), (
            f"Stale copy still at docs/_archive/{filename} — should have been moved to docs/"
        )


class TestArchiveMoveEdge:
    """No source file should reference docs/_archive/ paths for the moved files."""

    @pytest.mark.parametrize("filename", _ACTIVE_RAILS_MOVED_FROM_ARCHIVE)
    def test_no_stale_archive_refs_in_source(self, filename: str) -> None:
        """Python and JSON source files must not reference the old archive path."""
        stale_patterns = [
            f"docs/_archive/{filename}",
            f"governance_content/docs/_archive/{filename}",
        ]
        violations: list[str] = []
        for glob_pat in _SOURCE_GLOBS:
            for p in REPO_ROOT.rglob(glob_pat):
                # Skip __pycache__, .git, node_modules
                rel = str(p.relative_to(REPO_ROOT))
                if any(skip in rel for skip in ("__pycache__", ".git", "node_modules")):
                    continue
                try:
                    content = p.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                if any(stale_pattern in content for stale_pattern in stale_patterns):
                    violations.append(rel)
        assert not violations, (
            f"Stale archive refs for '{filename}' found in: {violations}"
        )

    def test_customer_exclude_has_no_moved_files(self) -> None:
        """CUSTOMER_MARKDOWN_EXCLUDE.json must not list the moved files."""
        content = _read("governance/assets/catalogs/CUSTOMER_MARKDOWN_EXCLUDE.json")
        for filename in _ACTIVE_RAILS_MOVED_FROM_ARCHIVE:
            assert f"_archive/{filename}" not in content, (
                f"CUSTOMER_MARKDOWN_EXCLUDE.json still lists archived path for {filename}"
            )
            # They shouldn't be excluded at all — they're active
            assert f"docs/{filename}" not in content, (
                f"CUSTOMER_MARKDOWN_EXCLUDE.json should not exclude active rail docs/{filename}"
            )


class TestArchiveMoveCorner:
    """Corner-case guards for the archive move."""

    def test_install_py_references_docs_path(self) -> None:
        """install.py must use docs-based collection logic for active rails."""
        content = _read("install.py")
        assert "docs/" in content
        assert "governance_content/docs/" in content

    def test_governance_lint_references_docs_path(self) -> None:
        """governance_lint.py must reference docs/<file> for all 4 moved files."""
        content = _read("scripts/governance_lint.py")
        for filename in _ACTIVE_RAILS_MOVED_FROM_ARCHIVE:
            # Accepts both string literal and Path construction forms
            has_string_ref = f"docs/{filename}" in content
            has_path_ref = f'"docs" / "{filename}"' in content
            has_docs_root_ref = f'docs_root() / "{filename}"' in content
            assert has_string_ref or has_path_ref or has_docs_root_ref, (
                f"governance_lint.py missing reference to docs/{filename}"
            )

    def test_reason_remediation_map_uses_docs_path(self) -> None:
        """REASON_REMEDIATION_MAP.json must not use _archive paths for moved files."""
        content = _read("governance/assets/catalogs/REASON_REMEDIATION_MAP.json")
        for filename in _ACTIVE_RAILS_MOVED_FROM_ARCHIVE:
            assert f"_archive/{filename}" not in content, (
                f"REASON_REMEDIATION_MAP.json uses stale archive path for {filename}"
            )

    def test_archive_directory_still_has_other_files(self) -> None:
        """docs/_archive/ should still exist with other legitimately archived files."""
        archive = DOCS / "_archive"
        assert archive.is_dir(), "docs/_archive/ directory should still exist"
        remaining = list(archive.glob("*.md"))
        assert len(remaining) > 0, "docs/_archive/ should still contain archived files"
        # None of the moved files should be among them
        remaining_names = {p.name for p in remaining}
        for filename in _ACTIVE_RAILS_MOVED_FROM_ARCHIVE:
            assert filename not in remaining_names
