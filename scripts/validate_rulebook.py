#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
import sys
import yaml
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_schema():
    schema_path = ROOT / "schemas" / "rulebook.schema.json"
    if schema_path.exists():
        return json.loads(schema_path.read_text(encoding="utf-8"))
    return None


def validate_file(path: Path, schema: dict | None) -> list[str]:
    """Validate a single YAML file against schema. Returns list of issues."""
    issues = []
    try:
        if not path.exists():
            issues.append(f"File not found: {path}")
            return issues
        # Check for YAML extension
        if path.suffix not in (".yml", ".yaml"):
            issues.append(f"{path}: Not a YAML file")
            return issues
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if data is None:
            issues.append(f"{path}: empty file")
            return issues
        # Basic validation: check for required fields instead of strict schema
        if not isinstance(data, dict):
            issues.append(f"{path}: not a valid YAML mapping")
            return issues
        # Check for basic required fields
        if "kind" not in data:
            issues.append(f"{path}: missing 'kind' field")
        if "metadata" not in data:
            issues.append(f"{path}: missing 'metadata' field")
        elif not isinstance(data.get("metadata"), dict):
            issues.append(f"{path}: 'metadata' must be a mapping")
        # Check for schema_version in metadata if schema is provided
        if schema and "metadata" in data:
            metadata = data.get("metadata", {})
            if "schema_version" not in metadata:
                issues.append(f"{path}: missing metadata.schema_version")
            else:
                # Check major version matches
                doc_version = str(metadata.get("schema_version", ""))
                schema_version = str(schema.get("version", ""))
                if doc_version and schema_version:
                    doc_major = doc_version.split(".")[0] if "." in doc_version else doc_version
                    schema_major = schema_version.split(".")[0] if "." in schema_version else schema_version
                    if doc_major != schema_major:
                        issues.append(f"{path}: schema_version major mismatch")
    except yaml.YAMLError as e:
        issues.append(f"{path}: parse error - {e}")
    return issues


def validate_yaml_file(path: Path, schema: dict | None, issues: list[str]) -> bool:
    """Validate a single YAML file against schema."""
    result = validate_file(path, schema)
    issues.extend(result)
    return len(result) == 0


def validate_all(root: Path, use_json: bool = False) -> int:
    """Validate all rulebook files."""
    issues: list[str] = []
    schema = load_schema()
    file_count = 0
    
    # Only validate rulebook files under governance_spec/rulesets and governance_content/profiles
    # Exclude profiles/addons (they have different schema)
    rulesets_dir = root / "governance_spec" / "rulesets"
    if rulesets_dir.exists():
        for yml_file in rulesets_dir.rglob("*.yml"):
            file_count += 1
            validate_yaml_file(yml_file, schema, issues)
    
    profiles_dir = root / "governance_content" / "profiles"
    if profiles_dir.exists():
        for yml_file in profiles_dir.glob("*.md"):
            continue  # Skip MD files
        for yml_file in profiles_dir.glob("*.yml"):
            # Skip addon files - they have different schema
            if "addons" in str(yml_file):
                continue
            file_count += 1
            validate_yaml_file(yml_file, schema, issues)
    
    if issues:
        msg = {"status": "FAILED", "errors": issues}
        print(json.dumps(msg) if use_json else "\n".join(issues))
        return 1
    
    msg = {"status": "OK", "message": f"{file_count} file(s) validated"}
    print(json.dumps(msg) if use_json else f"OK - {file_count} file(s) validated")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate governance rulebooks")
    parser.add_argument("--all", action="store_true", help="Validate all rulebooks")
    parser.add_argument("file", nargs="?", help="File to validate")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--schema-version", help="Expected schema version")
    parser.add_argument("--repo-root", help="Repository root path")
    
    args = parser.parse_args()
    root = Path(args.repo_root) if args.repo_root else ROOT
    
    if args.all:
        return validate_all(root, args.json)
    elif args.file:
        file_path = Path(args.file)
        if not file_path.is_absolute():
            file_path = root / file_path
        issues = validate_file(file_path, load_schema())
        if issues:
            msg = {"status": "FAILED", "errors": issues}
            print(json.dumps(msg) if args.json else "\n".join(issues))
            return 1
        msg = {"status": "OK", "message": "Validation passed"}
        print(json.dumps(msg) if args.json else "Validation passed")
        return 0
    else:
        print("Error: Specify --all or provide a file", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
