"""Build AUDIT_READOUT_SPEC.v1 payloads from workspace artifacts."""

from __future__ import annotations

from datetime import datetime, timezone
import importlib
import json
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Tuple

from governance.domain.audit_readout_contract import validate_audit_readout_v1
from governance.domain.canonical_json import canonical_json_hash
from governance.domain.operating_profile import derive_mode_evidence

POINTER_SCHEMA = "opencode-session-pointer.v1"


def _verify_repository_manifest_proxy(runs_dir: Path, *, expected_repo_fingerprint: str) -> Tuple[bool, Optional[str]]:
    module = importlib.import_module("governance.infrastructure.io_verify")
    return module.verify_repository_manifest(runs_dir, expected_repo_fingerprint=expected_repo_fingerprint)


def _verify_run_archive_proxy(run_dir: Path) -> Tuple[bool, Dict[str, bool], Optional[str]]:
    module = importlib.import_module("governance.infrastructure.io_verify")
    return module.verify_run_archive(run_dir)


def _parse_session_pointer_document_proxy(payload: object) -> dict[str, str]:
    module = importlib.import_module("governance.infrastructure.session_pointer")
    return module.parse_session_pointer_document(payload)


def _resolve_active_session_state_path_proxy(pointer: Mapping[str, object], *, config_root: Path) -> Path:
    module = importlib.import_module("governance.infrastructure.session_pointer")
    return module.resolve_active_session_state_path(pointer, config_root=config_root)


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


def _extract_mode_fields(state: Mapping[str, object]) -> tuple[str, str, str]:
    effective, resolved, verify_policy_version = derive_mode_evidence(
        effective_operating_mode=_state_text(state, "effective_operating_mode", "operating_mode"),
        resolved_operating_mode=_state_text(state, "resolved_operating_mode", "resolvedOperatingMode"),
        verify_policy_version=_state_text(state, "verify_policy_version", "verifyPolicyVersion"),
    )
    return effective, str(resolved), verify_policy_version


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


def _event_with_required_fields(event: Mapping[str, object]) -> dict[str, object] | None:
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
        "reactivated_run_id",
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


def _read_current_run_pointer(workspace_dir: Path) -> tuple[str, list[str]]:
    notes: list[str] = []
    pointer_path = workspace_dir / "current_run.json"
    if not pointer_path.exists():
        notes.append("missing-current-run-pointer")
        return "", notes
    try:
        payload = _read_json(pointer_path)
    except Exception:
        notes.append("invalid-current-run-pointer")
        return "", notes

    run_id = str(payload.get("active_run_id") or "").strip()
    if not run_id:
        notes.append("missing-current-run-id")
    return run_id, notes


def _list_run_archives(workspace_dir: Path) -> tuple[list[dict[str, object]], list[str]]:
    notes: list[str] = []
    runs_dir = workspace_dir.parent / "governance-records" / workspace_dir.name / "runs"
    if not runs_dir.exists() or not runs_dir.is_dir():
        notes.append("missing-runs-directory")
        return [], notes

    fingerprint_hint = workspace_dir.name
    repo_manifest_ok, repo_manifest_message = _verify_repository_manifest_proxy(
        runs_dir,
        expected_repo_fingerprint=fingerprint_hint,
    )
    if not repo_manifest_ok:
        notes.append(f"repository-manifest-invalid:{repo_manifest_message or 'unknown'}")

    run_roots = sorted(
        [path.parent for path in runs_dir.rglob("metadata.json")],
        key=lambda p: str(p),
    )
    archives: list[dict[str, object]] = []
    for entry in run_roots:
        run_id = entry.name
        metadata_path = entry / "metadata.json"
        snapshot_path = entry / "SESSION_STATE.json"
        run_manifest_path = entry / "run-manifest.json"
        checksums_path = entry / "checksums.json"
        if not metadata_path.exists():
            notes.append(f"run-metadata-missing:{run_id}")
            continue
        if not snapshot_path.exists():
            notes.append(f"run-session-state-missing:{run_id}")
            continue
        try:
            metadata = _read_json(metadata_path)
        except Exception:
            notes.append(f"run-metadata-invalid:{run_id}")
            continue
        try:
            snapshot_document = _read_json(snapshot_path)
        except Exception:
            notes.append(f"run-session-state-invalid:{run_id}")
            continue

        state_view = _extract_state_view(snapshot_document)
        effective_mode, resolved_mode, verify_policy_version = _extract_mode_fields(state_view)

        metadata_run_id = str(metadata.get("run_id") or run_id).strip() or run_id
        digest = str(metadata.get("snapshot_digest") or "").strip()
        archived_at = str(metadata.get("archived_at") or "").strip()
        source_phase = str(metadata.get("source_phase") or "unknown").strip() or "unknown"
        run_status = "unknown"
        integrity_status = "unknown"

        if run_manifest_path.exists():
            try:
                run_manifest = _read_json(run_manifest_path)
                run_status = str(run_manifest.get("run_status") or "unknown").strip() or "unknown"
                integrity_status = str(run_manifest.get("integrity_status") or "unknown").strip() or "unknown"
                manifest_resolved = str(run_manifest.get("resolvedOperatingMode") or "").strip().lower()
                manifest_verify = str(run_manifest.get("verifyPolicyVersion") or "").strip()
                if manifest_resolved:
                    resolved_mode = manifest_resolved
                if manifest_verify:
                    verify_policy_version = manifest_verify
            except Exception:
                notes.append(f"run-manifest-invalid:{run_id}")
        else:
            notes.append(f"run-manifest-missing:{run_id}")

        if not checksums_path.exists():
            notes.append(f"run-checksums-missing:{run_id}")

        verify_ok, _, verify_message = _verify_run_archive_proxy(entry)
        if not verify_ok:
            notes.append(f"run-verify-failed:{run_id}:{verify_message or 'unknown'}")

        if not digest:
            notes.append(f"run-snapshot-digest-missing:{run_id}")
            digest = canonical_json_hash(snapshot_document)
        if not archived_at:
            notes.append(f"run-archived-at-missing:{run_id}")
            archived_at = "1970-01-01T00:00:00Z"

        archives.append(
            {
                "run_id": metadata_run_id,
                "snapshot_path": str(snapshot_path),
                "snapshot_digest": digest,
                "archived_at": archived_at,
                "source_phase": source_phase,
                "run_status": run_status,
                "integrity_status": integrity_status,
                "effective_operating_mode": effective_mode,
                "resolved_operating_mode": resolved_mode,
                "verify_policy_version": verify_policy_version,
            }
        )

    return archives, notes


