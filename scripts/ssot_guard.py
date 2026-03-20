from __future__ import annotations

import json
import hashlib
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _docs_root() -> Path:
    return REPO_ROOT / "governance_content" / "docs"


def _catalog_path() -> Path:
    return REPO_ROOT / "governance_content" / "governance" / "assets" / "catalogs" / "SSOT_GUARD_RULES.json"


CATALOG_PATH = _catalog_path()
MATRIX_PATH = _docs_root() / "governance" / "kernel_vs_docs_matrix.csv"
FIELD_OWNERSHIP_PATH = _docs_root() / "governance" / "canonical_field_ownership.md"

ALLOWED_ARCHIVE_PREFIXES = (
    "docs/archive/",
    "migration_notes/",
    "governance_spec/migrations/",
    "tests/fixtures/legacy_examples/",
    "governance_content/docs/archived/",
)

CANONICAL_DOCS = {
    "master.md": "governance_content/reference/master.md",
    "rules.md": "governance_content/reference/rules.md",
    "README.md": "README.md",
    "QUICKSTART.md": "QUICKSTART.md",
}

NORMATIVE_SCAN_ROOTS = (
    "governance_content",
    "governance_spec",
    "templates",
    "opencode",
    ".github",
)

NORMATIVE_EXTENSIONS = {".md", ".yml", ".yaml", ".json"}


def _map_legacy_relpath(rel: str) -> str:
    if rel == "master.md":
        return "governance_content/reference/master.md"
    if rel == "rules.md":
        return "governance_content/reference/rules.md"
    if rel == "phase_api.yaml":
        return "governance_spec/phase_api.yaml"
    if rel.startswith("docs/"):
        return "governance_content/" + rel
    if rel.startswith("profiles/"):
        return "governance_content/" + rel
    if rel.startswith("templates/"):
        return "governance_content/" + rel
    if rel.startswith("rulesets/"):
        return "governance_spec/" + rel
    if rel.startswith("governance/docs/"):
        return "governance_content/docs/governance/" + rel.removeprefix("governance/docs/")
    if rel.startswith("governance/"):
        return "governance_runtime/" + rel.removeprefix("governance/")
    return rel


def _fail(message: str) -> int:
    print(message, file=sys.stderr)
    return 1


def _load_catalog() -> dict[str, object]:
    if not CATALOG_PATH.exists():
        raise SystemExit(f"Missing SSOT guard catalog: {CATALOG_PATH}")
    payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    if payload.get("schema") != "governance.ssot-guard-rules.v1":
        raise SystemExit("SSOT guard catalog schema mismatch")
    return payload


def _load_kernel_matrix() -> list[list[str]]:
    if not MATRIX_PATH.exists():
        raise SystemExit(f"Missing kernel/doc matrix: {MATRIX_PATH}")
    rows = []
    for raw in MATRIX_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        rows.append([col.strip() for col in line.split(",")])
    return rows


def _validate_guard_sources(issues: list[str], guards: list[dict[str, object]]) -> None:
    for guard in guards:
        source = guard.get("source")
        if not isinstance(source, str) or not source.strip():
            issues.append("SSOT guard missing source")
            continue
        src_path = REPO_ROOT / _map_legacy_relpath(source)
        if not src_path.exists():
            issues.append(f"SSOT guard source missing: {source}")


def _validate_guard_references(issues: list[str], guards: list[dict[str, object]]) -> None:
    for guard in guards:
        refs = guard.get("md_references")
        if not isinstance(refs, list) or not refs:
            issues.append(f"SSOT guard missing md_references: {guard.get('id')}")
            continue
        for entry in refs:
            if not isinstance(entry, str) or not entry.strip():
                issues.append(f"SSOT guard invalid md_references entry: {guard.get('id')}")
                continue
            if not (REPO_ROOT / _map_legacy_relpath(entry)).exists():
                issues.append(f"SSOT guard reference missing: {entry}")


def _validate_matrix_alignment(issues: list[str], guards: list[dict[str, object]], matrix_rows: list[list[str]]) -> None:
    matrix_sources = set()
    for row in matrix_rows[1:] if matrix_rows and matrix_rows[0][0] == "ssot_source" else matrix_rows:
        if row:
            matrix_sources.add(_map_legacy_relpath(row[0]))

    guard_sources = {
        _map_legacy_relpath(source)
        for guard in guards
        for source in [guard.get("source")]
        if isinstance(source, str)
    }
    missing_in_matrix = sorted(source for source in guard_sources if source not in matrix_sources)
    if missing_in_matrix:
        issues.append("SSOT guard sources missing from kernel_vs_docs_matrix.csv: " + ", ".join(missing_in_matrix))


def _validate_field_ownership_exists(issues: list[str]) -> None:
    if not FIELD_OWNERSHIP_PATH.exists():
        issues.append("canonical_field_ownership.md missing")


def _is_allowed_archive(rel_posix: str) -> bool:
    return any(rel_posix.startswith(prefix) for prefix in ALLOWED_ARCHIVE_PREFIXES)


def _iter_normative_files() -> list[Path]:
    files: list[Path] = []
    for root_name in NORMATIVE_SCAN_ROOTS:
        root = REPO_ROOT / root_name
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in NORMATIVE_EXTENSIONS:
                files.append(path)
    for name in ("README.md", "QUICKSTART.md"):
        path = REPO_ROOT / name
        if path.exists():
            files.append(path)
    return files


def _validate_canonical_uniqueness(issues: list[str]) -> None:
    files = _iter_normative_files()
    by_name: dict[str, list[Path]] = {}
    for path in files:
        by_name.setdefault(path.name, []).append(path)

    for name, canonical_rel in CANONICAL_DOCS.items():
        canonical_path = REPO_ROOT / canonical_rel
        matches = by_name.get(name, [])
        if not canonical_path.exists():
            issues.append(f"canonical missing: {canonical_rel}")
            continue
        for path in matches:
            rel_posix = path.relative_to(REPO_ROOT).as_posix()
            if rel_posix == canonical_rel:
                continue
            if _is_allowed_archive(rel_posix):
                continue
            issues.append(
                f"non-canonical normative duplicate for {name}: {rel_posix} (canonical: {canonical_rel})"
            )


def _validate_byte_identical_duplicates(issues: list[str]) -> None:
    files = _iter_normative_files()
    digest_map: dict[str, list[str]] = {}
    for path in files:
        rel_posix = path.relative_to(REPO_ROOT).as_posix()
        if _is_allowed_archive(rel_posix):
            continue
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        digest_map.setdefault(digest, []).append(rel_posix)

    for paths in digest_map.values():
        if len(paths) <= 1:
            continue
        sorted_paths = sorted(paths)
        issues.append("byte-identical normative duplicates: " + ", ".join(sorted_paths))


def main() -> int:
    issues: list[str] = []
    payload = _load_catalog()
    guards = payload.get("guards")
    if not isinstance(guards, list) or not guards:
        return _fail("SSOT guard catalog guards must be a non-empty array")

    _validate_guard_sources(issues, guards)
    _validate_guard_references(issues, guards)
    _validate_field_ownership_exists(issues)
    _validate_canonical_uniqueness(issues)
    _validate_byte_identical_duplicates(issues)

    matrix_rows = _load_kernel_matrix()
    if not matrix_rows:
        issues.append("kernel_vs_docs_matrix.csv empty")
    _validate_matrix_alignment(issues, guards, matrix_rows)

    if issues:
        for issue in issues:
            print(f"SSOT-GUARD: {issue}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
