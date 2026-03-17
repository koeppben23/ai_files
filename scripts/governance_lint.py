#!/usr/bin/env python3
from __future__ import annotations
import json
import sys
import yaml
from pathlib import Path


"""Lightweight governance lint stub.

This script provides a minimal, safe check that the repository contains
the canonical SSOT files under governance_spec/governance_content in
the expected locations. It is intended to be used by the installer as a
safety check during release runs, without performing expensive analyses.
"""

# Module-level ROOT variable for test monkeypatching
ROOT = Path(__file__).resolve().parents[1]


def check_yaml_rulebook_schema(issues: list[str]) -> None:
    """Check YAML rulebooks for schema compliance."""
    root = ROOT
    schema_path = root / "schemas" / "rulebook.schema.json"
    if not schema_path.exists():
        return
    rulesets_dir = root / "rulesets"
    if not rulesets_dir.exists():
        return
    for yml_file in rulesets_dir.rglob("*.yml"):
        try:
            data = yaml.safe_load(yml_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                issues.append(f"{yml_file.name}: not a dict")
                continue
            if "kind" not in data:
                issues.append(f"{yml_file.name}: missing 'kind'")
            if "metadata" not in data:
                issues.append(f"{yml_file.name}: missing 'metadata'")
        except yaml.YAMLError as e:
            issues.append(f"{yml_file.name}: parse error {e}")


def check_catalog_version_format(issues: list[str]) -> None:
    """Check catalog files for version format."""
    root = ROOT
    catalogs_dir = root / "governance" / "assets" / "catalogs"
    if not catalogs_dir.exists():
        return
    for cat_file in catalogs_dir.rglob("*.yaml"):
        try:
            data = yaml.safe_load(cat_file.read_text(encoding="utf-8"))
            if data and "version" in data:
                version = str(data["version"])
                if not version.replace(".", "").isdigit():
                    issues.append(f"{cat_file.name}: invalid version format")
        except yaml.YAMLError:
            pass


def check_artifact_hash_integrity(issues: list[str]) -> None:
    """Check artifact hash files for consistency."""
    root = ROOT
    hashes_file = root / "hashes.json"
    if not hashes_file.exists():
        return
    try:
        data = json.loads(hashes_file.read_text(encoding="utf-8"))
        if "artifacts" not in data:
            issues.append("hashes.json: missing 'artifacts' key")
    except json.JSONDecodeError:
        issues.append("hashes.json: invalid JSON")


def main() -> int:
    root = ROOT

    # Canonical SSOT paths that should exist in a migrated repo
    ssot_candidates = [
        root / "governance_content" / "master.md",
        root / "governance_content" / "rules.md",
        root / "governance_spec" / "phase_api.yaml",
        root / "governance_spec" / "rules.yml",
        root / "governance_spec" / "rulesets" / "core" / "rules.yml",
    ]

    # Optional extra docs under governance_content/docs
    docs_dir = root / "governance_content" / "docs"
    if docs_dir.exists():
        for dname in ["phases.md", "operator-runbook.md"]:
            cand = docs_dir / dname
            if not cand.exists():
                ssot_candidates.append(cand)

    missing = [p for p in ssot_candidates if not p.exists()]
    if missing:
        msg = {"status": "MISSING", "missing": [str(p) for p in missing]}
        print(json.dumps(msg))
        for m in missing:
            print(f" - {m}", file=sys.stderr)
        return 1
    msg = {"status": "OK"}
    print(json.dumps(msg))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
