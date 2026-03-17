#!/usr/bin/env python3
from __future__ import annotations
import json

"""Lightweight governance lint stub.

This script provides a minimal, safe check that the repository contains
the canonical SSOT files under governance_spec/governance_content in
the expected locations. It is intended to be used by the installer as a
safety check during release runs, without performing expensive analyses.
"""

import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]  # repo root when invoked from scripts/

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
