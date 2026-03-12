"""D1 static verification for requirement hotspots."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping


def run_static_verification(*, requirements: tuple[Mapping[str, object], ...], repo_root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for contract in requirements:
        req_id = str(contract.get("id") or "").strip()
        hotspots = contract.get("code_hotspots")
        if not isinstance(hotspots, list) or not hotspots:
            out[req_id] = "FAIL"
            continue
        missing = False
        for hotspot in hotspots:
            if not (repo_root / str(hotspot)).exists():
                missing = True
                break
        out[req_id] = "FAIL" if missing else "PASS"
    return out
