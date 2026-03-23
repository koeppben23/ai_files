#!/usr/bin/env python3
"""
check_rules_compiled.py — CI sync guard: fail if rules.md changed but schema not regenerated.

SSOT:     governance_content/reference/rules.md
Artifact: governance_runtime/assets/schemas/governance_mandates.v1.schema.json

This guard ensures the committed schema is always in sync with rules.md.
Run in CI after any change to rules.md.

Exit codes:
  0 = in sync
  1 = STALE — schema needs regeneration (run scripts/compile_rules.py)
  2 = error
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).absolute().parents[1]
_RULES_MD = _REPO_ROOT / "governance_content" / "reference" / "rules.md"
_SCHEMA_OUT = _REPO_ROOT / "governance_runtime" / "assets" / "schemas" / "governance_mandates.v1.schema.json"


def main(argv: list[str] | None = None) -> int:
    if not _RULES_MD.exists():
        print(f"ERROR: SSOT not found: {_RULES_MD}", file=sys.stderr)
        return 2

    source_digest = hashlib.sha256(_RULES_MD.read_bytes()).hexdigest()

    if not _SCHEMA_OUT.exists():
        print(
            f"STALE: Schema artifact missing: {_SCHEMA_OUT.relative_to(_REPO_ROOT)}\n"
            f"  rules.md digest: {source_digest}\n"
            f"  Run: python scripts/compile_rules.py",
            file=sys.stderr,
        )
        return 1

    try:
        existing = json.loads(_SCHEMA_OUT.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"ERROR: Cannot read schema: {exc}", file=sys.stderr)
        return 2

    existing_digest = existing.get("source_digest", "")
    if existing_digest != source_digest:
        print(
            f"STALE: Schema is out of sync with rules.md\n"
            f"  rules.md digest:    {source_digest}\n"
            f"  schema source_digest: {existing_digest}\n"
            f"  Run: python scripts/compile_rules.py",
            file=sys.stderr,
        )
        return 1

    print(f"OK: schema is in sync (source_digest={source_digest[:16]}...)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
