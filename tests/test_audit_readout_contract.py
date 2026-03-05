from __future__ import annotations

from governance.engine.audit_readout_contract import validate_audit_readout_v1


def _valid_payload() -> dict[str, object]:
    return {
        "contract_version": "AUDIT_READOUT_SPEC.v1",
        "active": {
            "run_id": "work-1",
            "phase": "4",
            "active_gate": "Ticket Input Gate",
            "next": "5",
            "updated_at": "2026-03-05T20:34:32Z",
        },
        "last_snapshot": {
            "snapshot_path": "/tmp/work_runs/work-0.json",
            "snapshot_digest": "a" * 64,
            "archived_at": "2026-03-05T20:30:00Z",
            "source_phase": "6-PostFlight",
            "run_id": "work-0",
        },
        "chain": {
            "tail_count": 1,
            "events": [
                {
                    "event": "new_work_session_created",
                    "observed_at": "2026-03-05T20:34:32Z",
                    "repo_fingerprint": "fp",
                    "session_id": "sess",
                    "run_id": "work-0",
                    "new_run_id": "work-1",
                    "snapshot_path": "/tmp/work_runs/work-0.json",
                    "snapshot_digest": "a" * 64,
                }
            ],
        },
        "integrity": {
            "snapshot_ref_present": True,
            "run_id_consistent": True,
            "monotonic_timestamps": True,
            "notes": [],
        },
    }


def test_happy_valid_payload_has_no_errors() -> None:
    assert validate_audit_readout_v1(_valid_payload()) == []


def test_bad_created_event_requires_snapshot_refs() -> None:
    payload = _valid_payload()
    event = payload["chain"]["events"][0]
    del event["snapshot_path"]
    del event["snapshot_digest"]
    errors = validate_audit_readout_v1(payload)
    assert any("snapshot_path:required-for-created" in e for e in errors)
    assert any("snapshot_digest:required-for-created" in e for e in errors)


def test_bad_dedupe_event_requires_reason() -> None:
    payload = _valid_payload()
    payload["chain"]["events"] = [
        {
            "event": "new_work_session_deduped",
            "observed_at": "2026-03-05T20:34:32Z",
            "repo_fingerprint": "fp",
            "session_id": "sess",
            "run_id": "work-1",
        }
    ]
    errors = validate_audit_readout_v1(payload)
    assert any("reason:required-for-dedupe-events" in e for e in errors)


def test_bad_timestamp_without_z_suffix_is_rejected() -> None:
    payload = _valid_payload()
    payload["active"]["updated_at"] = "2026-03-05T20:34:32+00:00"
    errors = validate_audit_readout_v1(payload)
    assert any("$.active.updated_at:pattern" in e for e in errors)
