#!/usr/bin/env python3
"""Migrate YAML rulebooks between schema versions.

Usage:
    python scripts/migrate_rulebook_schema.py --target-version 2.0.0 [--dry-run]
    python scripts/migrate_rulebook_schema.py --check

Migration strategy:
    - Each migration step is a function registered in MIGRATIONS.
    - Steps are applied sequentially from the rulebook's current schema_version
      to the target version.
    - --dry-run prints what would change without writing.
    - --check validates all rulebooks declare a schema_version compatible with
      the current schema.

Adding a new migration:
    1. Bump the version in schemas/rulebook.schema.json
    2. Add a migration function: def migrate_1_0_0_to_2_0_0(rulebook: dict) -> dict
    3. Register it in MIGRATIONS: ("1.0.0", "2.0.0"): migrate_1_0_0_to_2_0_0
    4. Run: python scripts/migrate_rulebook_schema.py --target-version 2.0.0
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable

try:
    import yaml
except ImportError:
    print("ERROR: pyyaml required. Install with: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# Migration registry
# ---------------------------------------------------------------------------
# Each key is (from_version, to_version), value is the migration function.
# Functions receive a parsed rulebook dict and return the migrated dict.
#
# Example:
#   def migrate_1_0_0_to_2_0_0(rb: dict) -> dict:
#       rb["metadata"]["schema_version"] = "2.0.0"
#       # ... transform fields ...
#       return rb
#
#   MIGRATIONS[("1.0.0", "2.0.0")] = migrate_1_0_0_to_2_0_0

MigrationFn = Callable[[dict], dict]
MIGRATIONS: dict[tuple[str, str], MigrationFn] = {}


# ---------------------------------------------------------------------------
# Migration: 1.0.0 → 1.1.0
# ---------------------------------------------------------------------------
# Adds optional metadata.description field (empty string default).
# Bumps schema_version from 1.0.0 to 1.1.0.


def _migrate_1_0_0_to_1_1_0(rb: dict) -> dict:
    """Add metadata.description and bump schema_version to 1.1.0."""
    rb = dict(rb)
    meta = dict(rb.get("metadata", {}))
    meta["schema_version"] = "1.1.0"
    if "description" not in meta:
        meta["description"] = ""
    rb["metadata"] = meta
    return rb


MIGRATIONS[("1.0.0", "1.1.0")] = _migrate_1_0_0_to_1_1_0


def _get_schema_version() -> str:
    """Read current schema version from rulebook.schema.json."""
    schema_path = ROOT / "schemas" / "rulebook.schema.json"
    schema = json.loads(schema_path.read_text())
    return schema.get("version", "unknown")


def _parse_version(v: str) -> tuple[int, ...]:
    """Parse semver string to comparable tuple."""
    return tuple(int(x) for x in v.split("."))


def _find_migration_path(from_ver: str, to_ver: str) -> list[tuple[str, str]]:
    """Find ordered migration steps from from_ver to to_ver."""
    if from_ver == to_ver:
        return []

    # BFS through registered migrations
    visited = {from_ver}
    queue: list[tuple[str, list[tuple[str, str]]]] = [(from_ver, [])]

    while queue:
        current, path = queue.pop(0)
        for (src, dst), _fn in sorted(MIGRATIONS.items()):
            if src == current and dst not in visited:
                new_path = path + [(src, dst)]
                if dst == to_ver:
                    return new_path
                visited.add(dst)
                queue.append((dst, new_path))

    return []  # No path found


def migrate_rulebook(rulebook: dict, target_version: str) -> tuple[dict, list[str]]:
    """Apply migration steps to a rulebook. Returns (migrated_dict, log_messages)."""
    current = (rulebook.get("metadata") or {}).get("schema_version", "")
    if not current:
        return rulebook, ["SKIP: no schema_version in metadata"]

    if current == target_version:
        return rulebook, [f"already at {target_version}"]

    path = _find_migration_path(current, target_version)
    if not path:
        return rulebook, [f"ERROR: no migration path from {current} to {target_version}"]

    log: list[str] = []
    for src, dst in path:
        fn = MIGRATIONS[(src, dst)]
        rulebook = fn(rulebook)
        log.append(f"migrated {src} -> {dst}")

    return rulebook, log


def check_all(target_version: str | None = None) -> int:
    """Check all rulebooks have compatible schema_version. Returns exit code."""
    schema_version = target_version or _get_schema_version()
    schema_major = _parse_version(schema_version)[0]

    rulesets_dir = ROOT / "rulesets"
    if not rulesets_dir.exists():
        print("No rulesets directory found.")
        return 1

    issues: list[str] = []
    count = 0
    for yml in sorted(rulesets_dir.glob("**/*.yml")):
        rb = yaml.safe_load(yml.read_text())
        sv = (rb.get("metadata") or {}).get("schema_version", "")
        count += 1
        if not sv:
            issues.append(f"  {yml.relative_to(ROOT)}: missing schema_version")
        else:
            rb_major = _parse_version(sv)[0]
            if rb_major != schema_major:
                issues.append(
                    f"  {yml.relative_to(ROOT)}: schema_version {sv} "
                    f"incompatible with schema {schema_version} (major mismatch)"
                )

    if issues:
        print(f"Schema version check FAILED ({len(issues)} issues in {count} rulebooks):")
        for issue in issues:
            print(issue)
        return 1

    print(f"Schema version check OK: {count} rulebooks at major version {schema_major} (schema {schema_version})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Migrate YAML rulebooks between schema versions.")
    parser.add_argument("--target-version", help="Target schema version (semver)")
    parser.add_argument("--check", action="store_true", help="Check all rulebooks have compatible schema_version")
    parser.add_argument("--dry-run", action="store_true", help="Print what would change without writing")
    args = parser.parse_args(argv)

    if args.check:
        return check_all(args.target_version)

    if not args.target_version:
        parser.error("--target-version is required unless --check is used")

    target = args.target_version
    rulesets_dir = ROOT / "rulesets"
    if not rulesets_dir.exists():
        print("No rulesets directory found.")
        return 1

    total = 0
    migrated = 0
    errors = 0
    for yml in sorted(rulesets_dir.glob("**/*.yml")):
        total += 1
        rb = yaml.safe_load(yml.read_text())
        result, log = migrate_rulebook(rb, target)

        prefix = f"  {yml.relative_to(ROOT)}:"
        for msg in log:
            if msg.startswith("ERROR"):
                print(f"{prefix} {msg}")
                errors += 1
            elif msg.startswith("SKIP") or msg.startswith("already"):
                print(f"{prefix} {msg}")
            else:
                print(f"{prefix} {msg}")
                migrated += 1

        if not args.dry_run and any("migrated" in m for m in log):
            yml.write_text(yaml.dump(result, default_flow_style=False, sort_keys=False, allow_unicode=True))

    mode = "DRY-RUN" if args.dry_run else "APPLIED"
    print(f"\n{mode}: {migrated} migrated, {total - migrated - errors} unchanged, {errors} errors")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
