#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ALLOWED_SURFACES = {
    "api_contract",
    "backend_templates",
    "bdd_framework",
    "build_tooling",
    "db_migration",
    "e2e_test_framework",
    "frontend_api_client",
    "frontend_templates",
    "governance_docs",
    "linting",
    "messaging",
    "principal_review",
    "release",
    "risk_model",
    "scorecard_calibration",
    "security",
    "static",
    "test_framework",
}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def check_master_priority_uniqueness(issues: list[str]) -> None:
    master = read_text(ROOT / "master.md")
    count = master.count("## 1. PRIORITY ORDER")
    if count != 1:
        issues.append(f"master.md: expected exactly one '## 1. PRIORITY ORDER', found {count}")


def check_anchor_presence(issues: list[str]) -> None:
    rules = read_text(ROOT / "rules.md")
    for anchor in ["RULEBOOK-PRECEDENCE-POLICY", "ADDON-CLASS-BEHAVIOR-POLICY"]:
        if anchor not in rules:
            issues.append(f"rules.md: missing required anchor '{anchor}'")


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and ((value[0] == '"' and value[-1] == '"') or (value[0] == "'" and value[-1] == "'")):
        return value[1:-1]
    return value


def parse_manifest(path: Path) -> tuple[dict[str, str], dict[str, list[str]], list[str]]:
    scalars: dict[str, str] = {}
    list_fields: dict[str, list[str]] = {"path_roots": [], "owns_surfaces": [], "touches_surfaces": []}
    errors: list[str] = []
    active_list_key: str | None = None

    for line_no, raw in enumerate(read_text(path).splitlines(), start=1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue

        top = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*):\s*(.*?)\s*$", raw)
        if top:
            key, val = top.group(1), top.group(2)
            if key in list_fields:
                active_list_key = key if val == "" else None
                if val:
                    errors.append(f"{path}: line {line_no}: {key} must be multiline list")
                continue
            active_list_key = None
            scalars[key] = _unquote(val)
            continue

        if active_list_key:
            m = re.match(r"^\s{2}-\s*(.*?)\s*$", raw)
            if not m:
                errors.append(f"{path}: line {line_no}: malformed {active_list_key} entry")
                continue
            root = _unquote(m.group(1))
            list_fields[active_list_key].append(root)

    return scalars, list_fields, errors


def _validate_relative_paths(issues: list[str], manifest: Path, path_roots: list[str]) -> None:
    if not path_roots:
        issues.append(f"{manifest}: path_roots must be non-empty")
    for root in path_roots:
        p = Path(root)
        if root == "/":
            issues.append(f"{manifest}: path_roots must not be '/'")
        if p.is_absolute():
            issues.append(f"{manifest}: path_roots must be relative, found '{root}'")
        if ".." in p.parts:
            issues.append(f"{manifest}: path_roots must not contain traversal, found '{root}'")


def _validate_surface_fields(issues: list[str], manifest: Path, list_fields: dict[str, list[str]]) -> None:
    owns = list_fields.get("owns_surfaces", [])
    touches = list_fields.get("touches_surfaces", [])
    if not owns:
        issues.append(f"{manifest}: owns_surfaces must be non-empty")
    if not touches:
        issues.append(f"{manifest}: touches_surfaces must be non-empty")

    for field_name, values in (("owns_surfaces", owns), ("touches_surfaces", touches)):
        seen = set()
        for value in values:
            if value in seen:
                issues.append(f"{manifest}: duplicate {field_name} entry '{value}'")
            seen.add(value)
            if value not in ALLOWED_SURFACES:
                issues.append(f"{manifest}: unsupported {field_name} value '{value}'")


def _validate_surface_ownership_uniqueness(
    issues: list[str], manifests_data: list[tuple[Path, dict[str, str], dict[str, list[str]]]]
) -> None:
    owners: dict[str, str] = {}
    for manifest, scalars, list_fields in manifests_data:
        addon_key = scalars.get("addon_key") or manifest.name
        for surface in list_fields.get("owns_surfaces", []):
            existing = owners.get(surface)
            if existing and existing != addon_key:
                issues.append(
                    f"{manifest}: owns_surfaces conflict on '{surface}' (also owned by addon_key={existing})"
                )
            else:
                owners[surface] = addon_key


def check_manifest_contract(issues: list[str]) -> None:
    manifests = sorted((ROOT / "profiles" / "addons").glob("*.addon.yml"))
    if not manifests:
        issues.append("profiles/addons: no addon manifests found")
        return

    manifests_data: list[tuple[Path, dict[str, str], dict[str, list[str]]]] = []
    for manifest in manifests:
        scalars, list_fields, errors = parse_manifest(manifest)
        issues.extend(errors)
        manifests_data.append((manifest, scalars, list_fields))

        mv = scalars.get("manifest_version", "")
        if mv != "1":
            issues.append(f"{manifest}: expected manifest_version=1, found '{mv or '<missing>'}'")

        rb = scalars.get("rulebook", "")
        if not rb:
            issues.append(f"{manifest}: missing rulebook")
        else:
            rb_path = ROOT / "profiles" / rb if not rb.startswith("profiles/") else ROOT / rb
            if not rb_path.exists():
                issues.append(f"{manifest}: referenced rulebook does not exist: {rb}")

        addon_class = scalars.get("addon_class", "")
        if addon_class not in {"required", "advisory"}:
            issues.append(f"{manifest}: invalid addon_class '{addon_class or '<missing>'}'")

        _validate_relative_paths(issues, manifest, list_fields.get("path_roots", []))
        _validate_surface_fields(issues, manifest, list_fields)

    _validate_surface_ownership_uniqueness(issues, manifests_data)


def check_required_addon_references(issues: list[str]) -> None:
    manifests = sorted((ROOT / "profiles" / "addons").glob("*.addon.yml"))
    for manifest in manifests:
        scalars, _list_fields, _errors = parse_manifest(manifest)
        if scalars.get("addon_class") != "required":
            continue
        rb = scalars.get("rulebook", "")
        rb_path = ROOT / "profiles" / rb if rb and not rb.startswith("profiles/") else ROOT / rb
        if not rb or not rb_path.exists():
            issues.append(f"{manifest}: required addon must reference existing rulebook")


def check_template_verified_claims_have_evidence_wording(issues: list[str]) -> None:
    templates = sorted((ROOT / "profiles").glob("rules*templates*.md"))
    for tpl in templates:
        text = read_text(tpl).lower()
        if "verified" in text and "evidence" not in text:
            issues.append(f"{tpl}: contains 'verified' claims but no 'evidence' wording")


def main() -> int:
    issues: list[str] = []
    check_master_priority_uniqueness(issues)
    check_anchor_presence(issues)
    check_manifest_contract(issues)
    check_required_addon_references(issues)
    check_template_verified_claims_have_evidence_wording(issues)

    if issues:
        print("Governance lint FAILED:")
        for issue in issues:
            print(f"- {issue}")
        return 1

    print("Governance lint OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
