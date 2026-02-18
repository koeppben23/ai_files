#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import platform
from pathlib import Path

from governance.infrastructure.binding_evidence_resolver import BindingEvidenceResolver


def _abs(path: Path) -> Path:
    return Path(os.path.normpath(os.path.abspath(str(path))))


def main() -> int:
    resolver = BindingEvidenceResolver()
    evidence = resolver.resolve(mode="start")
    if not evidence.binding_ok:
        payload = {
            "schema": "opencode-governance.paths.v1",
            "status": "blocked",
            "reason_code": "BLOCKED-MISSING-BINDING-FILE",
            "message": "Installer-owned governance.paths.json exists but could not be loaded via resolver.",
            "bindingEvidenceSource": evidence.source,
        }
        print(json.dumps(payload, ensure_ascii=True))
        return 0

    binding_file = evidence.governance_paths_json
    if binding_file is not None and Path(binding_file).exists():
        try:
            print(Path(binding_file).read_text(encoding="utf-8"))
            return 0
        except Exception:
            pass

    payload = {
        "schema": "opencode-governance.paths.v1",
        "status": "blocked",
        "reason_code": "BLOCKED-MISSING-BINDING-FILE",
        "bindingEvidenceSource": evidence.source,
    }
    print(json.dumps(payload, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
