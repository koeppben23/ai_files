#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path


PRODUCTIVE_ROOTS = (
    "bin",
    "cli",
    "session_state",
    "governance_runtime",
    "governance_content",
    "governance_spec",
    "opencode",
)

ARCHIVE_BASELINE = {
    "governance_content/docs/archived/README.md",
    "governance_content/docs/archived/governance-layer-separation-decisions.md",
    "governance_spec/migrations/archived/README.md",
    "governance_spec/migrations/archived/R2_Import_Inventory.md",
    "governance_spec/migrations/archived/R2_Migration_Units.md",
    "governance_spec/migrations/archived/WAVE_22_MIGRATION_INVENTORY.md",
}

README_BASELINE = {
    "README-OPENCODE.md",
    "governance_content/README-OPENCODE.md",
    "README-RULES.md",
    "governance_content/README-RULES.md",
}

INIT_MARKER_BASELINE = {
    "governance_content/reference/__init__.py",
    "governance_runtime/assets/__init__.py",
    "governance_runtime/assets/catalogs/__init__.py",
    "governance_runtime/assets/config/__init__.py",
    "governance_runtime/assets/reasons/__init__.py",
    "governance_runtime/assets/schemas/__init__.py",
    "governance_runtime/bin/__init__.py",
    "governance_runtime/entrypoints/__init__.py",
    "governance_runtime/entrypoints/errors/__init__.py",
    "governance_runtime/entrypoints/io/__init__.py",
    "governance_runtime/install/__init__.py",
    "governance_runtime/scripts/__init__.py",
    "governance_runtime/session_state/__init__.py",
    "governance_spec/config/__init__.py",
    "governance_spec/contracts/__init__.py",
    "governance_spec/schemas/__init__.py",
    "opencode/__init__.py",
    "opencode/commands/__init__.py",
    "opencode/config/__init__.py",
    "opencode/plugins/__init__.py",
    "tests/__init__.py",
    "tests/conformance/__init__.py",
}

DUPLICATE_BASELINE_GROUPS = {
    frozenset({"bin/opencode-governance-bootstrap", "governance_runtime/bin/opencode-governance-bootstrap"}),
    frozenset({"bin/opencode-governance-bootstrap.cmd", "governance_runtime/bin/opencode-governance-bootstrap.cmd"}),
    frozenset({"cli/deps.py", "governance_runtime/cli/deps.py"}),
    frozenset({"session_state/schema.py", "governance_runtime/session_state/schema.py"}),
    frozenset({"session_state/serde.py", "governance_runtime/session_state/serde.py"}),
    frozenset({"session_state/transitions.py", "governance_runtime/session_state/transitions.py"}),
    frozenset({"governance_content/governance/assets/catalogs/audit.md", "governance_runtime/assets/catalogs/audit.md"}),
    frozenset({"governance_runtime/assets/config/blocked_reason_catalog.yaml", "governance_runtime/assets/reasons/blocked_reason_catalog.yaml"}),
}

SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "dist",
    "build",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
    ".mypy_cache",
    ".ruff_cache",
}


def _is_marker_init(path: Path) -> bool:
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        return True
    if text in {"__all__ = []", "__all__=[]"}:
        return True
    if text.startswith("#") and "\n" not in text:
        return True
    if text in {"\"\"\"Package marker.\"\"\"", "\"\"\"Namespace package marker.\"\"\""}:
        return True
    return False


def _iter_files(repo_root: Path) -> list[Path]:
    files: list[Path] = []
    for root_name in PRODUCTIVE_ROOTS:
        root = repo_root / root_name
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            files.append(path)
    return files


def _scan_byte_duplicates(repo_root: Path) -> set[frozenset[str]]:
    buckets: dict[tuple[int, str], list[str]] = {}
    for path in _iter_files(repo_root):
        rel = path.relative_to(repo_root).as_posix()
        if rel.endswith("/__init__.py"):
            continue
        if rel.endswith("/.gitkeep"):
            continue
        data = path.read_bytes()
        key = (len(data), hashlib.sha256(data).hexdigest())
        buckets.setdefault(key, []).append(rel)

    groups: set[frozenset[str]] = set()
    for rels in buckets.values():
        if len(rels) < 2:
            continue
        groups.add(frozenset(sorted(rels)))
    return groups


