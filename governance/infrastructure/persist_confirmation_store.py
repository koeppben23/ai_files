from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping

from governance.domain.canonical_json import canonical_json_text
from governance.domain.reason_codes import PERSIST_DISALLOWED_IN_PIPELINE, REASON_CODE_NONE
from governance.infrastructure.fs_atomic import atomic_write_text


@dataclass(frozen=True)
class PersistConfirmationResult:
    ok: bool
    reason_code: str
    reason: str


def load_persist_confirmation_evidence(*, evidence_path: Path | None) -> dict[str, Any]:
    if evidence_path is None or not evidence_path.exists():
        return {"schema": "persist-confirmations.v1", "items": []}
    try:
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    except Exception:
        return {"schema": "persist-confirmations.v1", "items": []}
    if not isinstance(payload, dict):
        return {"schema": "persist-confirmations.v1", "items": []}
    items = payload.get("items")
    if not isinstance(items, list):
        payload["items"] = []
    return payload


def has_persist_confirmation(
    evidence: Mapping[str, Any] | None,
    *,
    scope: str,
    gate: str,
    value: str,
) -> bool:
    if evidence is None:
        return False
    items = evidence.get("items") if isinstance(evidence, Mapping) else None
    if not isinstance(items, list):
        return False
    for item in items:
        if not isinstance(item, Mapping):
            continue
        if str(item.get("scope") or "").strip() != scope:
            continue
        if str(item.get("gate") or "").strip() != gate:
            continue
        if str(item.get("value") or "").strip() != value:
            continue
        return True
    return False


def record_persist_confirmation(
    *,
    evidence_path: Path,
    scope: str,
    gate: str,
    value: str,
    mode: str,
    reason: str,
) -> PersistConfirmationResult:
    if mode.strip().lower() == "pipeline":
        return PersistConfirmationResult(False, PERSIST_DISALLOWED_IN_PIPELINE, "pipeline-cannot-record-confirmation")

    payload = load_persist_confirmation_evidence(evidence_path=evidence_path)
    items = payload.get("items")
    if not isinstance(items, list):
        items = []
        payload["items"] = items

    items.append(
        {
            "scope": scope,
            "gate": gate,
            "value": value,
            "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "reason": reason,
            "mode": mode,
        }
    )
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(evidence_path, canonical_json_text(payload) + "\n")
    return PersistConfirmationResult(True, REASON_CODE_NONE, "ok")
