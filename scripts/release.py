#!/usr/bin/env python3
from __future__ import annotations
import json
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    
    ssot_paths = [
        root / "governance_content" / "master.md",
        root / "governance_content" / "rules.md",
        root / "governance_spec" / "phase_api.yaml",
        root / "governance_spec" / "rules.yml",
        root / "governance_spec" / "rulesets" / "core" / "rules.yml",
    ]
    
    missing = [p for p in ssot_paths if not p.exists()]
    if missing:
        print(json.dumps({"status": "MISSING", "missing": [str(p) for p in missing]}))
        return 1
    
    print(json.dumps({"status": "OK", "message": "Release prerequisites satisfied"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
