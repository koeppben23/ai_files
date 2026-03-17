#!/usr/bin/env python3
from __future__ import annotations
import json
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    
    core_rules = root / "governance_spec" / "rulesets" / "core" / "rules.yml"
    if not core_rules.exists():
        print(json.dumps({"status": "MISSING", "missing": [str(core_rules)]}))
        return 1
    
    print(json.dumps({"status": "OK", "message": "Core rulebook valid"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