def _scan_archives(repo_root: Path) -> set[str]:
    found: set[str] = set()
    for root_name in ("governance_content", "governance_spec", "governance_runtime"):
        root = repo_root / root_name
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if "archived" in path.parts and path.is_file():
                found.add(path.relative_to(repo_root).as_posix())
    return found


def _scan_readme_duplicates(repo_root: Path) -> set[str]:
    found: set[str] = set()
    for rel in README_BASELINE:
        if (repo_root / rel).exists():
            found.add(rel)
    for path in repo_root.rglob("README-OPENCODE.md"):
        if path.is_file():
            found.add(path.relative_to(repo_root).as_posix())
    for path in repo_root.rglob("README-RULES.md"):
        if path.is_file():
            found.add(path.relative_to(repo_root).as_posix())
    return found


def _scan_marker_inits(repo_root: Path) -> set[str]:
    found: set[str] = set()
    for path in repo_root.rglob("__init__.py"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        rel = path.relative_to(repo_root).as_posix()
        if _is_marker_init(path):
            found.add(rel)
    return found


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Block 9 hygiene regression guard")
    parser.add_argument("--repo-root", default=".", help="Repository root")
    args = parser.parse_args(argv)
    repo_root = Path(args.repo_root).resolve()

    issues: list[str] = []

    duplicate_groups = _scan_byte_duplicates(repo_root)
    unknown_duplicates = sorted(group for group in duplicate_groups if group not in DUPLICATE_BASELINE_GROUPS)
    missing_baseline_duplicates = sorted(group for group in DUPLICATE_BASELINE_GROUPS if group not in duplicate_groups)
    if unknown_duplicates:
        for group in unknown_duplicates:
            issues.append("dedup unknown byte-identical group: " + ", ".join(sorted(group)))
    if missing_baseline_duplicates:
        for group in missing_baseline_duplicates:
            issues.append("dedup baseline changed (update after consolidation): " + ", ".join(sorted(group)))

    archives = _scan_archives(repo_root)
    unknown_archives = sorted(archives - ARCHIVE_BASELINE)
    missing_archive_baseline = sorted(ARCHIVE_BASELINE - archives)
    if unknown_archives:
        for rel in unknown_archives:
            issues.append(f"archive guard violation: unexpected archived file {rel}")
    if missing_archive_baseline:
        for rel in missing_archive_baseline:
            issues.append(f"archive baseline changed (update after eviction): {rel}")

    readme_files = _scan_readme_duplicates(repo_root)
    unknown_readmes = sorted(readme_files - README_BASELINE)
    missing_readmes = sorted(README_BASELINE - readme_files)
    if unknown_readmes:
        for rel in unknown_readmes:
            issues.append(f"README SSOT violation: unexpected mirror file {rel}")
    if missing_readmes:
        for rel in missing_readmes:
            issues.append(f"README baseline changed (update after SSOT consolidation): {rel}")

    marker_inits = _scan_marker_inits(repo_root)
    unknown_marker_inits = sorted(marker_inits - INIT_MARKER_BASELINE)
    missing_marker_inits = sorted(INIT_MARKER_BASELINE - marker_inits)
    if unknown_marker_inits:
        for rel in unknown_marker_inits:
            issues.append(f"init policy violation: unexpected marker __init__.py {rel}")
    if missing_marker_inits:
        for rel in missing_marker_inits:
            issues.append(f"init baseline changed (update after marker cleanup): {rel}")

    if issues:
        print("❌ Repo hygiene guard failed")
        for item in issues:
            print(f" - {item}")
        return 1

    print("✅ Repo hygiene guard passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
