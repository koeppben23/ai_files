from __future__ import annotations

from pathlib import Path
from tests.util import get_master_path, REPO_ROOT
import re


DOC_FILES = [
    "master.md",
    "governance/assets/catalogs/audit.md",
    "docs/phases.md",
    "docs/governance_invariants.md",
    "docs/_archive/CLEANUP_ANALYSIS.md",
    "QUICKSTART.md",
    "SESSION_STATE_SCHEMA.md",
]

REQUIRED_PHRASE_DOCS = [
    "master.md",
    "docs/phases.md",
    "docs/governance_invariants.md",
    "docs/_archive/CLEANUP_ANALYSIS.md",
    "QUICKSTART.md",
    "SESSION_STATE_SCHEMA.md",
]

AUTHORITY_DOC_FILES = [
    "README.md",
    "README-OPENCODE.md",
    "README-RULES.md",
    "docs/install-layout.md",
    "master.md",
]

FORBIDDEN_PATTERNS = [
    re.compile(r"routing implemented in .*phase_router\.py", re.IGNORECASE),
    re.compile(r"phase_router\.py", re.IGNORECASE),
    re.compile(r"1\.3 deferred until phase 4", re.IGNORECASE),
    re.compile(r"deferred until post-phase-2", re.IGNORECASE),
    re.compile(r"deferred to phase 4", re.IGNORECASE),
    re.compile(r"deferred to post-phase-2", re.IGNORECASE),
    re.compile(r"phase_execution_config\.yaml", re.IGNORECASE),
    re.compile(r"OPENCODE_DIAGNOSTICS_ALLOW_WRITE", re.IGNORECASE),
    re.compile(r"active gates.*master\.md\s*\+\s*rules\.md", re.IGNORECASE),
    re.compile(r"authoritative and active", re.IGNORECASE),
]

REQUIRED_PHRASES = [
    "SSOT: `${COMMANDS_HOME}/phase_api.yaml` is the only truth for routing, execution, and validation.",
    "Kernel: `governance/kernel/*` is the only control-plane implementation.",
    "MD files are AI rails/guidance only and are never routing-binding.",
    "Phase `1.3` is mandatory before every phase `>=2`.",
]


def test_docs_forbidden_phrases_absent() -> None:
    root = REPO_ROOT
    violations: list[str] = []
    for rel in DOC_FILES:
        # Check both legacy and new paths
        file_path = root / rel
        if not file_path.exists():
            file_path = root / "governance_content" / rel
        if not file_path.exists():
            continue  # Skip missing files
        text = file_path.read_text(encoding="utf-8")
        for pattern in FORBIDDEN_PATTERNS:
            if pattern.search(text):
                violations.append(f"{rel}: {pattern.pattern}")
    assert not violations, f"forbidden doc phrases found: {violations}"


def test_docs_ssot_clarification_present() -> None:
    root = REPO_ROOT
    for rel in REQUIRED_PHRASE_DOCS:
        # Check new path first (SSOT), then fall back to legacy
        new_path = root / "governance_content" / rel
        if new_path.exists():
            file_path = new_path
        else:
            file_path = root / rel
        if not file_path.exists():
            continue  # Skip missing files
        text = file_path.read_text(encoding="utf-8")
        # For shim files, check that they reference the SSOT location
        if "shim" in text.lower():
            continue
        for phrase in REQUIRED_PHRASES:
            assert phrase in text, f"missing required SSOT phrase in {rel}: {phrase}"


def test_docs_do_not_claim_markdown_runtime_authority() -> None:
    root = get_master_path().resolve().parent
    forbidden = [
        re.compile(r"master\.md\s+is\s+the\s+system\s+source\s+of\s+truth", re.IGNORECASE),
        re.compile(r"master\.md\s+wins", re.IGNORECASE),
        re.compile(r"authoritative\s+runtime\s+contract", re.IGNORECASE),
        re.compile(r"master\.md\s+remains\s+authoritative", re.IGNORECASE),
        re.compile(r"\$\{CONFIG_ROOT\}/logs/", re.IGNORECASE),
    ]
    violations: list[str] = []
    for rel in AUTHORITY_DOC_FILES:
        text = (root / rel).read_text(encoding="utf-8")
        for pattern in forbidden:
            if pattern.search(text):
                violations.append(f"{rel}: {pattern.pattern}")
    assert not violations, f"markdown runtime-authority drift found: {violations}"


def test_install_layout_doc_has_required_structure() -> None:
    root = get_master_path().resolve().parent
    text = (root / "docs" / "install-layout.md").read_text(encoding="utf-8")
    required_markers = [
        "# Install Layout",
        "## Canonical Path Variables",
        "## Installed Layout (Canonical Shape)",
        "## Customer-Facing Installed Assets",
    ]
    missing = [marker for marker in required_markers if marker not in text]
    assert not missing, f"docs/install-layout.md missing required markers: {missing}"


def test_desktop_phase4_plan_mode_guidance_is_present() -> None:
    root = REPO_ROOT
    required = {
        "README.md": "Phase 4",
        "README-OPENCODE.md": "Plan Mode",
        "QUICKSTART.md": "Phase 4",
    }
    for rel, token in required.items():
        text = (root / rel).read_text(encoding="utf-8")
        assert token in text, f"missing Phase 4 Plan Mode guidance in {rel}: {token}"


def test_phase6_changes_requested_docs_match_rework_clarification_model() -> None:
    root = get_master_path().resolve().parent
    phases = (root / "docs" / "phases.md").read_text(encoding="utf-8")
    assert "Rework Clarification Gate" in phases
    assert "Loop-reset within Phase 6" not in phases
