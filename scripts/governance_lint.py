#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


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


def parse_manifest(path: Path) -> tuple[dict[str, str], list[str], list[str]]:
    scalars: dict[str, str] = {}
    path_roots: list[str] = []
    errors: list[str] = []
    in_path_roots = False

    for line_no, raw in enumerate(read_text(path).splitlines(), start=1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue

        top = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*):\s*(.*?)\s*$", raw)
        if top:
            key, val = top.group(1), top.group(2)
            if key == "path_roots":
                in_path_roots = val == ""
                if val:
                    errors.append(f"{path}: line {line_no}: path_roots must be multiline list")
                continue
            in_path_roots = False
            scalars[key] = _unquote(val)
            continue

        if in_path_roots:
            m = re.match(r"^\s{2}-\s*(.*?)\s*$", raw)
            if not m:
                errors.append(f"{path}: line {line_no}: malformed path_roots entry")
                continue
            root = _unquote(m.group(1))
            path_roots.append(root)

    return scalars, path_roots, errors


def check_manifest_contract(issues: list[str]) -> None:
    manifests = sorted((ROOT / "profiles" / "addons").glob("*.addon.yml"))
    if not manifests:
        issues.append("profiles/addons: no addon manifests found")
        return

    for manifest in manifests:
        scalars, path_roots, errors = parse_manifest(manifest)
        issues.extend(errors)

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


def check_required_addon_references(issues: list[str]) -> None:
    manifests = sorted((ROOT / "profiles" / "addons").glob("*.addon.yml"))
    for manifest in manifests:
        scalars, _roots, _errors = parse_manifest(manifest)
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
