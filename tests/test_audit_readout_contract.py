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
            "effective_operating_mode": "pipeline",
            "resolved_operating_mode": "team",
            "verify_policy_version": "v1",
        },
        "last_snapshot": {
            "snapshot_path": "/mock/runs/work-0/SESSION_STATE.json",
            "snapshot_digest": "a" * 64,
            "archived_at": "2026-03-05T20:30:00Z",
            "source_phase": "6-PostFlight",
            "run_id": "work-0",
            "run_status": "finalized",
            "integrity_status": "passed",
            "effective_operating_mode": "pipeline",
            "resolved_operating_mode": "team",
            "verify_policy_version": "v1",
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
                    "snapshot_path": "/mock/runs/work-0/SESSION_STATE.json",
                    "snapshot_digest": "a" * 64,
                }
            ],
        },
        "integrity": {
            "snapshot_ref_present": True,
            "run_id_consistent": True,
            "monotonic_timestamps": True,
            "active_run_pointer_consistent": True,
            "reactivation_chain_consistent": True,
            "snapshot_quality_ok": True,
            "run_archives_verified": True,
            "notes": [],
        },
    }


def test_happy_valid_payload_has_no_errors() -> None:
    assert validate_audit_readout_v1(_valid_payload()) == []


def test_bad_created_event_requires_snapshot_refs() -> None:
    payload = _valid_payload()
    chain = payload["chain"]
    assert isinstance(chain, dict)
    events = chain.get("events")
    assert isinstance(events, list)
    event = events[0]
    assert isinstance(event, dict)
    del event["snapshot_path"]
    del event["snapshot_digest"]
    errors = validate_audit_readout_v1(payload)
    assert any("snapshot_path:required-for-created" in e for e in errors)
    assert any("snapshot_digest:required-for-created" in e for e in errors)


def test_bad_dedupe_event_requires_reason() -> None:
    payload = _valid_payload()
    chain = payload["chain"]
    assert isinstance(chain, dict)
    chain["events"] = [
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
    active = payload["active"]
    assert isinstance(active, dict)
    active["updated_at"] = "2026-03-05T20:34:32+00:00"
    errors = validate_audit_readout_v1(payload)
    assert any("$.active.updated_at:pattern" in e for e in errors)


def test_bad_reactivation_event_requires_reactivated_run_id() -> None:
    payload = _valid_payload()
    chain = payload["chain"]
    assert isinstance(chain, dict)
    chain["events"] = [
        {
            "event": "work_session_reactivated",
            "observed_at": "2026-03-05T20:34:32Z",
            "repo_fingerprint": "fp",
            "session_id": "sess",
            "run_id": "work-2",
            "previous_run_id": "work-2",
        }
    ]
    errors = validate_audit_readout_v1(payload)
    assert any("reactivated_run_id:required-for-reactivation" in e for e in errors)