def _build_last_snapshot(
    *,
    events: list[dict[str, object]],
    active_run_id: str,
    run_archives: list[dict[str, object]],
) -> tuple[dict[str, object], list[str]]:
    notes: list[str] = []
    if not run_archives:
        return {
            "snapshot_path": "none",
            "snapshot_digest": "0" * 64,
            "archived_at": "1970-01-01T00:00:00Z",
            "source_phase": "none",
            "run_id": "none",
            "run_status": "unknown",
            "integrity_status": "unknown",
            "effective_operating_mode": "unknown",
            "resolved_operating_mode": "solo",
            "verify_policy_version": "v1",
        }, ["missing-run-archive-snapshot"]

    by_run_id = {str(item.get("run_id") or ""): item for item in run_archives}

    for event in reversed(events):
        if str(event.get("event") or "") != "new_work_session_created":
            continue
        snapshot_run_id = str(event.get("run_id") or "").strip()
        if not snapshot_run_id or snapshot_run_id == active_run_id:
            continue
        archive = by_run_id.get(snapshot_run_id)
        if archive is None:
            notes.append(f"created-event-references-missing-run:{snapshot_run_id}")
            continue
        return dict(archive), notes

    notes.append("last-snapshot-derived-from-archive-fallback")
    candidate_archives = [item for item in run_archives if str(item.get("run_id") or "") != active_run_id]
    source = candidate_archives if candidate_archives else run_archives

    def _key(item: Mapping[str, object]) -> tuple[datetime, str]:
        raw = str(item.get("archived_at") or "")
        try:
            parsed = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except Exception:
            parsed = datetime.fromtimestamp(0, tz=timezone.utc)
        return parsed, str(item.get("snapshot_path") or "")

    return dict(sorted(source, key=_key)[-1]), notes


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
    last_event_type = str(last.get("event") or "")
    if last_event_type == "new_work_session_created":
        expected = str(last.get("new_run_id") or "")
        if active_run_id != expected:
            notes.append("active-run-id-mismatch-created-event")
            return False, notes
        return True, notes

    if last_event_type == "work_session_reactivated":
        expected = str(last.get("reactivated_run_id") or "")
        if active_run_id != expected:
            notes.append("active-run-id-mismatch-reactivation-event")
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


def _snapshot_quality(last_snapshot: Mapping[str, object]) -> list[str]:
    notes: list[str] = []
    run_status = str(last_snapshot.get("run_status") or "unknown").strip()
    integrity_status = str(last_snapshot.get("integrity_status") or "unknown").strip()
    if run_status != "finalized":
        notes.append(f"snapshot-run-not-finalized:{run_status or 'unknown'}")
    if integrity_status != "passed":
        notes.append(f"snapshot-integrity-not-passed:{integrity_status or 'unknown'}")
    return notes


