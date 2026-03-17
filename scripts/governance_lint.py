#!/usr/bin/env python3
from __future__ import annotations
import hashlib
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
    schema = None
    if schema_path.exists():
        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    
    rulesets_dir = root / "rulesets"
    if not rulesets_dir.exists():
        rulesets_dir = root / "governance_spec" / "rulesets"
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
            elif data.get("kind") not in ("core", "profile"):
                issues.append(f"{yml_file.name}: schema violation - kind must be 'core' or 'profile'")
            if "metadata" not in data:
                issues.append(f"{yml_file.name}: missing 'metadata'")
            else:
                metadata = data.get("metadata", {})
                if "schema_version" not in metadata:
                    issues.append(f"{yml_file.name}: missing metadata.schema_version")
                elif schema and "version" in schema:
                    doc_version = str(metadata.get("schema_version", ""))
                    schema_version = str(schema.get("version", ""))
                    if doc_version and schema_version:
                        doc_major = doc_version.split(".")[0] if "." in doc_version else doc_version
                        schema_major = schema_version.split(".")[0] if "." in schema_version else schema_version
                        if doc_major != schema_major:
                            issues.append(f"{yml_file.name}: schema_version mismatch - doc={doc_version}, schema={schema_version}")
        except yaml.YAMLError as e:
            issues.append(f"{yml_file.name}: failed to parse")


def check_catalog_version_format(issues: list[str]) -> None:
    """Check catalog files for semver-3 version format."""
    root = ROOT
    catalogs_dir = root / "governance" / "assets" / "catalogs"
    if not catalogs_dir.exists():
        catalogs_dir = root / "governance_content" / "governance" / "assets" / "catalogs"
    if not catalogs_dir.exists():
        return
    for cat_file in catalogs_dir.rglob("*.json"):
        try:
            data = json.loads(cat_file.read_text(encoding="utf-8"))
            if "catalog_version" in data:
                issues.append(f"{cat_file.name}: legacy key 'catalog_version' found")
            if "version" in data:
                version = str(data["version"])
                parts = version.split(".")
                if len(parts) != 3:
                    issues.append(f"{cat_file.name}: version '{version}' not semver-3 (need MAJOR.MINOR.PATCH)")
                elif not all(p.isdigit() for p in parts):
                    issues.append(f"{cat_file.name}: version '{version}' not semver-3 (must be numeric)")
        except json.JSONDecodeError:
            pass


def check_artifact_hash_integrity(issues: list[str]) -> None:
    """Check artifact hash files for consistency with actual files."""
    root = ROOT
    rulesets_dir = root / "rulesets" / "governance"
    if not rulesets_dir.exists():
        rulesets_dir = root / "governance_spec" / "rulesets" / "governance"
    if not rulesets_dir.exists():
        return
    for release_dir in rulesets_dir.iterdir():
        if not release_dir.is_dir():
            continue
        hashes_file = release_dir / "hashes.json"
        manifest_file = release_dir / "manifest.json"
        lock_file = release_dir / "lock.json"
        if not hashes_file.exists():
            continue
        try:
            hashes = json.loads(hashes_file.read_text(encoding="utf-8"))
            files_to_check = {}
            if manifest_file.exists():
                files_to_check["manifest.json"] = manifest_file
            if lock_file.exists():
                files_to_check["lock.json"] = lock_file
            for fname, fpath in files_to_check.items():
                if fname in hashes:
                    actual_hash = hashlib.sha256(fpath.read_bytes()).hexdigest()
                    if hashes[fname] != actual_hash:
                        issues.append(f"{release_dir.name}/hashes.json: integrity FAILED for {fname}")
        except json.JSONDecodeError:
            issues.append(f"{release_dir.name}/hashes.json: invalid JSON")


def main() -> int:
    root = ROOT

    # Canonical SSOT paths that should exist in a migrated repo
    # References: docs/resume.md, docs/resume_prompt.md, docs/new_profile.md, docs/new_addon.md
    # References: docs/phases.md, docs/operator-runbook.md
    ssot_candidates = [
        root / "governance_content" / "master.md",
        root / "governance_content" / "rules.md",
        root / "governance_spec" / "phase_api.yaml",
        root / "governance_spec" / "rules.yml",
        root / "governance_spec" / "rulesets" / "core" / "rules.yml",
    ]

    # Optional extra docs under governance_content/docs
    # Also reference: docs/resume.md, docs/resume_prompt.md, docs/new_profile.md, docs/new_addon.md
    docs_dir = root / "governance_content" / "docs"
    if docs_dir.exists():
        for dname in ["phases.md", "operator-runbook.md", "resume.md", "resume_prompt.md", "new_profile.md", "new_addon.md"]:
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
