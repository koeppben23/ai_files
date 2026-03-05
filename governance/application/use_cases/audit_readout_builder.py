"""Build AUDIT_READOUT_SPEC.v1 payloads from workspace artifacts."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Mapping

from governance.domain.audit_readout_contract import validate_audit_readout_v1
from governance.domain.canonical_json import canonical_json_hash

POINTER_SCHEMA = "opencode-session-pointer.v1"
_LEGACY_POINTER_SCHEMA = "active-session-pointer.v1"


def _read_json(path: Path) -> dict[str, object]:
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return data


def _extract_state_view(document: Mapping[str, object]) -> Mapping[str, object]:
    nested = document.get("SESSION_STATE")
    if isinstance(nested, Mapping):
        return nested
    return document


def _state_text(state: Mapping[str, object], *keys: str) -> str:
    for key in keys:
        value = state.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return str(value)
    return ""


def _as_rfc3339_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _extract_updated_at(state: Mapping[str, object], *, session_path: Path) -> str:
    value = _state_text(
        state,
        "updated_at",
        "UpdatedAt",
        "phase4_intake_updated_at",
        "phase4IntakeUpdatedAt",
    )
    if value.endswith("Z"):
        return value
    mtime = datetime.fromtimestamp(session_path.stat().st_mtime, tz=timezone.utc)
    return _as_rfc3339_z(mtime)


def _parse_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        row = line.strip()
        if not row:
            continue
        try:
            item = json.loads(row)
        except Exception:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _event_with_required_fields(event: Mapping[str, object]) -> Mapping[str, object] | None:
    required = ("event", "observed_at", "repo_fingerprint", "session_id", "run_id")
    for key in required:
        value = event.get(key)
        if not isinstance(value, str) or not value.strip():
            return None
    normalized: dict[str, object] = {key: str(event[key]).strip() for key in required}
    optional = (
        "reason",
        "new_run_id",
        "previous_run_id",
        "phase",
        "next",
        "snapshot_path",
        "snapshot_digest",
    )
    for key in optional:
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            normalized[key] = value.strip()
    return normalized


def _list_snapshot_files(workspace_dir: Path) -> list[Path]:
    runs_dir = workspace_dir / "work_runs"
    if not runs_dir.exists() or not runs_dir.is_dir():
        return []
    return sorted(
        [path for path in runs_dir.glob("*.json") if path.is_file()],
        key=lambda p: (p.stat().st_mtime, str(p)),
    )


def _build_last_snapshot(workspace_dir: Path) -> tuple[dict[str, object], list[str]]:
    notes: list[str] = []
    files = _list_snapshot_files(workspace_dir)
    if not files:
        return {
            "snapshot_path": "none",
            "snapshot_digest": "0" * 64,
            "archived_at": "1970-01-01T00:00:00Z",
            "source_phase": "none",
            "run_id": "none",
        }, ["missing-work-run-snapshot"]

    path = files[-1]
    payload = _read_json(path)
    digest = canonical_json_hash(payload)

    return {
        "snapshot_path": str(path),
        "snapshot_digest": digest,
        "archived_at": str(payload.get("archived_at") or "1970-01-01T00:00:00Z"),
        "source_phase": str(payload.get("source_phase") or "unknown"),
        "run_id": str(payload.get("session_run_id") or "unknown"),
    }, notes


def _timestamps_monotonic(events: list[dict[str, object]], *, last_snapshot: Mapping[str, object]) -> tuple[bool, list[str]]:
    notes: list[str] = []
    previous: datetime | None = None
    try:
        snapshot_dt = datetime.strptime(str(last_snapshot.get("archived_at") or ""), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except Exception:
        notes.append("invalid-last-snapshot-archived-at")
        return False, notes

    first_ref_dt: datetime | None = None
    for event in events:
        observed = str(event.get("observed_at") or "")
        try:
            observed_dt = datetime.strptime(observed, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except Exception:
            notes.append(f"invalid-event-timestamp:{observed}")
            return False, notes
        if previous is not None and observed_dt < previous:
            notes.append("event-timestamps-not-monotonic")
            return False, notes
        previous = observed_dt

        snapshot_path = str(last_snapshot.get("snapshot_path") or "")
        snapshot_digest = str(last_snapshot.get("snapshot_digest") or "")
        if (
            str(event.get("snapshot_path") or "") == snapshot_path
            or str(event.get("snapshot_digest") or "") == snapshot_digest
        ):
            if first_ref_dt is None:
                first_ref_dt = observed_dt

    if first_ref_dt is not None and snapshot_dt > first_ref_dt:
        notes.append("snapshot-after-first-reference")
        return False, notes
    return True, notes


def _run_id_consistent(active: Mapping[str, object], events: list[dict[str, object]]) -> tuple[bool, list[str]]:
    notes: list[str] = []
    if not events:
        notes.append("no-events-in-tail")
        return False, notes

    active_run_id = str(active.get("run_id") or "")
    last = events[-1]
    if str(last.get("event") or "") == "new_work_session_created":
        expected = str(last.get("new_run_id") or "")
        if active_run_id != expected:
            notes.append("active-run-id-mismatch-created-event")
            return False, notes
        return True, notes

    expected = str(last.get("run_id") or "")
    if active_run_id != expected:
        notes.append("active-run-id-mismatch-tail-event")
        return False, notes
    return True, notes


def _snapshot_ref_present(events: list[dict[str, object]], *, last_snapshot: Mapping[str, object]) -> tuple[bool, list[str]]:
    notes: list[str] = []
    last_path = str(last_snapshot.get("snapshot_path") or "")
    last_digest = str(last_snapshot.get("snapshot_digest") or "")
    for event in events:
        if str(event.get("event") or "") != "new_work_session_created":
            continue
        event_path = str(event.get("snapshot_path") or "")
        event_digest = str(event.get("snapshot_digest") or "")
        if event_path and event_digest and (event_path == last_path or event_digest == last_digest):
            return True, notes
    notes.append("missing-created-event-snapshot-reference")
    return False, notes


def build_audit_readout(
    *,
    commands_home: Path,
    tail_count: int = 25,
) -> dict[str, object]:
    """Build an AUDIT_READOUT_SPEC.v1 payload from workspace artifacts."""

    config_root = commands_home.parent
    pointer_path = config_root / "SESSION_STATE.json"
    if not pointer_path.exists():
        raise FileNotFoundError(f"No session pointer at {pointer_path}")

    pointer = _read_json(pointer_path)
    schema = str(pointer.get("schema") or "")
    if schema not in {POINTER_SCHEMA, _LEGACY_POINTER_SCHEMA}:
        raise ValueError(f"Unknown pointer schema: {schema}")

    session_file_raw = pointer.get("activeSessionStateFile")
    if not session_file_raw:
        rel = pointer.get("activeSessionStateRelativePath")
        if isinstance(rel, str) and rel:
            session_file_raw = str(config_root / rel)
    if not isinstance(session_file_raw, str) or not session_file_raw:
        raise ValueError("Pointer contains no session state file path")

    session_path = Path(session_file_raw)
    state_document = _read_json(session_path)
    state = _extract_state_view(state_document)

    active = {
        "run_id": _state_text(state, "session_run_id") or "unknown",
        "phase": _state_text(state, "Phase", "phase") or "unknown",
        "active_gate": _state_text(state, "active_gate", "ActiveGate") or "unknown",
        "next": _state_text(state, "Next", "next") or "unknown",
        "updated_at": _extract_updated_at(state, session_path=session_path),
    }

    last_snapshot, snapshot_notes = _build_last_snapshot(session_path.parent)

    events_raw = _parse_jsonl(session_path.parent / "events.jsonl")
    normalized_events: list[dict[str, object]] = []
    for event in events_raw:
        normalized = _event_with_required_fields(event)
        if normalized is not None:
            normalized_events.append(normalized)
    tail = normalized_events[-max(0, int(tail_count)):]

    snapshot_ref_present, snapshot_ref_notes = _snapshot_ref_present(tail, last_snapshot=last_snapshot)
    run_id_consistent, run_id_notes = _run_id_consistent(active, tail)
    monotonic_timestamps, monotonic_notes = _timestamps_monotonic(tail, last_snapshot=last_snapshot)

    payload = {
        "contract_version": "AUDIT_READOUT_SPEC.v1",
        "active": active,
        "last_snapshot": last_snapshot,
        "chain": {
            "tail_count": len(tail),
            "events": tail,
        },
        "integrity": {
            "snapshot_ref_present": snapshot_ref_present,
            "run_id_consistent": run_id_consistent,
            "monotonic_timestamps": monotonic_timestamps,
            "notes": snapshot_notes + snapshot_ref_notes + run_id_notes + monotonic_notes,
        },
    }

    validation_errors = validate_audit_readout_v1(payload)
    if validation_errors:
        raise ValueError("invalid audit readout contract: " + "; ".join(validation_errors))
    return payload


__all__ = ["build_audit_readout"]