def _active_run_pointer_consistent(active: Mapping[str, object], *, pointer_run_id: str) -> tuple[bool, list[str]]:
    notes: list[str] = []
    active_run_id = str(active.get("run_id") or "").strip()
    if not pointer_run_id:
        notes.append("missing-current-run-pointer")
        return False, notes
    if pointer_run_id != active_run_id:
        notes.append("current-run-pointer-mismatch")
        return False, notes
    return True, notes


def _reactivation_chain_consistent(
    active: Mapping[str, object],
    *,
    pointer_run_id: str,
    events: list[dict[str, object]],
    run_archives: list[dict[str, object]],
) -> tuple[bool, list[str]]:
    notes: list[str] = []
    run_ids = {str(item.get("run_id") or "") for item in run_archives}
    reactivations = [event for event in events if str(event.get("event") or "") == "work_session_reactivated"]
    if not reactivations:
        return True, notes

    for event in reactivations:
        run_id = str(event.get("reactivated_run_id") or "").strip()
        if not run_id:
            notes.append("reactivation-event-missing-run-id")
            return False, notes
        if run_id not in run_ids:
            notes.append(f"reactivation-event-run-missing:{run_id}")
            return False, notes

    last = reactivations[-1]
    expected = str(last.get("reactivated_run_id") or "").strip()
    if expected != str(active.get("run_id") or "").strip():
        notes.append("active-run-id-mismatch-last-reactivation")
        return False, notes
    if pointer_run_id and pointer_run_id != expected:
        notes.append("pointer-run-id-mismatch-last-reactivation")
        return False, notes
    return True, notes


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

    pointer = _parse_session_pointer_document_proxy(_read_json(pointer_path))
    session_path = _resolve_active_session_state_path_proxy(pointer, config_root=config_root)
    state_document = _read_json(session_path)
    state = _extract_state_view(state_document)
    active_effective_mode, active_resolved_mode, active_verify_policy_version = _extract_mode_fields(state)

    active = {
        "run_id": _state_text(state, "session_run_id") or "unknown",
        "phase": _state_text(state, "Phase", "phase") or "unknown",
        "active_gate": _state_text(state, "active_gate", "ActiveGate") or "unknown",
        "next": _state_text(state, "Next", "next") or "unknown",
        "updated_at": _extract_updated_at(state, session_path=session_path),
        "effective_operating_mode": active_effective_mode,
        "resolved_operating_mode": active_resolved_mode,
        "verify_policy_version": active_verify_policy_version,
    }

    events_raw = _parse_jsonl(session_path.parent / "events.jsonl")
    normalized_events: list[dict[str, object]] = []
    for event in events_raw:
        normalized = _event_with_required_fields(event)
        if normalized is not None:
            normalized_events.append(normalized)
    tail = normalized_events[-max(0, int(tail_count)):]

    pointer_run_id, pointer_notes = _read_current_run_pointer(session_path.parent)
    run_archives, archive_notes = _list_run_archives(session_path.parent)
    last_snapshot, snapshot_notes = _build_last_snapshot(
        events=tail,
        active_run_id=str(active.get("run_id") or ""),
        run_archives=run_archives,
    )

    snapshot_ref_present, snapshot_ref_notes = _snapshot_ref_present(tail, last_snapshot=last_snapshot)
    run_id_consistent, run_id_notes = _run_id_consistent(active, tail)
    monotonic_timestamps, monotonic_notes = _timestamps_monotonic(tail, last_snapshot=last_snapshot)
    snapshot_quality_notes = _snapshot_quality(last_snapshot)
    snapshot_quality_ok = len(snapshot_quality_notes) == 0
    pointer_consistent, pointer_integrity_notes = _active_run_pointer_consistent(active, pointer_run_id=pointer_run_id)
    reactivation_consistent, reactivation_notes = _reactivation_chain_consistent(
        active,
        pointer_run_id=pointer_run_id,
        events=tail,
        run_archives=run_archives,
    )
    run_archives_verified = not any(
        note.startswith("run-verify-failed:") or note.startswith("repository-manifest-invalid:")
        for note in archive_notes
    )

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
            "active_run_pointer_consistent": pointer_consistent,
            "reactivation_chain_consistent": reactivation_consistent,
            "snapshot_quality_ok": snapshot_quality_ok,
            "run_archives_verified": run_archives_verified,
            "notes": archive_notes
            + pointer_notes
            + pointer_integrity_notes
            + snapshot_notes
            + snapshot_ref_notes
            + snapshot_quality_notes
            + run_id_notes
            + monotonic_notes
            + reactivation_notes,
        },
    }

    validation_errors = validate_audit_readout_v1(payload)
    if validation_errors:
        raise ValueError("invalid audit readout contract: " + "; ".join(validation_errors))
    return payload


__all__ = ["build_audit_readout"]
