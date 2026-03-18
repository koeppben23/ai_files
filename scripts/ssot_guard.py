from __future__ import annotations

import json
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
            matrix_sources.add(row[0])

    guard_sources = {
        source
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


def main() -> int:
    issues: list[str] = []
    payload = _load_catalog()
    guards = payload.get("guards")
    if not isinstance(guards, list) or not guards:
        return _fail("SSOT guard catalog guards must be a non-empty array")

    _validate_guard_sources(issues, guards)
    _validate_guard_references(issues, guards)
    _validate_field_ownership_exists(issues)

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
