from __future__ import annotations

import json

from .util import REPO_ROOT


def test_reason_remediation_map_includes_p6_prerequisites_blocker() -> None:
    path = REPO_ROOT / "governance" / "assets" / "catalogs" / "REASON_REMEDIATION_MAP.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    mappings = payload.get("mappings")
    assert isinstance(mappings, dict), "REASON_REMEDIATION_MAP.json must contain mappings object"
    assert "BLOCKED-P6-PREREQUISITES-NOT-MET" in mappings, (
        "REASON_REMEDIATION_MAP.json missing BLOCKED-P6-PREREQUISITES-NOT-MET"
    )
