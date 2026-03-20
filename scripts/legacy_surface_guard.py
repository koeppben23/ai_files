#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


DEFAULT_ALLOWED_PREFIXES = (
    "docs/archive/",
    "migration_notes/",
    "tests/fixtures/legacy_examples/",
    "governance_content/docs/archived/",
    "governance_spec/migrations/",
    "scripts/legacy_surface_guard.py",
    "scripts/install_layout_gate.py",
    "scripts/delete_barrier_gate.py",
)

SCANNED_EXTENSIONS = {
    ".py",
    ".md",
    ".yml",
    ".yaml",
    ".json",
    ".txt",
    ".jinja",
    ".j2",
    ".template",
}

PYTHON_PRODUCTIVE_ROOTS = ("cli", "bootstrap", "governance_runtime", "governance", "scripts")
PATH_SCAN_ROOTS = (
    "governance_content",
    "governance_spec",
    "templates",
    "opencode/commands",
    ".github/workflows",
)
EXPLICIT_NORMATIVE_FILES = ("README.md", "QUICKSTART.md")
EXPLICIT_PRODUCTIVE_PYTHON_FILES = ("install.py",)

SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "dist",
    "build",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
}

IMPORT_PATTERN = re.compile(r"\b(from|import)\s+governance(\.|\b)")
MODULE_RUN_PATTERN = re.compile(r"python\s+-m\s+governance\.")
PATH_PATTERNS = (
    "governance/",
    "governance.",
    "governance/assets",
    "governance/kernel",
    "governance/entrypoints",
    "governance/VERSION",
)

ALLOW_WRITE_TEXT = ("governance/infrastructure/fs_atomic.py",)
RESTRICTED_ENV_PARTS = {
    ("governance", "application"),
    ("governance", "domain"),
    ("governance", "presentation"),
    ("governance", "render"),
}
REPO_IDENTITY_PATH = "governance/application/repo_identity_service.py"


def _to_posix(path: Path) -> str:
    return path.as_posix()


def _is_allowed(rel_posix: str, allowed_prefixes: tuple[str, ...]) -> bool:
    return any(rel_posix.startswith(prefix) for prefix in allowed_prefixes)


def _iter_candidate_files(repo_root: Path) -> list[Path]:
    files: list[Path] = []
    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in SCANNED_EXTENSIONS:
            continue
        files.append(path)
    return files


def _in_roots(rel_posix: str, roots: tuple[str, ...]) -> bool:
    return any(rel_posix == root or rel_posix.startswith(root + "/") for root in roots)


def scan_legacy_surface(repo_root: Path, *, allowed_prefixes: tuple[str, ...]) -> list[str]:
    violations: list[str] = []
    for path in _iter_candidate_files(repo_root):
        rel = path.relative_to(repo_root)
        rel_posix = _to_posix(rel)
        if _is_allowed(rel_posix, allowed_prefixes):
            continue

        scan_python = path.suffix.lower() == ".py" and (
            _in_roots(rel_posix, PYTHON_PRODUCTIVE_ROOTS) or rel_posix in EXPLICIT_PRODUCTIVE_PYTHON_FILES
        )
        scan_path_tokens = _in_roots(rel_posix, PATH_SCAN_ROOTS) or rel_posix in EXPLICIT_NORMATIVE_FILES
        if not scan_python and not scan_path_tokens:
            continue

        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()

        for idx, line in enumerate(lines, start=1):
            if scan_python:
                if IMPORT_PATTERN.search(line):
                    violations.append(f"{rel_posix}:{idx}: forbidden governance import")
                if MODULE_RUN_PATTERN.search(line):
                    violations.append(f"{rel_posix}:{idx}: forbidden python -m governance.* invocation")

            if scan_path_tokens or scan_python:
                for token in PATH_PATTERNS:
                    if token in line:
                        violations.append(f"{rel_posix}:{idx}: forbidden legacy path token '{token}'")

            if scan_python and ".write_text(" in line and "tmp.write_text(" not in line:
                if rel_posix not in ALLOW_WRITE_TEXT:
                    violations.append(f"{rel_posix}:{idx}: disallowed write_text usage")

        if scan_python:
            if "render_command_profiles(shlex.split(" in text:
                violations.append(f"{rel_posix}: disallowed render_command_profiles(shlex.split(...))")
            if "subprocess.run([sys.executable" in text:
                violations.append(f"{rel_posix}: disallowed subprocess.run([sys.executable, ...])")

        rel_parts = rel.parts
        if len(rel_parts) >= 2 and (rel_parts[0], rel_parts[1]) in RESTRICTED_ENV_PARTS:
            if "os.environ" in text or "os.getenv(" in text:
                violations.append(f"{rel_posix}: disallowed direct env access outside infrastructure")

    repo_identity = repo_root / REPO_IDENTITY_PATH
    if repo_identity.exists():
        text = repo_identity.read_text(encoding="utf-8", errors="replace")
        for idx, line in enumerate(text.splitlines(), start=1):
            if ".resolve(" in line and "gitdir" not in line.lower():
                violations.append(f"{REPO_IDENTITY_PATH}:{idx}: resolve() not allowed in repo identity flow")
    return violations


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fail on forbidden legacy governance references.")
    parser.add_argument("--repo-root", default=".", help="Repository root to scan")
    parser.add_argument(
        "--allow-prefix",
        action="append",
        default=[],
        help="Additional allowed path prefix (repo-relative, posix style)",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).resolve()
    allowed_prefixes = tuple(DEFAULT_ALLOWED_PREFIXES) + tuple(str(x) for x in args.allow_prefix)
    violations = scan_legacy_surface(repo_root, allowed_prefixes=allowed_prefixes)
    if violations:
        print("❌ Legacy surface guard failed")
        for item in violations:
            print(f" - {item}")
        return 1
    print("✅ Legacy surface guard passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
