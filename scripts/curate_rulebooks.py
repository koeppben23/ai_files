#!/usr/bin/env python3
from __future__ import annotations
import json
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    
    rulesets_dir = root / "governance_spec" / "rulesets"
    profiles_dir = root / "governance_content" / "profiles"
    
    missing = []
    if not rulesets_dir.exists():
        missing.append(str(rulesets_dir))
    if not profiles_dir.exists():
        missing.append(str(profiles_dir))
    
    if missing:
        print(json.dumps({"status": "MISSING", "missing": missing}))
        return 1
    
    print(json.dumps({"status": "OK", "message": "Rulebook directories present"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
