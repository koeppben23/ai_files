#!/usr/bin/env python3
"""Validate YAML rulebooks against the governance schema.

Usage:
    python scripts/validate_rulebook.py rulesets/profiles/rules.backend-python.yml
    python scripts/validate_rulebook.py rulesets/core/rules.yml rulesets/profiles/*.yml
    python scripts/validate_rulebook.py --all

Exit codes:
    0  All files valid
    1  Validation errors found
    2  Usage error (bad arguments, missing dependencies)

Designed for operator use: clear, actionable error messages with file paths
and JSON path locations for each issue.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

try:
    from jsonschema import Draft202012Validator
except ImportError:
    print("ERROR: jsonschema required. Install with: pip install jsonschema", file=sys.stderr)
    sys.exit(2)


def _load_schema(schema_path: Path) -> dict:
    """Load and return the rulebook JSON schema."""
    if not schema_path.exists():
        print(f"ERROR: Schema not found: {schema_path}", file=sys.stderr)
        sys.exit(2)
    return json.loads(schema_path.read_text(encoding="utf-8"))


def validate_file(path: Path, schema: dict) -> list[str]:
    """Validate a single YAML file. Returns list of human-readable error strings."""
    issues: list[str] = []

    if not path.exists():
        return [f"File not found: {path}"]

    if not path.suffix in (".yml", ".yaml"):
        return [f"Not a YAML file: {path}"]

    # Parse YAML
    try:
        content = path.read_text(encoding="utf-8")
        rulebook = yaml.safe_load(content)
    except yaml.YAMLError as e:
        return [f"YAML parse error: {e}"]

    if not isinstance(rulebook, dict):
        return [f"Expected YAML mapping (object), got {type(rulebook).__name__}"]

    # JSON Schema validation
    validator = Draft202012Validator(schema)
    for error in sorted(validator.iter_errors(rulebook), key=lambda e: list(e.absolute_path)):
        location = error.json_path or "$"
        issues.append(f"  {location}: {error.message}")

    # Schema version compatibility check
    schema_version = schema.get("version", "")
    rb_meta = rulebook.get("metadata") or {}
    rb_schema_ver = rb_meta.get("schema_version", "")

    if not rb_schema_ver and not any("schema_version" in i for i in issues):
        issues.append("  $.metadata.schema_version: missing (required for version tracking)")
    elif rb_schema_ver and schema_version:
        schema_major = schema_version.split(".")[0]
        rb_major = rb_schema_ver.split(".")[0]
        if schema_major != rb_major:
            issues.append(
                f"  $.metadata.schema_version: incompatible major version — "
                f"rulebook targets {rb_schema_ver} but schema is {schema_version}"
            )

    # Kind-specific checks
    kind = rulebook.get("kind", "")
    if kind not in ("core", "profile"):
        if not any("kind" in i for i in issues):
            issues.append(f"  $.kind: must be 'core' or 'profile', got '{kind}'")

    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate YAML rulebooks against the governance schema.",
        epilog="Examples:\n"
               "  python scripts/validate_rulebook.py rulesets/core/rules.yml\n"
               "  python scripts/validate_rulebook.py rulesets/profiles/*.yml\n"
               "  python scripts/validate_rulebook.py --all\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "files", nargs="*", type=Path,
        help="YAML rulebook files to validate",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Validate all YAML rulebooks under rulesets/",
    )
    parser.add_argument(
        "--schema", type=Path, default=None,
        help="Path to rulebook.schema.json (default: schemas/rulebook.schema.json)",
    )
    parser.add_argument(
        "--repo-root", type=Path, default=None,
        help="Repository root (default: auto-detect from script location)",
    )
    parser.add_argument(
        "--json", action="store_true", dest="json_output",
        help="Output structured JSON report (schema: governance.validate-rulebook-report.v1)",
    )
    args = parser.parse_args(argv)

    root = args.repo_root.resolve() if args.repo_root else REPO_ROOT
    schema_path = args.schema or (root / "schemas" / "rulebook.schema.json")
    schema = _load_schema(schema_path)

    # Collect files
    files: list[Path] = []
    if args.all:
        rulesets_dir = root / "rulesets"
        if not rulesets_dir.exists():
            print(f"ERROR: No rulesets directory at {rulesets_dir}", file=sys.stderr)
            return 2
        files = sorted(rulesets_dir.glob("**/*.yml"))
        if not files:
            print(f"ERROR: No .yml files found under {rulesets_dir}", file=sys.stderr)
            return 2
    elif args.files:
        files = args.files
    else:
        parser.error("Provide files to validate or use --all")

    # Validate
    total = 0
    failed = 0
    results: list[dict] = []
    for path in files:
        total += 1
        issues = validate_file(path, schema)
        rel = str(path.relative_to(root) if path.is_relative_to(root) else path)

        if issues:
            failed += 1
            # Build structured error entries
            errors = []
            for issue in issues:
                stripped = issue.strip()
                # Parse "$.path: message" format from validate_file
                if ": " in stripped and stripped.startswith("$"):
                    colon_idx = stripped.index(": ")
                    errors.append({
                        "path": stripped[:colon_idx],
                        "message": stripped[colon_idx + 2:],
                    })
                else:
                    errors.append({"path": "$", "message": stripped})
            results.append({"file": rel, "valid": False, "errors": errors})

            if not args.json_output:
                print(f"FAIL {rel}")
                for issue in issues:
                    print(issue)
                print()
        else:
            results.append({"file": rel, "valid": True, "errors": []})
            if not args.json_output:
                print(f"  OK {rel}")

    # Output
    if args.json_output:
        report = {
            "schema": "governance.validate-rulebook-report.v1",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "files_checked": total,
            "files_valid": total - failed,
            "files_invalid": failed,
            "results": results,
        }
        print(json.dumps(report, indent=2))
    else:
        # Human-readable summary
        print(f"\n{'=' * 50}")
        if failed:
            print(f"FAILED: {failed}/{total} file(s) have validation errors")
        else:
            print(f"OK: {total} file(s) validated successfully")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
