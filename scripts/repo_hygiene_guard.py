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

ARCHIVE_BASELINE: set[str] = set()

README_BASELINE = {
    "README-OPENCODE.md",
    "README-RULES.md",
}

INIT_MARKER_BASELINE = {
    "governance_runtime/entrypoints/__init__.py",
    "tests/__init__.py",
    "tests/conformance/__init__.py",
}

PSEUDO_EMPTY_DIR_BASELINE: set[str] = set()

MARKER_FILE_NAMES = {
    "__init__.py",
    ".gitkeep",
    ".keep",
    ".DS_Store",
}

ARCHIVE_REFERENCE_PATTERNS = (
    "governance_content/docs/archived/",
    "governance_spec/migrations/archived/",
    "historical/governance_content_docs/",
    "historical/governance_spec_migrations/",
)

DUPLICATE_BASELINE_GROUPS: set[frozenset[str]] = set()

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


def _scan_archive_references(repo_root: Path) -> list[str]:
    offenders: list[str] = []
    # Narrow exception policy: only cleanup/inventory records may reference
    # historical archive paths as evidence breadcrumbs.
    allowed_reference_files = {
        "scripts/repo_hygiene_guard.py",
        "governance_spec/migrations/REPO_CLEANUP_POLICY.md",
        "governance_spec/migrations/CLEANUP_DECISION_LOG.md",
        "governance_content/docs/repo-hygiene-block9-inventory.md",
    }
    for root_name in PRODUCTIVE_ROOTS:
        root = repo_root / root_name
        if not root.exists() or not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".md", ".py", ".yml", ".yaml", ".json"}:
                continue
            rel = path.relative_to(repo_root).as_posix()
            if rel in allowed_reference_files:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for pattern in ARCHIVE_REFERENCE_PATTERNS:
                if pattern in text:
                    offenders.append(f"{rel} -> {pattern}")
    return sorted(offenders)


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


def _is_pseudo_empty_dir(path: Path) -> bool:
    if not path.exists() or not path.is_dir():
        return False
    files = [entry for entry in path.rglob("*") if entry.is_file()]
    if not files:
        return True
    for file_path in files:
        if file_path.name in MARKER_FILE_NAMES:
            continue
        return False
    return True


def _scan_pseudo_empty_dirs(repo_root: Path) -> set[str]:
    found: set[str] = set()
    opencode_root = repo_root / "opencode"
    if not opencode_root.exists() or not opencode_root.is_dir():
        return found
    for path in opencode_root.rglob("*"):
        if not path.is_dir():
            continue
        rel = path.relative_to(repo_root).as_posix()
        if _is_pseudo_empty_dir(path):
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

    archive_refs = _scan_archive_references(repo_root)
    for offender in archive_refs:
        issues.append(f"archive reference violation: {offender}")

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

    pseudo_empty_dirs = _scan_pseudo_empty_dirs(repo_root)
    unknown_pseudo_empty_dirs = sorted(pseudo_empty_dirs - PSEUDO_EMPTY_DIR_BASELINE)
    missing_pseudo_empty_dirs = sorted(PSEUDO_EMPTY_DIR_BASELINE - pseudo_empty_dirs)
    if unknown_pseudo_empty_dirs:
        for rel in unknown_pseudo_empty_dirs:
            issues.append(f"pseudo-empty dir violation: unexpected marker-only directory {rel}")
    if missing_pseudo_empty_dirs:
        for rel in missing_pseudo_empty_dirs:
            issues.append(f"pseudo-empty baseline changed (update after cleanup): {rel}")

    if issues:
        print("❌ Repo hygiene guard failed")
        for item in issues:
            print(f" - {item}")
        return 1

    print("✅ Repo hygiene guard passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
