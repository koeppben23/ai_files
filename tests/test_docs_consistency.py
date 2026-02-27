from __future__ import annotations

from pathlib import Path
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
    root = Path(__file__).resolve().parents[1]
    violations: list[str] = []
    for rel in DOC_FILES:
        text = (root / rel).read_text(encoding="utf-8")
        for pattern in FORBIDDEN_PATTERNS:
            if pattern.search(text):
                violations.append(f"{rel}: {pattern.pattern}")
    assert not violations, f"forbidden doc phrases found: {violations}"


def test_docs_ssot_clarification_present() -> None:
    root = Path(__file__).resolve().parents[1]
    for rel in REQUIRED_PHRASE_DOCS:
        text = (root / rel).read_text(encoding="utf-8")
        for phrase in REQUIRED_PHRASES:
            assert phrase in text, f"missing required SSOT phrase in {rel}: {phrase}"


def test_docs_do_not_claim_markdown_runtime_authority() -> None:
    root = Path(__file__).resolve().parents[1]
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
