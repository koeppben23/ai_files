"""AUDIT_READOUT_SPEC.v1 contract validator."""

from __future__ import annotations

import re
from typing import Mapping

from governance.engine.schema_validator import validate_against_schema


_RFC3339_UTC_Z_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")


AUDIT_READOUT_SCHEMA_V1: dict[str, object] = {
    "type": "object",
    "required": ["contract_version", "active", "last_snapshot", "chain", "integrity"],
    "properties": {
        "contract_version": {"type": "string", "const": "AUDIT_READOUT_SPEC.v1"},
        "active": {
            "type": "object",
            "required": ["run_id", "phase", "active_gate", "next", "updated_at"],
            "properties": {
                "run_id": {"type": "string", "minLength": 1},
                "phase": {"type": "string", "minLength": 1},
                "active_gate": {"type": "string", "minLength": 1},
                "next": {"type": "string", "minLength": 1},
                "updated_at": {"type": "string", "pattern": _RFC3339_UTC_Z_RE.pattern},
            },
        },
        "last_snapshot": {
            "type": "object",
            "required": [
                "snapshot_path",
                "snapshot_digest",
                "archived_at",
                "source_phase",
                "run_id",
                "run_status",
                "integrity_status",
            ],
            "properties": {
                "snapshot_path": {"type": "string", "minLength": 1},
                "snapshot_digest": {"type": "string", "pattern": _SHA256_HEX_RE.pattern},
                "archived_at": {"type": "string", "pattern": _RFC3339_UTC_Z_RE.pattern},
                "source_phase": {"type": "string", "minLength": 1},
                "run_id": {"type": "string", "minLength": 1},
                "run_status": {
                    "type": "string",
                    "enum": ["in_progress", "materialized", "finalized", "failed", "invalidated", "unknown"],
                },
                "integrity_status": {
                    "type": "string",
                    "enum": ["pending", "passed", "failed", "unknown"],
                },
            },
        },
        "chain": {
            "type": "object",
            "required": ["tail_count", "events"],
            "properties": {
                "tail_count": {"type": "integer", "minimum": 0},
                "events": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["event", "observed_at", "repo_fingerprint", "session_id", "run_id"],
                        "properties": {
                            "event": {"type": "string", "minLength": 1},
                            "observed_at": {"type": "string", "pattern": _RFC3339_UTC_Z_RE.pattern},
                            "repo_fingerprint": {"type": "string", "minLength": 1},
                            "session_id": {"type": "string", "minLength": 1},
                            "run_id": {"type": "string", "minLength": 1},
                        },
                    },
                },
            },
        },
        "integrity": {
            "type": "object",
            "required": [
                "snapshot_ref_present",
                "run_id_consistent",
                "monotonic_timestamps",
                "active_run_pointer_consistent",
                "reactivation_chain_consistent",
                "snapshot_quality_ok",
                "run_archives_verified",
            ],
            "properties": {
                "snapshot_ref_present": {"type": "boolean"},
                "run_id_consistent": {"type": "boolean"},
                "monotonic_timestamps": {"type": "boolean"},
                "active_run_pointer_consistent": {"type": "boolean"},
                "reactivation_chain_consistent": {"type": "boolean"},
                "snapshot_quality_ok": {"type": "boolean"},
                "run_archives_verified": {"type": "boolean"},
                "notes": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
        },
    },
}


def validate_audit_readout_v1(payload: Mapping[str, object]) -> list[str]:
    """Return deterministic validation errors for audit readout payload."""

    errors = validate_against_schema(schema=AUDIT_READOUT_SCHEMA_V1, value=dict(payload))

    chain = payload.get("chain")
    events = chain.get("events") if isinstance(chain, Mapping) else None
    if isinstance(events, list):
        for idx, event in enumerate(events):
            if not isinstance(event, Mapping):
                continue
            event_type = str(event.get("event") or "")
            if event_type == "new_work_session_created":
                if not isinstance(event.get("snapshot_path"), str) or not str(event.get("snapshot_path") or "").strip():
                    errors.append(f"$.chain.events[{idx}].snapshot_path:required-for-created")
                digest = event.get("snapshot_digest")
                if not isinstance(digest, str) or _SHA256_HEX_RE.match(digest) is None:
                    errors.append(f"$.chain.events[{idx}].snapshot_digest:required-for-created")
            if event_type == "work_session_reactivated":
                reactivated_run_id = event.get("reactivated_run_id")
                if not isinstance(reactivated_run_id, str) or not reactivated_run_id.strip():
                    errors.append(f"$.chain.events[{idx}].reactivated_run_id:required-for-reactivation")
            if event_type in {"new_work_session_deduped", "new_work_session_dedupe_bypassed"}:
                reason = event.get("reason")
                if not isinstance(reason, str) or not reason.strip():
                    errors.append(f"$.chain.events[{idx}].reason:required-for-dedupe-events")
    return errors


__all__ = [
    "AUDIT_READOUT_SCHEMA_V1",
    "validate_audit_readout_v1",
]
